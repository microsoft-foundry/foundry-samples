#Requires -Version 7.2
. (Join-Path $PSScriptRoot 'Input.ps1')
. (Join-Path $PSScriptRoot 'Transport.ps1')

function ConvertFrom-SetupJson([string]$Text) {
    function Convert-Element($Element) {
        switch ($Element.ValueKind.ToString()) {
            'Object' { $map = [hashtable]::new([StringComparer]::Ordinal); foreach ($p in $Element.EnumerateObject()) { $map[$p.Name] = Convert-Element $p.Value }; return $map }
            'Array' { $items = @($Element.EnumerateArray() | ForEach-Object { Convert-Element $_ }); return ,$items }
            'String' { return $Element.GetString() }
            'Number' { return ($Element.GetRawText() | ConvertFrom-Json) }
            'True' { return $true }
            'False' { return $false }
            'Null' { return $null }
            default { throw 'Unsupported JSON token.' }
        }
    }
    $options = [System.Text.Json.JsonDocumentOptions]::new()
    $options.MaxDepth = 100
    $document = [System.Text.Json.JsonDocument]::Parse($Text,$options)
    try { Convert-Element $document.RootElement } finally { $document.Dispose() }
}
function Read-Json($Path) { ConvertFrom-SetupJson (Get-Content -LiteralPath $Path -Raw) }
function Copy-Data($Value) { ConvertFrom-SetupJson (ConvertTo-Json -InputObject $Value -Depth 100) }
function Write-Json($Path, $Value) {
    $directory = Split-Path ([IO.Path]::GetFullPath($Path))
    $null = New-Item -ItemType Directory -Path $directory -Force
    $temp = Join-Path $directory ([guid]::NewGuid().ToString() + '.tmp')
    try {
        ConvertTo-Json -InputObject $Value -Depth 100 | Set-Content -LiteralPath $temp -Encoding utf8NoBOM
        # Windows can briefly lock the target (antivirus/indexer); retry the local replace a few times.
        for ($attempt = 1; ; $attempt++) {
            try { [IO.File]::Move($temp, [IO.Path]::GetFullPath($Path), $true); break }
            catch [UnauthorizedAccessException], [IO.IOException] { if ($attempt -ge 10) { throw }; Start-Sleep -Milliseconds 200 }
        }
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp } }
}
function Get-PackageFileHashes {
    $root = Split-Path $PSScriptRoot
    $hashes = @{}
    foreach ($file in (Get-ChildItem -LiteralPath $root -Recurse -File)) {
        $hashes[(ConvertTo-PackagePath ([IO.Path]::GetRelativePath($root,$file.FullName)))] = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $hashes
}
function Get-PackageHash { Get-Digest (Get-PackageFileHashes) }
function Get-PackageChangeSummary($Recorded) {
    $current = Get-PackageFileHashes
    $added = @($current.Keys | Where-Object { !$Recorded.Contains($_) } | Sort-Object)
    $removed = @($Recorded.Keys | Where-Object { !$current.Contains($_) } | Sort-Object)
    $changed = @($current.Keys | Where-Object { $Recorded.Contains($_) -and $Recorded[$_] -cne $current[$_] } | Sort-Object)
    $parts = @()
    foreach ($entry in @(@('added',$added),@('removed',$removed),@('changed',$changed))) {
        if ($entry[1].Count) {
            $shown = @($entry[1] | Select-Object -First 5) -join ', '
            $parts += "$($entry[0]): $shown$(if ($entry[1].Count -gt 5) { " (+$($entry[1].Count - 5) more)" })"
        }
    }
    return $parts -join '; '
}
function ConvertTo-PackagePath([string]$Path) { return $Path.Replace('\','/') }
function Start-Phase([string]$Name) {
    @{ phase = $Name; startedUtc = [DateTimeOffset]::UtcNow.ToString('o'); tick = [Diagnostics.Stopwatch]::GetTimestamp() }
}
function Stop-Phase($Clock) {
    @{ phase = $Clock.phase; startedUtc = $Clock.startedUtc; endedUtc = [DateTimeOffset]::UtcNow.ToString('o')
        elapsedMs = [Math]::Round(([Diagnostics.Stopwatch]::GetTimestamp() - $Clock.tick) * 1000.0 / [Diagnostics.Stopwatch]::Frequency,3) }
}
function Add-AttemptTiming($Attempt,$Timing) {
    $Attempt.receipt.timings += $Timing
    Write-Json $Attempt.path $Attempt.receipt
}

function ConvertTo-Semantic {
    param($Value, [string]$Path = '', [string]$ResourceId = '')
    if ($Value -is [Collections.IDictionary]) {
        if (!$Path -and $Value.Contains('id')) { $ResourceId = $Value.id }
        $result = @{}
        foreach ($key in $Value.Keys) {
            $network = $ResourceId -match '/Microsoft.Network/'
            $subnet = $ResourceId -match '/subnets/[^/]+$' -or $Path -match '^properties\.subnets\[\]\.properties$'
            $volatile = ($key -eq 'etag' -and ($Path -eq '' -or ($network -and $Path -match '(subnets|delegations|securityRules|defaultSecurityRules|routes|serviceEndpoints|virtualNetworkPeerings)\[\]$'))) -or
                ($Path -match '(^|\.)properties$' -and $key -eq 'provisioningState')
            if ($Path -eq '' -and $key -eq 'systemData') { $volatile = $true }
            if ($Path -eq 'properties' -and $key -eq 'privateEndpointConnections') { $volatile = $true }
            if ($network -and $subnet -and $Path -match 'properties$' -and $key -in @('serviceAssociationLinks','ipConfigurations','privateEndpoints','purpose')) { $volatile = $true }
            if ($ResourceId -match '/Microsoft.Network/privateDnsZones/[^/]+$' -and $Path -eq 'properties' -and
                $key -in @('numberOfRecordSets','numberOfVirtualNetworkLinks','numberOfVirtualNetworkLinksWithRegistration')) { $volatile = $true }
            if ($ResourceId -match '/Microsoft.(Insights|OperationalInsights)/' -and $Path -eq 'properties' -and
                $key -in @('PrivateLinkScopedResources','privateLinkScopedResources','scopedResources')) { $volatile = $true }
            if ($ResourceId -match '/Microsoft.CognitiveServices/accounts/[^/]+$' -and $Path -eq 'properties' -and
                $key -in @('armFeatures','callRateLimit','capabilities')) { $volatile = $true }
            if (!$volatile) { $result[$key] = ConvertTo-Semantic $Value[$key] $(if ($Path) { "$Path.$key" } else { $key }) $ResourceId }
        }
        return $result
    }
    if ($Value -is [array]) {
        $items = @($Value | ForEach-Object { ConvertTo-Semantic $_ "$Path[]" $ResourceId })
        if ($ResourceId -match '/Microsoft.Network/' -and $Path -match '(^|\.)(subnets|delegations|securityRules|defaultSecurityRules|routes|virtualNetworkPeerings|serviceEndpoints)$') {
            $items = @($items | Sort-Object { Get-Digest $_ })
        } elseif ($ResourceId -match '/Microsoft.Network/' -and $Path -match '(^|\.)(addressPrefixes|sourceAddressPrefixes|destinationAddressPrefixes|sourcePortRanges|destinationPortRanges|groupIds)$') {
            $items = @($items | Sort-Object)
        } elseif ($ResourceId -match '/Microsoft.(CognitiveServices/accounts|Storage/storageAccounts)/' -and $Path -match '^properties\.networkAcls\.(ipRules|virtualNetworkRules)$') {
            $items = @($items | Sort-Object { Get-Digest $_ })
        }
        return ,$items
    }
    return $Value
}

function Get-SemanticDiff {
    param($Before, $After, [string]$Path = '$')
    if ((Get-Digest $Before) -eq (Get-Digest $After)) { return }
    if ($Before -is [Collections.IDictionary] -and $After -is [Collections.IDictionary]) {
        foreach ($key in (@($Before.Keys)+@($After.Keys) | Sort-Object -Unique)) {
            if (!$Before.Contains($key) -or !$After.Contains($key)) {
                @{ path = "$Path.$key"; before = $Before[$key]; after = $After[$key] }
            } else { Get-SemanticDiff $Before[$key] $After[$key] "$Path.$key" }
        }
    } else { @{ path = $Path; before = $Before; after = $After } }
}

function New-Approval {
    param([string]$Kind, $Config, $Request, $Before)
    $plan = @{ kind = $Kind; operationId = [guid]::NewGuid().ToString('N'); config = $Config
        configHash = (Get-Digest $Config); packageHash = (Get-PackageHash); request = $Request; before = $Before
        createdAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        expiresAt = [DateTimeOffset]::UtcNow.AddHours(2).ToUnixTimeMilliseconds() }
    return $plan
}
function Seal-Approval($Plan) {
    $Plan.approvalHash = Get-Digest $Plan
    return $Plan
}
function Assert-Approval($Plan, [string]$Hash) {
    $copy = @{}
    foreach ($key in $Plan.Keys) { if ($key -ne 'approvalHash') { $copy[$key] = $Plan[$key] } }
    if (!$Hash -or $Hash -cne $Plan.approvalHash -or (Get-Digest $copy) -cne $Hash) { throw 'Exact reviewed hash required; changed/blanket approval rejected.' }
    if ($Plan.packageHash -ne (Get-PackageHash) -or $Plan.configHash -ne (Get-Digest $Plan.config)) { throw 'Package/config changed; prepare a new preview.' }
    if ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -gt $Plan.expiresAt) { throw 'Approval expired; inspect and preview again.' }
}
function New-Attempt($Plan, [string]$Directory) {
    $path = Join-Path $Directory "$($Plan.operationId).attempt.json"
    if (Test-Path -LiteralPath $path) { throw 'Attempt already exists; reconcile it, never replay the write.' }
    $receipt = @{ operationId = $Plan.operationId; approvalHash = $Plan.approvalHash; kind = $Plan.kind; timings = @()
        requestHash = (Get-Digest $Plan.request); state = 'NotSubmitted'; confirmed = $false }
    Write-Json $path $receipt
    return @{ path = $path; receipt = $receipt }
}
function Mark-Attempt($Attempt, [string]$State, [string]$Reason = '') {
    $Attempt.receipt.state = $State
    $Attempt.receipt.reason = $Reason
    if ($State -eq 'SubmissionAttempted') { $Attempt.receipt.submissionStartedAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() }
    Write-Json $Attempt.path $Attempt.receipt
}
function Test-Submitted($Attempt) { $Attempt.receipt.Contains('submissionStartedAt') }
function Invoke-AttemptWrite($Attempt,[scriptblock]$Body) {
    $clock = Start-Phase 'SubmissionApply'
    try { & $Body }
    catch {
        Mark-Attempt $Attempt $(if (Test-Submitted $Attempt) { 'OutcomeUnknown' } else { 'NotSubmitted' }) $_.Exception.Message
        throw
    } finally { Add-AttemptTiming $Attempt (Stop-Phase $clock) }
}
function Read-Attempt($Plan,[string]$Directory) {
    $path = Join-Path $Directory "$($Plan.operationId).attempt.json"
    $receipt = Read-Json $path
    $copy = Copy-Data $Plan; $copy.Remove('approvalHash')
    if ($receipt.operationId -cne $Plan.operationId -or $receipt.kind -cne $Plan.kind -or
        $receipt.approvalHash -cne $Plan.approvalHash -or (Get-Digest $copy) -cne $Plan.approvalHash -or
        $receipt.requestHash -cne (Get-Digest $Plan.request) -or $Plan.configHash -cne (Get-Digest $Plan.config)) {
        throw 'Receipt/approval/config/request binding mismatch.'
    }
    return @{ path = $path; receipt = $receipt }
}
function Confirm-Attempt($Attempt, $Result, [string]$VerifiedPath) {
    $Attempt.receipt.state = if ($Result.state -in @('Failed','Canceled','Rejected')) { 'Failed' } else { 'Succeeded' }
    $Attempt.receipt.confirmed = $true
    $Attempt.receipt.result = $Result
    Write-Json $Attempt.path $Attempt.receipt
    # Never replace last verified evidence on prewrite drift or unknown outcome.
    if ($Result.state -notin @('Failed','Canceled','Rejected')) {
        Write-Json $VerifiedPath @{ operationId = $Attempt.receipt.operationId; result = $Result; verifiedAt = [DateTimeOffset]::UtcNow.ToString('o') }
    }
}
function Assert-NoDrift($Plan, $Current, $Attempt) {
    $diff = @(Get-SemanticDiff $Plan.before $Current)
    if ($diff.Count) {
        $Attempt.receipt.diff = $diff
        Mark-Attempt $Attempt 'NotSubmitted' 'Meaningful state changed; inspect the visible policy/settings diff and prepare a fresh scoped preview.'
        throw 'Prewrite drift: NotSubmitted. No write was attempted; a fresh preview may assess compatible current state.'
    }
}
function Test-Subset($Desired, $Actual) {
    if ($Desired -is [Collections.IDictionary]) {
        if ($Actual -isnot [Collections.IDictionary]) { return $false }
        foreach ($key in $Desired.Keys) { if (!$Actual.Contains($key) -or !(Test-Subset $Desired[$key] $Actual[$key])) { return $false } }
        return $true
    }
    if ($Desired -is [array]) { return (Get-Digest (ConvertTo-Semantic $Desired)) -eq (Get-Digest (ConvertTo-Semantic $Actual)) }
    return $Desired -ieq $Actual
}
