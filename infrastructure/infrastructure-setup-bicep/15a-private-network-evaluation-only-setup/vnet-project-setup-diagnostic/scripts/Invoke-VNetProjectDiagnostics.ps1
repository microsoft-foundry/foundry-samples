#requires -Version 7.2
[CmdletBinding()]
param(
    [string]$ProjectResourceId,
    [string]$SubscriptionId,
    [string]$ResourceGroup,
    [string]$AccountName,
    [string]$ProjectName,
    [ValidateSet('Core','Models','Graders','Traces','Agent','Scheduled','Continuous')]
    [string[]]$Profiles = @('Core'),
    [ValidateSet('Configuration','ConfigurationAndNetwork')][string]$Mode = 'Configuration',
    [switch]$AdvancedNetworkDetails,
    [string]$EvaluationCallerObjectId,
    [string]$StorageConnectionName,
    [string]$ModelConnectionName,
    [string]$ModelDeploymentName,
    [string]$MonitoringConnectionName,
    [ValidateSet('Auto','ApiKey','Entra')][string]$ModelAuthentication = 'Auto',
    [switch]$PrivilegedTraceContent,
    [string]$OutputDirectory = (Join-Path (Get-Location) 'vnet-project-diagnostic-report'),
    [ValidateSet('AzureCli','AzurePowerShell')][string]$AuthenticationProvider = 'AzureCli',
    [string]$AzureCliExecutable = 'az',
    [string[]]$AzureCliPrefixArguments = @(),
    [ValidateRange(5,120)][int]$RequestTimeoutSeconds = 25,
    [string]$FixturePath
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ArmReader.ps1')
. (Join-Path $PSScriptRoot 'Checks.ps1')
. (Join-Path $PSScriptRoot 'NetworkChecks.ps1')
. (Join-Path $PSScriptRoot 'Scenarios.ps1')

$context = $null
$stage = 'Input'
try {
    if ($ProjectResourceId -and ($SubscriptionId -or $ResourceGroup -or $AccountName -or $ProjectName)) {
        throw 'Use either a project ARM ID or explicit subscription/resource group/account/project parameters, not both.'
    }
    if (!$ProjectResourceId) {
        if (!$SubscriptionId -or !$ResourceGroup -or !$AccountName -or !$ProjectName) { throw 'A project ARM ID or all four resource parameters is required.' }
        $ProjectResourceId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName/projects/$ProjectName"
    }
    $ProjectResourceId = Assert-ArmId $ProjectResourceId -Project
    if ($EvaluationCallerObjectId -and ![guid]::TryParse($EvaluationCallerObjectId, [ref]([guid]::Empty))) { throw 'Caller object ID must be a GUID.' }
    if ($FixturePath -and $Mode -ne 'Configuration') { throw 'Offline fixtures support Configuration only.' }
    if ($AdvancedNetworkDetails -and $Mode -ne 'ConfigurationAndNetwork') { throw 'AdvancedNetworkDetails requires ConfigurationAndNetwork.' }
    if (!$FixturePath -and $AuthenticationProvider -eq 'AzurePowerShell' -and
        ($PSBoundParameters.ContainsKey('AzureCliExecutable') -or $PSBoundParameters.ContainsKey('AzureCliPrefixArguments'))) {
        throw 'CLI override parameters do not apply to AzurePowerShell.'
    }
    if ($PrivilegedTraceContent -and 'Traces' -notin $Profiles) { throw 'PrivilegedTraceContent requires the Traces profile.' }
    $Profiles = @(@('Core') + $Profiles | Sort-Object -Unique)
    $stage = 'Bootstrap'
    $context = New-DiagnosticContext $FixturePath $AzureCliExecutable $AzureCliPrefixArguments $RequestTimeoutSeconds `
        -AuthenticationProvider $AuthenticationProvider -SubscriptionId ($ProjectResourceId.Split('/')[2])
    $catalog = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\references\requirements.json') -Raw | ConvertFrom-Json -AsHashtable
    $options = @{
        ProjectId = $ProjectResourceId; Profiles = $Profiles; Caller = $EvaluationCallerObjectId
        StorageConnection = $StorageConnectionName; ModelConnection = $ModelConnectionName
        ModelDeployment = $ModelDeploymentName; MonitoringConnection = $MonitoringConnectionName
        ModelAuthentication = $ModelAuthentication; PrivilegedTraceContent = [bool]$PrivilegedTraceContent
    }
    $stage = 'Assessment'
    Invoke-ConfigurationAssessment $context $options $catalog
    if ($Mode -eq 'ConfigurationAndNetwork') { Test-LocalNetwork $context -AdvancedNetworkDetails:$AdvancedNetworkDetails }
    $outcome = Get-Outcome $context.Checks
    $report = [ordered]@{
        schemaVersion = 2; assessmentTime = [DateTimeOffset]::UtcNow.ToString('o')
        projectResourceId = $ProjectResourceId; profiles = $Profiles; mode = $Mode
        fixture = $context.Offline; tenantId = $context.TenantId; advancedNetworkDetails = [bool]$AdvancedNetworkDetails
        authenticationProvider = $(if ($context.Offline) {'OfflineFixture'} else {$AuthenticationProvider})
        summary = $outcome; hostContext = $context.HostContext
        statement = 'No evaluation, inference, agent call, setup-validation API, or data-plane authorization probe was made. No Azure state was changed. Passed means selected implemented configuration/connectivity checks only; coverage is reported separately. No effective-access, whole-VNet health, or evaluation verification is claimed.'
        checks = @($context.Checks.ToArray())
    }
    $stage = 'Report'
    $null = New-Item -ItemType Directory -Path $OutputDirectory -Force
    $jsonPath = Join-Path $OutputDirectory 'diagnostics.json'
    $textPath = Join-Path $OutputDirectory 'diagnostics.md'
    $report | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $jsonPath -Encoding utf8
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add("# Foundry VNet setup: $($outcome.status)")
    $lines.Add('')
    $lines.Add($report.statement)
    $lines.Add("Fixture: $($report.fixture). Profiles: $($Profiles -join ', '). Mode: $Mode.")
    $lines.Add("Findings: $($outcome.findingCount); passed: $($outcome.passedFindingCount); inventory: $($outcome.inventoryCount).")
    $lines.Add("Coverage: $($outcome.coverageStatus); not assessed: $($outcome.notAssessed -join ', ').")
    $lines.Add('')
    $lines.Add('## Actionable summary')
    if (!$outcome.actionableGroups.Count) { $lines.Add('No actionable findings in selected implemented checks. See coverage limits below.') }
    foreach ($group in $outcome.actionableGroups) {
        $lines.Add("- $($group.status): $($group.id) ($($group.count)); required=$($group.required). Resources: $($group.resources -join ', ')")
    }
    foreach ($classification in @('Finding','Coverage','Inventory')) {
        $lines.Add('')
        $lines.Add("## $classification details")
        foreach ($check in @($context.Checks | Where-Object { $_.classification -eq $classification })) {
        $lines.Add('')
        $lines.Add("### $($check.id) - $($check.status)")
        $lines.Add("Resource: $($check.resource)")
        $lines.Add("Principal: $($check.principal). Required: $($check.required). Evidence: $($check.evidenceKind).")
        $lines.Add("Expected: $($check.expected)")
        $lines.Add('```json')
        $lines.Add(($check.observed | ConvertTo-Json -Depth 40))
        $lines.Add('```')
        $lines.Add("Limitations: $($check.limitations -join ' ')")
        $lines.Add("Remediation: $($check.remediation)")
        }
    }
    $lines | Set-Content -LiteralPath $textPath -Encoding utf8
    Write-Output "$($outcome.status); findings=$($outcome.findingCount); passed=$($outcome.passedFindingCount); exit=$($outcome.exitCode). No evaluation was run."
    Write-Output "Coverage: $($outcome.coverageStatus); not assessed: $($outcome.notAssessed -join ', '). Inventory=$($outcome.inventoryCount)."
    if ($outcome.actionableGroups.Count) {
        Write-Output ("Actionable: " + (($outcome.actionableGroups | ForEach-Object { "$($_.status) $($_.id) x$($_.count)" }) -join '; '))
    }
    Write-Output "JSON: $([IO.Path]::GetFullPath($jsonPath))"
    Write-Output "Report: $([IO.Path]::GetFullPath($textPath))"
    exit $outcome.exitCode
}
catch {
    # Never echo exception text: CLI/resource errors can contain credentials or URLs.
    $errorType = $_.Exception.GetType().Name
    $errorLine = $_.InvocationInfo.ScriptLineNumber
    $errorFile = [IO.Path]::GetFileName($_.InvocationInfo.ScriptName)
    $prerequisite = $_.Exception.Data['DiagnosticPrerequisite']
    Write-Output "Diagnostic stopped during $stage; exit=3; type=$errorType; source=${errorFile}:$errorLine. Check input, selected authentication provider prerequisites, metadata schema, and local output access. No evaluation was run."
    if ($prerequisite) { Write-Output "Prerequisite: $prerequisite" }
    exit 3
}
finally {
    Close-DiagnosticContext $context
}
