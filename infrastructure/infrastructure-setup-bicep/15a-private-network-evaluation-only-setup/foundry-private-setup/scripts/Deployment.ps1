#Requires -Version 7.2
[CmdletBinding()]
param(
    [ValidateSet('Preview','Apply','Reconcile')][string]$Action,
    [string]$ConfigPath,[string]$Template,[string]$ParametersPath,[string]$PlanPath,
    [string]$ApprovalHash,[string]$ReceiptDirectory,[string]$OutputPath
)
. (Join-Path $PSScriptRoot 'Inspection.ps1')
. (Join-Path $PSScriptRoot 'DeploymentRules.ps1')
. (Join-Path $PSScriptRoot 'OperationScope.ps1')

function Get-ReferencedIds($Value) {
    if ($Value -is [Collections.IDictionary]) { foreach ($item in $Value.Values) { Get-ReferencedIds $item } }
    elseif ($Value -is [array]) { foreach ($item in $Value) { Get-ReferencedIds $item } }
    elseif ($Value -is [string] -and $Value.StartsWith('/subscriptions/')) { $Value }
}
function New-GroupPreview($Config) {
    Assert-SetupContext $Config
    $id = (Get-SetupIds $Config).ResourceGroup
    $before = Get-CurrentState @($id)
    $exists = $before.resources[$id] -ne 'Absent'
    if ($Config.resourceGroup.mode -eq 'existing' -and !$exists) { throw 'Existing RG is not observable.' }
    if ($Config.resourceGroup.mode -eq 'create' -and $exists) { throw 'RG already exists; reconcile its prior attempt, never blindly re-PUT.' }
    $request = @{ resourceId = $id; method = $(if ($exists) { 'None' } else { 'PUT' }); body = @{ location = $Config.location } }
    Seal-Approval (New-Approval 'ResourceGroup' $Config $request $before)
}
function Submit-Group($Plan,[string]$Hash,[string]$Directory) {
    Assert-Approval $Plan $Hash
    Assert-SetupContext $Plan.config
    $attempt = New-Attempt $Plan $Directory
    Assert-NoDrift $Plan (Get-CurrentState @($Plan.request.resourceId)) $attempt
    if ($Plan.request.method -eq 'None') {
        Confirm-Attempt $attempt @{ state = 'VerifiedExisting'; resourceId = $Plan.request.resourceId } (Join-Path $Directory 'last-verified-rg.json')
        return $attempt.receipt
    }
    try {
        $response = Invoke-AttemptWrite $attempt { Invoke-SetupArm PUT $Plan.request.resourceId $Plan.request.body -OnStart { Mark-Attempt $attempt 'SubmissionAttempted' } }
        if ($response.Code -ne 200) { Mark-Attempt $attempt 'OutcomeUnknown' 'RG outcome unknown; reconcile without repeating PUT.'; return $attempt.receipt }
        $actual = Wait-SetupResource $Plan.request.resourceId 300 -AllowMissingState
        if (!(Test-Subset $Plan.request.body $actual)) { throw 'RG readback mismatch.' }
        Confirm-Attempt $attempt @{ state = 'Succeeded'; resourceId = $actual.id } (Join-Path $Directory 'last-verified-rg.json')
    } catch { Mark-Attempt $attempt $(if (Test-Submitted $attempt) { 'OutcomeUnknown' } else { 'NotSubmitted' }) $_.Exception.Message; throw }
    return $attempt.receipt
}
function Reconcile-Group($Plan,[string]$Directory) {
    $attempt = Read-Attempt $Plan $Directory
    if ($attempt.receipt.state -in @('NotSubmitted','Succeeded','Failed')) { return $attempt.receipt }
    $actual = Get-SetupResource $Plan.request.resourceId -Optional
    if ($actual -and (Test-Subset $Plan.request.body $actual)) {
        Confirm-Attempt $attempt @{ state = 'ObservedConfigured'; resourceId = $actual.id; attribution = 'Observed state, not proof of which caller created it.' } (Join-Path $Directory 'last-verified-rg.json')
    } else { Mark-Attempt $attempt 'OutcomeUnknown' 'No matching RG outcome is observable; do not retry blindly.' }
    return $attempt.receipt
}
function Invoke-DeploymentCli {
    param([string]$Verb,$Plan,[scriptblock]$OnStart)
    $temp = Join-Path ([IO.Path]::GetTempPath()) ('foundry-deployment-' + [guid]::NewGuid())
    $null = New-Item -ItemType Directory -Path $temp
    try {
        $templateFile = Join-Path $temp 'template.json'
        $parametersFile = Join-Path $temp 'parameters.json'
        Write-Json $templateFile $Plan.request.template
        Write-Json $parametersFile @{ parameters = $Plan.request.parameters }
        $ids = $Plan.request.scope.Split('/')
        $arguments = @('deployment','group',$Verb,'--subscription',$ids[2],'--resource-group',$ids[4],
            '--name',$Plan.request.name,'--template-file',$templateFile,'--parameters',"@$parametersFile")
        if ($Verb -eq 'what-if') {
            $arguments += @('--no-pretty-print','--result-format','FullResourcePayloads',
                '--query','{changes:changes[].{resourceId:resourceId,changeType:changeType}}')
        } else { $arguments += @('--no-wait','--query','{id:id}') }
        return Invoke-SetupCli $arguments -OnStart $OnStart
    } finally {
        foreach ($file in (Get-ChildItem -LiteralPath $temp -File)) { Remove-Item -LiteralPath $file.FullName }
        Remove-Item -LiteralPath $temp
    }
}
function New-DeploymentPreview {
    param($Config,[string]$Asset,$Values)
    Assert-SetupContext $Config
    $timings = @(); $clock = Start-Phase 'LocalPreparation'
    $folder = Join-Path $PSScriptRoot '..\assets\bicep'
    $allowed = @('account','project','network','storage','monitoring','workspace','connections','connectivity','monitor-scope','monitor-connectivity')
    if ($Asset -cnotin $allowed) { throw 'Select an included Bicep asset by its exact short name.' }
    $compiled = Invoke-LocalBicep (Join-Path $folder "$Asset.bicep")
    if ($Asset -eq 'storage' -and $compiled.resources[0].kind -cne 'StorageV2') { throw 'Azure GPv2 requires StorageV2, independent of build exit code.' }
    $parameters = @{}
    foreach ($key in $Values.Keys) {
        if (!$compiled.parameters.Contains($key)) { throw "Unknown asset parameter: $key." }
        $parameters[$key] = @{ value = $Values[$key] }
    }
    foreach ($key in $compiled.parameters.Keys) {
        if (!$parameters.Contains($key)) {
            if (!$compiled.parameters[$key].Contains('defaultValue')) { throw "Missing asset parameter: $key." }
            $parameters[$key] = @{ value = $compiled.parameters[$key].defaultValue }
        }
    }
    $timings += Stop-Phase $clock
    $ids = Get-SetupIds $Config
    $scope = if ($Asset -eq 'connections' -and $Config.foundryAccount.mode -eq 'existing') {
        $ids.Account -replace '/providers/Microsoft.CognitiveServices/accounts/[^/]+$',''
    } else { $ids.ResourceGroup }
    $null = Get-SetupResource $scope
    $request = @{ scope = $scope; asset = $Asset; template = $compiled; parameters = $parameters; observedIds = @() }
    $state = Get-DeploymentState $Config $request
    Assert-DeploymentParameters $Config $Asset $Values $parameters @{ state = $state.material }
    $plan = New-Approval 'Deployment' $Config $request $state.material
    $plan.observed = $state.observations
    $plan.request.name = "setup-$Asset-$($plan.operationId.Substring(0,12))"
    $plan.request.resourceId = "$scope/providers/Microsoft.Resources/deployments/$($plan.request.name)"
    if (Get-SetupResource $plan.request.resourceId -Optional) { throw 'Unique operation deployment name already exists; no reuse of old deployment state.' }
    $clock = Start-Phase 'PreviewWhatIf'
    $preview = Invoke-DeploymentCli 'what-if' $plan
    $timings += Stop-Phase $clock
    if ($preview.Code -ne 200 -or !$preview.Data.Contains('changes')) { throw 'Actual Azure what-if is unavailable; no write approval generated.' }
    $changes = @()
    foreach ($change in $preview.Data.changes) {
        if ($change.changeType -eq 'Modify') { throw "Existing-resource modification requires a different reviewed operation: $($change.resourceId)." }
        if ($change.changeType -notin @('Create','NoChange','Ignore')) { throw 'Destructive/unexpanded/unknown what-if change cannot be approved by this helper.' }
        $changes += @{ resourceId = $change.resourceId; changeType = $change.changeType }
    }
    if (@(Get-SemanticDiff $plan.before (Get-DeploymentState $Config $plan.request).material).Count) {
        throw 'State changed during what-if; inspect it and create a fresh preview. No approval generated.'
    }
    foreach ($change in $changes) {
        if ($change.changeType -eq 'Create' -and (Get-SetupResource $change.resourceId -Optional)) {
            throw 'What-if creation target is no longer absent; no stale approval.'
        }
    }
    $plan.request.observedIds = @($changes | Where-Object changeType -in @('Create','NoChange') | ForEach-Object resourceId | Sort-Object -Unique)
    $state = Get-DeploymentState $Config $plan.request
    $plan.before = $state.material; $plan.observed = $state.observations
    $plan.preview = $changes
    $plan.request.bicepGeneratorHash = [string]$compiled.metadata._generator.templateHash
    $plan.request.parametersHash = Get-Digest (Get-ParameterValues $compiled $parameters)
    $plan.timings = $timings
    return Seal-Approval $plan
}
function Get-ParameterValues($Template,$Parameters) {
    foreach ($key in $Parameters.Keys) { if (!$Template.parameters.Contains($key)) { throw "Unknown observed parameter: $key." } }
    $values = @{}
    foreach ($key in $Template.parameters.Keys) {
        if ($Parameters.Contains($key)) {
            if ($Parameters[$key] -isnot [Collections.IDictionary] -or !$Parameters[$key].Contains('value')) { throw 'Unobservable/redacted parameter value cannot be attributed.' }
            $values[$key] = $Parameters[$key].value
        } elseif ($Template.parameters[$key].Contains('defaultValue')) {
            $default = $Template.parameters[$key].defaultValue
            if ($default -is [string] -and $default.StartsWith('[')) { throw 'Expression default requires an explicit resolved value; no guessed Azure evaluation.' }
            $values[$key] = $default
        } else { throw "Required observed parameter is missing: $key." }
    }
    return $values
}
function ConvertTo-TemplateDocument($Template) {
    $document = Copy-Data $Template
    if ($document -isnot [Collections.IDictionary]) { throw 'ARM template document must be an object.' }
    if ($document.Contains('metadata') -and $document.metadata -is [Collections.IDictionary] -and $document.metadata.Contains('_generator')) {
        $generator = $document.metadata['_generator']
        if ($generator -is [Collections.IDictionary] -and $generator.Contains('name') -and $generator.name -ceq 'bicep' -and
            !@($generator.Keys | Where-Object { $_ -cnotin @('name','version','templateHash') }).Count) {
            $document.metadata.Remove('_generator')
            if (!$document.metadata.Count) { $document.Remove('metadata') }
        }
    }
    foreach ($section in @('parameters','outputs')) {
        if ($document.Contains($section) -and $document[$section] -is [Collections.IDictionary]) {
            foreach ($declaration in $document[$section].Values) {
                if ($declaration -is [Collections.IDictionary] -and $declaration.Contains('type') -and $declaration.type -is [string]) {
                    $declaration.type = $declaration.type.ToLowerInvariant()
                }
            }
        }
    }
    function Convert-NestedResources($Resources) {
        $items = if ($Resources -is [Collections.IDictionary]) { @($Resources.Values) } else { @($Resources) }
        foreach ($resource in $items) {
            if ($resource -isnot [Collections.IDictionary]) { continue }
            if ($resource.Contains('type') -and $resource.type -ieq 'Microsoft.Resources/deployments' -and
                $resource.Contains('properties') -and $resource.properties -is [Collections.IDictionary] -and
                $resource.properties.Contains('template') -and $resource.properties.template -is [Collections.IDictionary]) {
                $resource.properties.template = ConvertTo-TemplateDocument $resource.properties.template
            }
            if ($resource.Contains('resources')) { Convert-NestedResources $resource.resources }
        }
    }
    if ($document.Contains('resources')) { Convert-NestedResources $document.resources }
    return $document
}
function Get-TemplateContentHash($Template) {
    function Convert-Content($Value) {
        if ($Value -is [Collections.IDictionary]) {
            $sorted = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
            $keys = [string[]]@($Value.Keys); [array]::Sort($keys,[StringComparer]::Ordinal)
            foreach ($key in $keys) { $sorted.Add($key,(Convert-Content $Value[$key])) }
            return $sorted
        }
        if ($Value -is [array]) { return ,@($Value | ForEach-Object { Convert-Content $_ }) }
        return $Value
    }
    $json = ConvertTo-Json -InputObject (Convert-Content (ConvertTo-TemplateDocument $Template)) -Depth 100 -Compress
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))).ToLowerInvariant()
}
function Invoke-DeploymentExport($Plan) {
    $parts = $Plan.request.resourceId.Split('/')
    Invoke-SetupCli @('deployment','group','export','--subscription',$parts[2],'--resource-group',$parts[4],'--name',$parts[-1])
}
function Get-TemplateContentProof($Plan,$Attempt,$Deployment) {
    $approvedHash = Get-TemplateContentHash $Plan.request.template
    $binding = @{ operationId = $Plan.operationId; requestHash = (Get-Digest $Plan.request)
        submissionStartedAt = $Attempt.receipt.submissionStartedAt; deploymentId = $Plan.request.resourceId
        providerTemplateHash = [string]$Deployment.properties.templateHash; correlationId = $Deployment.properties.correlationId
        approvedContentHash = $approvedHash }
    if ($Attempt.receipt.Contains('templateContentProof')) {
        $cached = $Attempt.receipt.templateContentProof
        if ($cached -isnot [Collections.IDictionary] -or !$cached.Contains('binding') -or
            (Get-Digest $cached.binding) -cne (Get-Digest $binding) -or !$cached.Contains('exportedContentHash') -or
            $cached.exportedContentHash -cne $approvedHash) {
            return @{ state = 'OutcomeUnknown'; attributionCode = 'TemplateProofBindingChanged'
                reason = 'Cached exact template proof no longer matches this request/attempt/provider hash/correlation. No new write is authorized.' }
        }
        return @{ state = 'Matched'; contentHash = $approvedHash }
    }
    try { $export = Invoke-DeploymentExport $Plan }
    catch {
        return @{ state = 'OutcomeUnknown'; attributionCode = 'DeploymentExportUnavailable'
            reason = 'Read-only native deployment export failed; content attribution is unavailable. No permissions or writes were added.' }
    }
    if ($export.Code -ne 200) {
        return @{ state = 'OutcomeUnknown'; attributionCode = 'DeploymentExportUnavailable'; status = $export.Code
            reason = "Read-only native deployment export unavailable (status $($export.Code)); exact template content cannot be verified." }
    }
    try { $actualHash = Get-TemplateContentHash $export.Data }
    catch {
        return @{ state = 'OutcomeUnknown'; attributionCode = 'DeploymentExportInvalidTemplate'
            reason = 'Read-only deployment export did not yield a canonical ARM template document; no content was logged.' }
    }
    if ($actualHash -cne $approvedHash) {
        return @{ state = 'OutcomeUnknown'; attributionCode = 'TemplateContentMismatch'; approvedContentHash = $approvedHash
            exportedContentHash = $actualHash; reason = 'Full deployed-template content differs from the approved template after narrow compiler/type normalization.' }
    }
    $Attempt.receipt.templateContentProof = @{ binding = $binding; exportedContentHash = $actualHash; method = 'NativeExportFullContentV1' }
    if ($Attempt.Contains('path')) { Write-Json $Attempt.path $Attempt.receipt }
    return @{ state = 'Matched'; contentHash = $approvedHash }
}
function Get-DeploymentOutcome($Plan,$Attempt) {
    $deployment = Get-SetupResource $Plan.request.resourceId -Optional
    if (!$deployment) { return @{ state = 'OutcomeUnknown'; reason = 'No observable deployment is not proof the write was never submitted.' } }
    $properties = $deployment.properties
    if (!$properties.Contains('templateHash') -or ![string]$properties.templateHash -or
        !$properties.Contains('parameters') -or
        !$properties.Contains('correlationId') -or !$properties.correlationId -or !$properties.Contains('timestamp')) {
        return @{ state = 'OutcomeUnknown'; reason = 'Observed deployment content/attempt identity cannot be attributed to this request.' }
    }
    try { $observedHash = Get-Digest (Get-ParameterValues $Plan.request.template $properties.parameters) }
    catch { return @{ state = 'OutcomeUnknown'; reason = $_.Exception.Message } }
    if ($observedHash -cne $Plan.request.parametersHash) { return @{ state = 'OutcomeUnknown'; reason = 'Actual parameter values differ; Azure type wrappers alone are not a drift.' } }
    if ($Attempt.receipt.Contains('correlationId') -and $Attempt.receipt.correlationId -cne $properties.correlationId) {
        return @{ state = 'OutcomeUnknown'; reason = 'Correlation differs from the recorded attempt.' }
    }
    $timestamp = if ($properties.timestamp -is [datetime]) { ([DateTimeOffset]$properties.timestamp).ToUnixTimeMilliseconds() }
        else { [DateTimeOffset]::Parse([string]$properties.timestamp).ToUnixTimeMilliseconds() }
    if ($timestamp -lt $Attempt.receipt.submissionStartedAt - 300000) {
        return @{ state = 'OutcomeUnknown'; reason = 'Old same-name deployment is not this attempt.' }
    }
    if (!$deployment.Contains('id') -or $deployment.id -ine $Plan.request.resourceId) {
        return @{ state = 'OutcomeUnknown'; attributionCode = 'DeploymentIdMismatch'; reason = 'Observed deployment ID differs from the original operation.' }
    }
    $proof = Get-TemplateContentProof $Plan $Attempt $deployment
    if ($proof.state -ne 'Matched') { return $proof }
    if ($properties.provisioningState -eq 'Succeeded') {
        return @{ state = 'Succeeded'; correlationId = $properties.correlationId; deploymentId = $deployment.id
            azureDurationMs = $(if ($properties.Contains('duration')) { [Xml.XmlConvert]::ToTimeSpan($properties.duration).TotalMilliseconds } else { $null })
            templateContentHash = $proof.contentHash; providerTemplateHash = [string]$properties.templateHash
            evidence = 'Authoritative deployment status, exact full native-export template content, normalized parameter values and attempt attribution; setup only.' }
    }
    if ($properties.provisioningState -in @('Failed','Canceled')) {
        return @{ state = $properties.provisioningState; correlationId = $properties.correlationId; deploymentId = $deployment.id }
    }
    return @{ state = 'Running'; correlationId = $properties.correlationId; deploymentId = $deployment.id }
}
function Submit-Deployment($Plan,[string]$Hash,[string]$Directory,[int]$TimeoutSeconds = 900) {
    Assert-Approval $Plan $Hash
    Assert-SetupContext $Plan.config
    $attempt = New-Attempt $Plan $Directory
    $attempt.receipt.timings = @($Plan.timings)
    $current = Get-DeploymentState $Plan.config $Plan.request
    Assert-OperationCurrent $Plan $current $attempt
    if (Get-SetupResource $Plan.request.resourceId -Optional) {
        Mark-Attempt $attempt 'NotSubmitted' 'Same-name deployment exists before submission; never attribute its success to a new request.'
        throw 'Deployment name collision: NotSubmitted.'
    }
    if (!@($Plan.preview | Where-Object { $_.changeType -eq 'Create' }).Count) {
        Confirm-Attempt $attempt @{ state = 'VerifiedNoChange' } (Join-Path $Directory 'last-verified-deployment.json')
        return $attempt.receipt
    }
    try {
        $response = Invoke-AttemptWrite $attempt { Invoke-DeploymentCli 'create' $Plan -OnStart { Mark-Attempt $attempt 'SubmissionAttempted' } }
        if ($response.Code -ne 200) {
            Mark-Attempt $attempt 'OutcomeUnknown' "Submission command did not confirm outcome ($($response.Code)); reconcile, never blindly retry."
            return $attempt.receipt
        }
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $statusClock = Start-Phase 'DeploymentStatusVerification'
        do {
            $outcome = Get-DeploymentOutcome $Plan $attempt
            $attempt.receipt.attribution = $outcome
            if ($outcome.Contains('correlationId')) { $attempt.receipt.correlationId = $outcome.correlationId; Write-Json $attempt.path $attempt.receipt }
            if ($outcome.state -in @('Succeeded','Failed','Canceled')) {
                Add-AttemptTiming $attempt (Stop-Phase $statusClock)
                Confirm-Attempt $attempt $outcome (Join-Path $Directory 'last-verified-deployment.json')
                return $attempt.receipt
            }
            if ($outcome.state -eq 'OutcomeUnknown') { break }
            if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
                Add-AttemptTiming $attempt (Stop-Phase $statusClock)
                Mark-Attempt $attempt 'Running' 'Azure confirms this attempt is running. Read-only reconciliation is bounded; do not resubmit.'
                return $attempt.receipt
            }
            Start-Sleep -Seconds 10
        } while ($true)
        Add-AttemptTiming $attempt (Stop-Phase $statusClock)
        Mark-Attempt $attempt 'OutcomeUnknown' $outcome.reason
    } catch {
        Mark-Attempt $attempt $(if (Test-Submitted $attempt) { 'OutcomeUnknown' } else { 'NotSubmitted' }) $_.Exception.Message
        throw
    }
    return $attempt.receipt
}
function Reconcile-Deployment($Plan,[string]$Directory) {
    $attempt = Read-Attempt $Plan $Directory
    if ($attempt.receipt.state -in @('NotSubmitted','Succeeded','Failed')) { return $attempt.receipt }
    $clock = Start-Phase 'Reconciliation'
    $outcome = Get-DeploymentOutcome $Plan $attempt
    $attempt.receipt.attribution = $outcome
    Add-AttemptTiming $attempt (Stop-Phase $clock)
    if ($outcome.state -in @('Succeeded','Failed','Canceled')) {
        Confirm-Attempt $attempt $outcome (Join-Path $Directory 'last-verified-deployment.json')
    } else {
        $reason = if ($outcome.Contains('reason')) { $outcome.reason } else { 'One bounded status read; Running can be reconciled later, unknown never resubmitted.' }
        Mark-Attempt $attempt $outcome.state $reason
    }
    return $attempt.receipt
}
if ($Action) {
    if ($Action -eq 'Preview') {
        $config = Read-SetupConfig $ConfigPath
        if ($Template -eq 'resource-group') { Write-Json $OutputPath (New-GroupPreview $config) }
        else {
            $document = Read-Json $ParametersPath
            $values = @{}
            foreach ($key in $document.parameters.Keys) { $values[$key] = $document.parameters[$key].value }
            Write-Json $OutputPath (New-DeploymentPreview $config $Template $values)
        }
    } else {
        $plan = Read-Json $PlanPath
        if ($plan.kind -eq 'ResourceGroup') {
            if ($Action -eq 'Apply') { Submit-Group $plan $ApprovalHash $ReceiptDirectory } else { Reconcile-Group $plan $ReceiptDirectory }
        } elseif ($plan.kind -eq 'Deployment') {
            if ($Action -eq 'Apply') { Submit-Deployment $plan $ApprovalHash $ReceiptDirectory } else { Reconcile-Deployment $plan $ReceiptDirectory }
        } else { throw 'Wrong helper for this operation kind.' }
    }
}
