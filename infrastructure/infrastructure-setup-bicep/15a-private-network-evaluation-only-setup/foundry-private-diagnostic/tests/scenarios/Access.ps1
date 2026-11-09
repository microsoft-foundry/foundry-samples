# Scenarios for Access (RBAC) checks.

# Scenario files run in a child scope; helpers are global so Mutate blocks can call them later.
function global:Get-AccessScenarioRaPath { param([string]$Scope) "$Scope/providers/Microsoft.Authorization/roleAssignments" }

function global:Set-AccessScenarioRoles {
    param($E, [string]$Scope, [object[]]$Assignments)
    Set-EvRequest $E (Get-AccessScenarioRaPath $Scope) @($Assignments)
}

@(
    @{ Name = 'access-storage-no-role'; Mutate = { param($E) Set-AccessScenarioRoles $E (Get-TestIds).Storage @() }
       Expect = @{ 'access.projectStorage' = 'Problem:High' } }
    @{ Name = 'access-storage-reader-only'; Mutate = { param($E) $ids = Get-TestIds
            Set-AccessScenarioRoles $E $ids.Storage @((New-RoleAssignment $ids.Storage $ids.ProjectPrincipal '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' 'ra-st-read')) }
       Expect = @{ 'access.projectStorage' = 'Problem:Medium' } }
    @{ Name = 'access-storage-conditional'; Mutate = { param($E) @(Get-EvData $E (Get-AccessScenarioRaPath (Get-TestIds).Storage))[0].properties.conditionPresent = $true }
       Expect = @{ 'access.projectStorage' = 'Problem:Medium' } }
    @{ Name = 'access-storage-group-only'; Mutate = { param($E) $ids = Get-TestIds
            $ra = New-RoleAssignment $ids.Storage '44444444-4444-4444-4444-444444444444' 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' 'ra-st-group'; $ra.properties.principalType = 'Group'
            Set-AccessScenarioRoles $E $ids.Storage @($ra) }
       Expect = @{ 'access.projectStorage' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'access-storage-roles-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-AccessScenarioRaPath (Get-TestIds).Storage) 403 }
       Expect = @{ 'access.projectStorage' = 'CouldNotCheck:Blocking'; 'access.runnerReads' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'access-storage-roles-old-evidence'; Mutate = { param($E) Remove-EvRequest $E (Get-AccessScenarioRaPath (Get-TestIds).Storage) }
       Expect = @{ 'access.projectStorage' = 'CouldNotCheck:KnownLimit' } }

    @{ Name = 'access-trace-no-role'; Mutate = { param($E) Set-AccessScenarioRoles $E (Get-TestIds).AppInsights @() }
       Expect = @{ 'access.traceReader' = 'Problem:High' } }
    @{ Name = 'access-trace-workspace-permissions-required'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Workspace).properties.features.enableLogAccessUsingOnlyResourcePermissions = $false }
       Expect = @{ 'access.traceReader' = 'Problem:High' } }
    @{ Name = 'access-trace-on-workspace'; Mutate = { param($E) $ids = Get-TestIds
            Set-AccessScenarioRoles $E $ids.AppInsights @()
            Set-AccessScenarioRoles $E $ids.Workspace @((New-RoleAssignment $ids.Workspace $ids.ProjectPrincipal '73c42c96-874c-492b-b04d-ab87d138a893' 'ra-law'))
            (Get-EvData $E $ids.Workspace).properties.features.enableLogAccessUsingOnlyResourcePermissions = $false }
       Expect = @{ 'access.traceReader' = 'OK' } }
    @{ Name = 'access-trace-workspace-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Workspace 403 }
       Expect = @{ 'access.traceReader' = 'CouldNotCheck:Blocking'; 'access.runnerReads' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'access-trace-roles-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-AccessScenarioRaPath (Get-TestIds).AppInsights) 403 }
       Expect = @{ 'access.traceReader' = 'CouldNotCheck:Blocking'; 'access.runnerReads' = 'CouldNotCheck:Blocking' } }

    @{ Name = 'access-project-assets-no-role'; Mutate = { param($E) Set-AccessScenarioRoles $E (Get-TestIds).Project @() }
       Expect = @{ 'access.projectAssets' = 'Problem:High' } }
    @{ Name = 'access-project-assets-ok'; Mutate = { param($E) $ids = Get-TestIds
            Set-AccessScenarioRoles $E $ids.Project @((New-RoleAssignment $ids.Project $ids.ProjectPrincipal '53ca6127-db72-4b80-b1b0-d745d6d5456d' 'ra-proj')) }
       Expect = @{ 'access.projectAssets' = 'OK' } }

    @{ Name = 'access-caller-no-role-project'; Mutate = { param($E) $E.discovery.evaluationCaller = '55555555-5555-5555-5555-555555555555'
            Set-AccessScenarioRoles $E (Get-TestIds).Project @((New-RoleAssignment (Get-TestIds).Project (Get-TestIds).ProjectPrincipal '53ca6127-db72-4b80-b1b0-d745d6d5456d' 'ra-proj')) }
       Expect = @{ 'access.evaluationCaller' = 'Problem:High' } }
    @{ Name = 'access-caller-role-on-account'; Mutate = { param($E) $ids = Get-TestIds; $E.discovery.evaluationCaller = '55555555-5555-5555-5555-555555555555'
            Set-AccessScenarioRoles $E $ids.Account @((New-RoleAssignment $ids.Account '55555555-5555-5555-5555-555555555555' '53ca6127-db72-4b80-b1b0-d745d6d5456d' 'ra-caller')) }
       Expect = @{ 'access.evaluationCaller' = 'OK' } }
    @{ Name = 'access-caller-account-only-read'; Mutate = { param($E) $E.discovery.evaluationCaller = '55555555-5555-5555-5555-555555555555' }
       Expect = @{ 'access.evaluationCaller' = 'CouldNotCheck:KnownLimit' } }

    @{ Name = 'access-runner-denied'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Nsg 403 }
       Expect = @{ 'access.runnerReads' = 'CouldNotCheck:Blocking' } }
    # A managed machine's own VM is unreadable by design; runner.location reports it, not the read-access check.
    @{ Name = 'access-runner-vm-denied-ignored'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Vm 401 }
       Expect = @{ 'access.runnerReads' = 'OK' } }
)
