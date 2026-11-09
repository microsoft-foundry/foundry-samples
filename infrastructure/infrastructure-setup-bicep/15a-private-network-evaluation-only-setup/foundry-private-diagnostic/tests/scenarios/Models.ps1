# Scenarios for Models checks. The healthy baseline doesn't use the Models path, so each scenario turns it on.

# Scenario files run in a child scope; helpers are global so Mutate blocks can call them later.
# Adds a model connection (Microsoft Entra ID) to $Target, the account by default, and gives the project
# identity Azure AI User on it, so the Models path is healthy before each scenario's change.
function global:Enable-ModelScenarioPath {
    param($E, [string]$Target, [string]$AuthType = 'AAD', [switch]$NoRole)
    $ids = Get-TestIds
    if (!$Target) { $Target = $ids.Account }
    $E.discovery.paths.Models = @{ used = $true; reason = 'connection model-conn' }
    $E.discovery.connections = @($E.discovery.connections) + @([ordered]@{ name = 'model-conn'; category = 'AIServices'; resource = $Target; path = 'Models' })
    $E.discovery.dependencies = @($E.discovery.dependencies) + @([ordered]@{ kind = 'Model'; path = 'Models'; resource = $Target; connection = 'model-conn'; privateEndpoints = @(); hosts = @() })
    $connPath = "$($ids.Project)/connections"
    $props = @{ category = 'AIServices'; target = 'https://acct.services.ai.azure.com/'; metadata = @{ ResourceId = $Target } }
    if ($AuthType) { $props.authType = $AuthType }
    Set-EvRequest $E $connPath (@(Get-EvData $E $connPath) + @((New-ArmObject "$connPath/model-conn" $props)))
    if (!$NoRole) {
        $raPath = "$Target/providers/Microsoft.Authorization/roleAssignments"
        Set-EvRequest $E $raPath @((New-RoleAssignment $Target $ids.ProjectPrincipal '53ca6127-db72-4b80-b1b0-d745d6d5456d' 'ra-model'))
    }
}

function global:Get-ModelScenarioOtherAccount { "$((Get-TestIds).Sub)/resourceGroups/rg-models/providers/Microsoft.CognitiveServices/accounts/models" }

@(
    @{ Name = 'models-enabled-healthy'; Mutate = { param($E) Enable-ModelScenarioPath $E }
       Expect = @{ 'model.connection' = 'OK'; 'model.target' = 'OK'; 'model.deployment' = 'OK'; 'model.authentication' = 'OK'; 'access.modelIdentity' = 'OK' } }
    @{ Name = 'models-no-connection'; Mutate = { param($E) $E.discovery.paths.Models = @{ used = $true; reason = 'model dependency' } }
       Expect = @{ 'model.connection' = 'Problem:High' } }
    @{ Name = 'models-target-wrong-type'; Mutate = { param($E) Enable-ModelScenarioPath $E -Target (Get-TestIds).Storage -NoRole }
       Expect = @{ 'model.target' = 'Problem:High' } }
    @{ Name = 'models-target-not-found'; Mutate = { param($E) $t = Get-ModelScenarioOtherAccount; Enable-ModelScenarioPath $E -Target $t; Set-EvStatus $E $t 404; Set-EvStatus $E "$t/deployments" 404 }
       Expect = @{ 'model.target' = 'Problem:High' } }
    @{ Name = 'models-target-failed'; Mutate = { param($E) $t = Get-ModelScenarioOtherAccount; Enable-ModelScenarioPath $E -Target $t
            Set-EvRequest $E $t (New-ArmObject $t @{ provisioningState = 'Failed'; disableLocalAuth = $true })
            Set-EvRequest $E "$t/deployments" @((New-ArmObject "$t/deployments/gpt-4o" @{ provisioningState = 'Succeeded'; model = @{ name = 'gpt-4o' } })) }
       Expect = @{ 'model.target' = 'Problem:High' } }
    @{ Name = 'models-target-unreadable'; Mutate = { param($E) $t = Get-ModelScenarioOtherAccount; Enable-ModelScenarioPath $E -Target $t; Set-EvStatus $E $t 403
            Set-EvRequest $E "$t/deployments" @((New-ArmObject "$t/deployments/gpt-4o" @{ provisioningState = 'Succeeded'; model = @{ name = 'gpt-4o' } })) }
       Expect = @{ 'model.target' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'models-no-deployments'; Mutate = { param($E) Enable-ModelScenarioPath $E; Set-EvRequest $E "$((Get-TestIds).Account)/deployments" @() }
       Expect = @{ 'model.deployment' = 'Problem:High' } }
    @{ Name = 'models-deployment-failed'; Mutate = { param($E) Enable-ModelScenarioPath $E; @(Get-EvData $E "$((Get-TestIds).Account)/deployments")[0].properties.provisioningState = 'Failed' }
       Expect = @{ 'model.deployment' = 'Problem:High' } }
    @{ Name = 'models-deployments-unreadable'; Mutate = { param($E) Enable-ModelScenarioPath $E; Set-EvStatus $E "$((Get-TestIds).Account)/deployments" 403 }
       Expect = @{ 'model.deployment' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'models-key-auth-local-auth-off'; Mutate = { param($E) Enable-ModelScenarioPath $E -AuthType 'ApiKey' -NoRole }
       Expect = @{ 'model.authentication' = 'Problem:High' } }
    @{ Name = 'models-key-auth'; Mutate = { param($E) Enable-ModelScenarioPath $E -AuthType 'ApiKey' -NoRole; (Get-EvData $E (Get-TestIds).Account).properties.disableLocalAuth = $false }
       Expect = @{ 'model.authentication' = 'Problem:Low' } }
    @{ Name = 'models-auth-unknown'; Mutate = { param($E) Enable-ModelScenarioPath $E -AuthType '' }
       Expect = @{ 'model.authentication' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'models-connections-unreadable'; Mutate = { param($E) Enable-ModelScenarioPath $E; Set-EvStatus $E "$((Get-TestIds).Project)/connections" 403 }
       Expect = @{ 'model.authentication' = 'CouldNotCheck:Blocking' } }

    # Access results for the Models path (helper above).
    @{ Name = 'access-model-no-role'; Mutate = { param($E) Enable-ModelScenarioPath $E -NoRole }
       Expect = @{ 'access.modelIdentity' = 'Problem:High' } }
    @{ Name = 'access-model-key-auth'; Mutate = { param($E) Enable-ModelScenarioPath $E -AuthType 'ApiKey' -NoRole; (Get-EvData $E (Get-TestIds).Account).properties.disableLocalAuth = $false }
       Expect = @{ 'access.modelIdentity' = 'OK' } }
)
