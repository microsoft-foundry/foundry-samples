# Scenarios for PrivateEndpoint checks.

function global:Get-PeScenarioDependency {
    param($E, [string]$Kind)
    @($E.discovery.dependencies | Where-Object { $_.kind -eq $Kind })[0]
}

# Removes every private endpoint from a dependency (discovery list and the target's connections).
function global:Remove-PeScenarioEndpoints {
    param($E, [string]$Kind)
    $ids = Get-TestIds
    (Get-PeScenarioDependency $E $Kind).privateEndpoints = @()
    switch ($Kind) {
        'Account' { Set-EvRequest $E "$($ids.Account)/privateEndpointConnections" @() }
        'Storage' { Set-EvRequest $E "$($ids.Storage)/privateEndpointConnections" @() }
        'Ampls' { (Get-EvData $E $ids.Ampls).properties.privateEndpointConnections = @() }
    }
}

# Moves the account private endpoint into another VNet (vnet-hub) with an NSG-free subnet.
function global:Move-PeScenarioAccountPe {
    param($E)
    $ids = Get-TestIds
    $hubSubnet = ($ids.Vnet -replace 'vnet-agents$', 'vnet-hub') + '/subnets/pe'
    (Get-EvData $E $ids.PeAccount).properties.subnet.id = $hubSubnet
    Set-EvRequest $E $hubSubnet (New-ArmObject $hubSubnet @{ addressPrefix = '10.2.5.0/24'; privateEndpointNetworkPolicies = 'Disabled'; delegations = @() })
    $hubSubnet
}

function global:Set-PeScenarioPeering {
    param($E, [string]$RemoteVnet, [string]$State)
    $ids = Get-TestIds
    Set-EvRequest $E "$($ids.Vnet)/virtualNetworkPeerings" @((New-ArmObject "$($ids.Vnet)/virtualNetworkPeerings/to-hub" @{
        remoteVirtualNetwork = @{ id = $RemoteVnet }; peeringState = $State; allowForwardedTraffic = $true; useRemoteGateways = $false }))
}

@(
    @{ Name = 'pe-account-missing'; Mutate = { param($E) Remove-PeScenarioEndpoints $E 'Account' }
       Expect = @{ 'pe.exists@Foundry' = 'Problem:High' } }
    @{ Name = 'pe-account-missing-public'; Mutate = { param($E) Remove-PeScenarioEndpoints $E 'Account'
            $a = Get-EvData $E (Get-TestIds).Account; $a.properties.publicNetworkAccess = 'Enabled'; $a.properties.networkAcls.defaultAction = 'Allow' }
       Expect = @{ 'pe.exists@Foundry' = 'OK' } }
    @{ Name = 'pe-storage-missing-selected-networks'; Mutate = { param($E) Remove-PeScenarioEndpoints $E 'Storage'
            (Get-EvData $E (Get-TestIds).Storage).properties.publicNetworkAccess = 'Enabled' }
       Expect = @{ 'pe.exists@Storage' = 'Problem:Medium' } }
    @{ Name = 'pe-ampls-missing'; Mutate = { param($E) Remove-PeScenarioEndpoints $E 'Ampls' }
       Expect = @{ 'monitoring.amplsPe@MonitorQuery' = 'Problem:High'; 'monitoring.queryPath@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'pe-connections-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).Account)/privateEndpointConnections" 403 }
       Expect = @{ 'pe.exists@Foundry' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'pe-connections-old-evidence'; Mutate = { param($E) Remove-EvRequest $E "$((Get-TestIds).Account)/privateEndpointConnections" }
       Expect = @{ 'pe.exists@Foundry' = 'CouldNotCheck:KnownLimit' } }

    @{ Name = 'pe-account-pending'; Mutate = { param($E) @(Get-EvData $E "$((Get-TestIds).Account)/privateEndpointConnections")[0].properties.privateLinkServiceConnectionState.status = 'Pending' }
       Expect = @{ 'pe.approval@Foundry' = 'Problem:High' } }
    @{ Name = 'pe-ampls-rejected'; Mutate = { param($E) @((Get-EvData $E (Get-TestIds).Ampls).properties.privateEndpointConnections)[0].properties.privateLinkServiceConnectionState.status = 'Rejected' }
       Expect = @{ 'pe.approval@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'pe-extra-pending-with-approved'; Mutate = { param($E)
            $ids = Get-TestIds; $pe2 = "$($ids.PeAccount)-2"
            New-PeEvidence $E $pe2 $ids.Account 'account' @{ 'acct.services.ai.azure.com' = '10.1.5.20' } @{}
            Set-EvRequest $E "$pe2/privateDnsZoneGroups" @()
            $c = Get-EvData $E "$($ids.Account)/privateEndpointConnections"
            Set-EvRequest $E "$($ids.Account)/privateEndpointConnections" @(@($c) + @(New-ArmObject "$($ids.Account)/privateEndpointConnections/pec-acct-2" @{
                privateEndpoint = @{ id = $pe2 }; privateLinkServiceConnectionState = @{ status = 'Pending' }; groupIds = @('account') })) }
       Expect = @{ 'pe.approval@Foundry' = 'Problem:Low' }; Allow = @('dns.zoneGroup', 'nsg.agentOutbound') }

    @{ Name = 'pe-unpeered-vnet'; Mutate = { param($E) Move-PeScenarioAccountPe $E | Out-Null }
       Expect = @{ 'pe.placement@Foundry' = 'Problem:High' } }
    @{ Name = 'pe-peering-disconnected'; Mutate = { param($E) $s = Move-PeScenarioAccountPe $E; Set-PeScenarioPeering $E (Get-ArmParent $s) 'Disconnected' }
       Expect = @{ 'pe.placement@Foundry' = 'Problem:High' } }
    @{ Name = 'pe-peering-connected'; Mutate = { param($E) $s = Move-PeScenarioAccountPe $E; Set-PeScenarioPeering $E (Get-ArmParent $s) 'Connected' }
       Expect = @{ 'pe.placement@Foundry' = 'OK' } }
    @{ Name = 'pe-unpeered-vnet-behind-hub'; Mutate = { param($E) Move-PeScenarioAccountPe $E | Out-Null
            $E.discovery.virtualHub = "/subscriptions/$((Get-TestIds).Sub)/resourceGroups/rg-network/providers/Microsoft.Network/virtualHubs/hub" }
       Expect = @{ 'pe.placement@Foundry' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'pe-peerings-unreadable'; Mutate = { param($E) Move-PeScenarioAccountPe $E | Out-Null; Set-EvStatus $E "$((Get-TestIds).Vnet)/virtualNetworkPeerings" 403 }
       Expect = @{ 'pe.placement@Foundry' = 'CouldNotCheck:Blocking' } }

    @{ Name = 'pe-no-addresses'; Mutate = { param($E)
            $ids = Get-TestIds
            (Get-EvData $E $ids.PeAccount).properties.customDnsConfigs = @()
            foreach ($c in @(Get-EvData $E "$($ids.PeAccount)/privateDnsZoneGroups")[0].properties.privateDnsZoneConfigs) { $c.properties.recordSets = @() } }
       Expect = @{ 'pe.addresses@Foundry' = 'Problem:High' } }
    @{ Name = 'pe-deleted'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).PeStorage 404 }
       Expect = @{ 'pe.addresses@Storage' = 'Problem:High' } }
    @{ Name = 'pe-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).PeAccount 403 }
       Expect = @{ 'pe.placement@Foundry' = 'CouldNotCheck:Blocking'; 'pe.addresses@Foundry' = 'CouldNotCheck:Blocking' } }
)
