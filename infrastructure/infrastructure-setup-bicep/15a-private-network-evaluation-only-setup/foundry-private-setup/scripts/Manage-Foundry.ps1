#Requires -Version 7.2
[CmdletBinding()]
param([ValidateSet('Inspect','Preview','Apply','Reconcile')][string]$Action,
    [ValidateSet('Injection','AccountHost','ProjectHost')][string]$Operation,
    [string]$ConfigPath,[string]$PlanPath,[string]$ApprovalHash,[string]$ReceiptDirectory,[string]$OutputPath,
    [switch]$AcknowledgeAccountWideImpact)
. (Join-Path $PSScriptRoot 'Inspection.ps1')

function Get-HostState($Config) {
    $ids = Get-SetupIds $Config
    $network = Get-CurrentState @($ids.Storage,$ids.Vnet,$ids.AgentSubnet,$ids.PeSubnet)
    Assert-ObservedDependencies $Config $network
    foreach ($id in @($ids.Storage,$ids.Vnet,$ids.AgentSubnet,$ids.PeSubnet)) {
        if ($network.resources[$id] -eq 'Absent') { throw 'Injection/host dependencies must exist first.' }
    }
    $hosts = @{}
    foreach ($parent in @($ids.Account,$ids.Project)) {
        $subnet = if ($parent -ieq $ids.Account) { $ids.AgentSubnet } else { '' }
        $hostResource = Get-Host $parent $subnet
        if ($hostResource -and $Config.foundryAccount.mode -eq 'existing' -and $hostResource.properties.provisioningState -ne 'Succeeded') {
            throw 'Pending existing hosts require read-only investigation; no migration/overwrite.'
        }
        $hosts[$parent] = if ($hostResource) { ConvertTo-Semantic $hostResource } else { 'Absent' }
    }
    @{ foundry = (Get-FoundryState $Config); hosts = $hosts
        network = $network }
}
function New-FoundryPreview($Config,[string]$Operation) {
    if ($Operation -eq 'ProjectHost' -and $Config.workload.projectHost -ne 'requested') { throw 'Project host creation must be explicitly requested; never infer it from non-trace/trace alone.' }
    Assert-SetupContext $Config
    $ids = Get-SetupIds $Config
    $before = Get-HostState $Config
    $account = Get-SetupResource $ids.Account
    $patch = Get-Injection $account $ids.AgentSubnet
    if ($Operation -eq 'Injection') {
        $request = @{ resourceId = $ids.Account; method = $(if ($patch) { 'PATCH' } else { 'None' }); body = $patch
            impact = 'Account-wide network change affecting the exact single project; public access/auth/models remain unchanged.'
            projects = @($ids.Project) }
    } else {
        if ($patch) { throw 'Exact account network injection must be configured first; no implicit PATCH.' }
        if ($Operation -eq 'ProjectHost') {
            $accountHost = Get-Host $ids.Account $ids.AgentSubnet
            if (!$accountHost -or $accountHost.properties.provisioningState -ne 'Succeeded') { throw 'Matching account host readiness is required.' }
        }
        $parent = if ($Operation -eq 'AccountHost') { $ids.Account } else { $ids.Project }
        $subnet = if ($Operation -eq 'AccountHost') { $ids.AgentSubnet } else { '' }
        $hostResource = Get-Host $parent $subnet
        $properties = @{ capabilityHostKind = 'Agents' }
        if ($subnet) { $properties.customerSubnet = $subnet }
        $request = @{ parent = $parent; subnet = $subnet; resourceId = "$parent/capabilityHosts/agents"
            method = $(if ($hostResource) { 'None' } else { 'PUT' }); body = @{ properties = $properties } }
    }
    Seal-Approval (New-Approval $Operation $Config $request $before)
}
function Assert-FoundryUnchanged($Before,$After,[switch]$AllowInjection) {
    $a = Copy-Data $Before
    $b = Copy-Data $After
    if ($AllowInjection) {
        foreach ($id in @($a.resources.Keys)) {
            if ($id -match '/accounts/[^/]+$') {
                $a.resources[$id].properties.Remove('networkInjections')
                $b.resources[$id].properties.Remove('networkInjections')
            }
        }
    }
    if ((Get-Digest $a) -ne (Get-Digest $b)) { throw 'Meaningful Foundry identity/settings/model/connection preservation mismatch.' }
}
function Read-HostReady($Request,[int]$TimeoutSeconds = 900) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        $hostResource = Get-Host $Request.parent $Request.subnet
        if ($hostResource -and $hostResource.properties.provisioningState -eq 'Succeeded') { return $hostResource }
        if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) { throw 'Host readiness incomplete; a write may still complete. Do not repeat PUT.' }
        Start-Sleep -Seconds 10
    } while ($true)
}
function Submit-Foundry($Plan,[string]$Hash,[string]$Directory,[switch]$AcknowledgeAccountWideImpact,[int]$TimeoutSeconds = 900) {
    Assert-Approval $Plan $Hash
    Assert-SetupContext $Plan.config
    if ($Plan.kind -eq 'Injection' -and $Plan.request.method -eq 'PATCH' -and !$AcknowledgeAccountWideImpact) {
        throw 'Explicit account-wide acknowledgment is required in addition to the exact scope hash.'
    }
    $attempt = New-Attempt $Plan $Directory
    Assert-NoDrift $Plan (Get-HostState $Plan.config) $attempt
    try {
        if ($Plan.request.method -ne 'None') {
            $response = Invoke-AttemptWrite $attempt { Invoke-SetupArm $Plan.request.method $Plan.request.resourceId $Plan.request.body -OnStart { Mark-Attempt $attempt 'SubmissionAttempted' } }
            if ($response.Code -notin @(200,409)) {
                Mark-Attempt $attempt 'OutcomeUnknown' 'Write outcome unknown; reconcile this exact attempt, never replay.'
                return $attempt.receipt
            }
            if ($response.Code -eq 409 -and $Plan.kind -eq 'Injection') { throw 'PATCH conflict; inspect before another approval.' }
        }
        $statusClock = Start-Phase 'ResourceStatusVerification'
        $ids = Get-SetupIds $Plan.config
        if ($Plan.kind -eq 'Injection') {
            if (Test-Submitted $attempt) { $null = Wait-SetupResource $ids.Account $TimeoutSeconds }
            $account = Get-SetupResource $ids.Account
            if (Get-Injection $account $ids.AgentSubnet) { throw 'Injection readback mismatch.' }
            $after = Get-HostState $Plan.config
            if ((Test-Submitted $attempt) -and (Get-Digest $account.properties.networkInjections) -ne (Get-Digest $Plan.request.body.properties.networkInjections)) {
                throw 'Unrelated injection settings changed during PATCH.'
            }
            Assert-FoundryUnchanged $Plan.before.foundry $after.foundry -AllowInjection
            $result = @{ state = 'ObservedConfigured'; resourceId = $ids.Account; publicAccessChange = 'None'
                accountHostAppeared = ($Plan.before.hosts[$ids.Account] -eq 'Absent' -and $after.hosts[$ids.Account] -ne 'Absent')
                route = 'NotVerified' }
        } else {
            $hostResource = Read-HostReady $Plan.request $TimeoutSeconds
            Assert-FoundryUnchanged $Plan.before.foundry (Get-FoundryState $Plan.config)
            $result = @{ state = 'ObservedConfigured'; resourceId = $hostResource.id
                mechanism = $(if (Test-Submitted $attempt) { 'ExplicitRequestOrConflictReconciled' } else { 'Existing' })
                provisioningState = 'Succeeded'; route = 'NotVerified'; backingRoutingMetadata = 'NotObserved' }
        }
        Add-AttemptTiming $attempt (Stop-Phase $statusClock)
        Confirm-Attempt $attempt $result (Join-Path $Directory "last-verified-$($Plan.kind).json")
    } catch {
        Mark-Attempt $attempt $(if (Test-Submitted $attempt) { 'OutcomeUnknown' } else { 'NotSubmitted' }) $_.Exception.Message
        throw
    }
    return $attempt.receipt
}
function Reconcile-Foundry($Plan,[string]$Directory) {
    $attempt = Read-Attempt $Plan $Directory
    if ($attempt.receipt.state -in @('NotSubmitted','Succeeded','Failed')) { return $attempt.receipt }
    $ids = Get-SetupIds $Plan.config
    if ($Plan.kind -eq 'Injection') {
        $account = Get-SetupResource $ids.Account
        if (Get-Injection $account $ids.AgentSubnet) {
            Mark-Attempt $attempt 'OutcomeUnknown' 'Matching injection not observed; no PATCH repeated.'
            return $attempt.receipt
        }
        Assert-FoundryUnchanged $Plan.before.foundry (Get-FoundryState $Plan.config) -AllowInjection
        $id = $ids.Account
    } else {
        $hostResource = Get-Host $Plan.request.parent $Plan.request.subnet
        if (!$hostResource -or $hostResource.properties.provisioningState -ne 'Succeeded') {
            Mark-Attempt $attempt 'OutcomeUnknown' 'Matching host not yet Succeeded; no PUT repeated.'
            return $attempt.receipt
        }
        Assert-FoundryUnchanged $Plan.before.foundry (Get-FoundryState $Plan.config)
        $id = $hostResource.id
    }
    Confirm-Attempt $attempt @{ state = 'ObservedConfigured'; resourceId = $id; route = 'NotVerified'; attribution = 'Observed matching state, not a repeated request.' } (Join-Path $Directory "last-verified-$($Plan.kind).json")
    return $attempt.receipt
}
if ($Action) {
    if ($Action -eq 'Inspect') {
        $config = Read-SetupConfig $ConfigPath; Assert-SetupContext $config
        Write-Json $OutputPath (Get-HostState $config)
    } elseif ($Action -eq 'Preview') { Write-Json $OutputPath (New-FoundryPreview (Read-SetupConfig $ConfigPath) $Operation) }
    else {
        $plan = Read-Json $PlanPath
        if ($plan.kind -notin @('Injection','AccountHost','ProjectHost')) { throw 'Wrong operation helper.' }
        if ($Action -eq 'Apply') { Submit-Foundry $plan $ApprovalHash $ReceiptDirectory -AcknowledgeAccountWideImpact:$AcknowledgeAccountWideImpact }
        else { Reconcile-Foundry $plan $ReceiptDirectory }
    }
}
