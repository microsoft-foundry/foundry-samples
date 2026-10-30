#Requires -Version 7.2
[CmdletBinding()]
param([ValidateSet('Preview','Apply','Reconcile')][string]$Action,[string]$ConfigPath,
    [ValidateSet('Account','Storage','Insights','Workspace')][string]$Target,
    [string]$PlanPath,[string]$ApprovalHash,[string]$ReceiptDirectory,[string]$OutputPath)
. (Join-Path $PSScriptRoot 'Inspection.ps1')

function New-GrantPreview($Config,[string]$Target) {
    Assert-SetupContext $Config
    $ids = Get-SetupIds $Config
    $foundry = Get-FoundryState $Config
    $project = Get-SetupResource $ids.Project
    $role = switch ($Target) { 'Account' { '53ca6127-db72-4b80-b1b0-d745d6d5456d' }
        'Storage' { 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' } default { '73c42c96-874c-492b-b04d-ab87d138a893' } }
    $scope = switch ($Target) {
        'Account' { $ids.Account }; 'Storage' { $ids.Storage }; 'Insights' { $ids.Insights }
        'Workspace' { if (!$ids.Insights) { throw 'Monitoring was not requested.' }; (Get-SetupResource $ids.Insights).properties.WorkspaceResourceId }
    }
    if (!$scope) { throw 'Monitoring was not requested.' }
    $null = Get-SetupResource $scope
    $definitionId = "/subscriptions/$($scope.Split('/')[2])/providers/Microsoft.Authorization/roleDefinitions/$role"
    $name = (Get-Digest @{ scope = $scope.ToLowerInvariant(); role = $role; principal = $project.identity.principalId }).Substring(0,32)
    $name = [guid]::ParseExact($name,'N').ToString()
    $assignments = Get-CollectionMetadata "$scope/providers/Microsoft.Authorization/roleAssignments"
    $matches = @($assignments | Where-Object { $_.properties.scope -ieq $scope -and
        $_.properties.principalId -ieq $project.identity.principalId -and $_.properties.roleDefinitionId -ieq $definitionId -and
        !($_.properties.Contains('condition') -and $_.properties.condition) })
    $id = if ($matches.Count) { $matches[0].id } else { "$scope/providers/Microsoft.Authorization/roleAssignments/$name" }
    if (!$matches.Count -and (Get-SetupResource $id -Optional)) { throw 'Assignment name is already occupied; never overwrite it.' }
    $body = @{ properties = @{ principalId = $project.identity.principalId; principalType = 'ServicePrincipal'; roleDefinitionId = $definitionId } }
    $request = @{ resourceId = $id; body = $body; scope = $scope; method = $(if ($matches.Count) { 'None' } else { 'PUT' }) }
    Seal-Approval (New-Approval 'Grant' $Config $request @{ foundry = $foundry; assignments = $assignments })
}
function Submit-Grant($Plan,[string]$Hash,[string]$Directory) {
    Assert-Approval $Plan $Hash; Assert-SetupContext $Plan.config
    $attempt = New-Attempt $Plan $Directory
    $current = @{ foundry = (Get-FoundryState $Plan.config)
        assignments = (Get-CollectionMetadata "$($Plan.request.scope)/providers/Microsoft.Authorization/roleAssignments") }
    Assert-NoDrift $Plan $current $attempt
    if ($Plan.request.method -eq 'None') {
        Confirm-Attempt $attempt @{ state = 'ObservedConfigured'; assignmentId = $Plan.request.resourceId; effectiveAccess = 'NotAssessed' } (Join-Path $Directory "verified-$($Plan.operationId).json")
        return $attempt.receipt
    }
    try {
        $response = Invoke-AttemptWrite $attempt { Invoke-SetupArm PUT $Plan.request.resourceId $Plan.request.body -OnStart { Mark-Attempt $attempt 'SubmissionAttempted' } }
        if ($response.Code -ne 200) { Mark-Attempt $attempt 'OutcomeUnknown' 'Reconcile this exact assignment; do not replay a grant batch.'; return $attempt.receipt }
        $actual = Wait-SetupResource $Plan.request.resourceId 300 -AllowMissingState
        if (!(Test-Subset $Plan.request.body $actual)) { throw 'Assignment readback mismatch.' }
        Confirm-Attempt $attempt @{ state = 'ObservedConfigured'; assignmentId = $actual.id; effectiveAccess = 'NotAssessed' } (Join-Path $Directory "verified-$($Plan.operationId).json")
    } catch { Mark-Attempt $attempt $(if (Test-Submitted $attempt) { 'OutcomeUnknown' } else { 'NotSubmitted' }) $_.Exception.Message; throw }
    return $attempt.receipt
}
function Reconcile-Grant($Plan,[string]$Directory) {
    $attempt = Read-Attempt $Plan $Directory
    if ($attempt.receipt.state -in @('NotSubmitted','Succeeded','Failed')) { return $attempt.receipt }
    $actual = Get-SetupResource $Plan.request.resourceId -Optional
    if ($actual -and (Test-Subset $Plan.request.body $actual)) {
        Confirm-Attempt $attempt @{ state = 'ObservedConfigured'; assignmentId = $actual.id; effectiveAccess = 'NotAssessed' } (Join-Path $Directory "verified-$($Plan.operationId).json")
    } else { Mark-Attempt $attempt 'OutcomeUnknown' 'Exact assignment not verified; no PUT was retried.' }
    return $attempt.receipt
}
if ($Action) {
    if ($Action -eq 'Preview') { Write-Json $OutputPath (New-GrantPreview (Read-SetupConfig $ConfigPath) $Target) }
    else {
        $plan = Read-Json $PlanPath
        if ($plan.kind -ne 'Grant') { throw 'Grant plan required.' }
        if ($Action -eq 'Apply') { Submit-Grant $plan $ApprovalHash $ReceiptDirectory } else { Reconcile-Grant $plan $ReceiptDirectory }
    }
}
