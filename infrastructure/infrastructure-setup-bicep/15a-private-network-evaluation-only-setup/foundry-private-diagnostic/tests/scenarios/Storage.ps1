# Scenarios for Storage checks.

# Scenario files run in a child scope; helpers are global so Mutate blocks can call them later.
function global:Get-StorageScenarioConnection {
    param($E)
    @((Get-EvData $E "$((Get-TestIds).Project)/connections") | Where-Object { $_.name -eq 'storage-conn' })[0]
}

@(
    @{ Name = 'storage-no-connection'; Mutate = { param($E) $E.discovery.connections = @($E.discovery.connections | Where-Object { $_.path -ne 'Storage' }) }
       Expect = @{ 'storage.connection' = 'Problem:High' }; Allow = @('access.projectStorage') }
    @{ Name = 'storage-connection-wrong-type'; Mutate = { param($E) @($E.discovery.connections | Where-Object { $_.path -eq 'Storage' })[0].resource = (Get-TestIds).AppInsights }
       Expect = @{ 'storage.connection' = 'Problem:High' } }
    @{ Name = 'storage-connection-target-mismatch'; Mutate = { param($E) (Get-StorageScenarioConnection $E).properties.target = 'https://otheracct.blob.core.windows.net/' }
       Expect = @{ 'storage.connection' = 'Problem:High' } }
    @{ Name = 'storage-not-found'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Storage 404 }
       Expect = @{ 'storage.resource' = 'Problem:High' } }
    @{ Name = 'storage-failed'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Storage).properties.provisioningState = 'Failed' }
       Expect = @{ 'storage.resource' = 'Problem:High' } }
    @{ Name = 'storage-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Storage 403 }
       Expect = @{ 'storage.resource' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'storage-key-auth'; Mutate = { param($E) (Get-StorageScenarioConnection $E).properties.authType = 'AccountKey'; (Get-EvData $E (Get-TestIds).Storage).properties.allowSharedKeyAccess = $true }
       Expect = @{ 'storage.authentication' = 'Problem:Low' } }
    @{ Name = 'storage-key-auth-shared-key-off'; Mutate = { param($E) (Get-StorageScenarioConnection $E).properties.authType = 'AccountKey' }
       Expect = @{ 'storage.authentication' = 'Problem:High' } }
    @{ Name = 'storage-auth-unknown'; Mutate = { param($E) (Get-StorageScenarioConnection $E).properties.Remove('authType') }
       Expect = @{ 'storage.authentication' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'storage-connections-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).Project)/connections" 403 }
       Expect = @{ 'storage.authentication' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'storage-private-no-pe'; Mutate = { param($E) Set-EvRequest $E "$((Get-TestIds).Storage)/privateEndpointConnections" @() }
       Expect = @{ 'storage.privatePolicy' = 'Problem:High' } }
    @{ Name = 'storage-selected-networks-no-pe'; Mutate = { param($E) Set-EvRequest $E "$((Get-TestIds).Storage)/privateEndpointConnections" @(); (Get-EvData $E (Get-TestIds).Storage).properties.publicNetworkAccess = 'Enabled' }
       Expect = @{ 'storage.privatePolicy' = 'Problem:Medium' } }
    @{ Name = 'storage-public-no-pe'; Mutate = { param($E) Set-EvRequest $E "$((Get-TestIds).Storage)/privateEndpointConnections" @(); $p = (Get-EvData $E (Get-TestIds).Storage).properties; $p.publicNetworkAccess = 'Enabled'; $p.networkAcls.defaultAction = 'Allow' }
       Expect = @{ 'storage.privatePolicy' = 'OK' } }
    @{ Name = 'storage-pe-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).Storage)/privateEndpointConnections" 403 }
       Expect = @{ 'storage.privatePolicy' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'storage-pe-file-only'; Mutate = { param($E) @(Get-EvData $E "$((Get-TestIds).Storage)/privateEndpointConnections")[0].properties.groupIds = @('file') }
       Expect = @{ 'storage.subresources' = 'Problem:High' } }
    @{ Name = 'storage-uses-queue-without-pe'; Mutate = { param($E) $d = @($E.discovery.dependencies | Where-Object { $_.kind -eq 'Storage' })[0]; $d.hosts = @($d.hosts) + 'stacct.queue.core.windows.net' }
       Expect = @{ 'storage.subresources' = 'Problem:High' } }
    # The storage account's connection list can omit groupIds; the private endpoint has them.
    @{ Name = 'storage-pec-without-group-ids'; Mutate = { param($E) @(Get-EvData $E "$((Get-TestIds).Storage)/privateEndpointConnections")[0].properties.Remove('groupIds') }
       Expect = @{ 'storage.subresources' = 'OK' } }
)
