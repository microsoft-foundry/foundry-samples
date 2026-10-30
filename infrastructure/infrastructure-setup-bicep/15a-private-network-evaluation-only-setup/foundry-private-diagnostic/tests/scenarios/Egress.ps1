# Scenarios for Egress checks. The network builders live in Fixtures.ps1.

@(
    # Positive: forced tunneling through a hub firewall that allows the Monitor query FQDNs.
    @{ Name = 'egress-forced-tunnel-allowed'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E }
       Expect = @{ 'egress.routeTable' = 'OK'; 'egress.peering' = 'OK'; 'egress.nextHopOwner' = 'OK'; 'egress.bgp' = 'OK'; 'firewall.ruleMatch@MonitorQuery' = 'OK' } }
    @{ Name = 'egress-nat-gateway'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).AgentSubnet).properties.natGateway = @{ id = '/subscriptions/x/resourceGroups/rg-network/providers/Microsoft.Network/natGateways/nat-agents' } }
       Expect = @{ 'egress.natGateway' = 'OK'; 'egress.routeTable' = 'OK' } }

    # egress.routeTable
    @{ Name = 'egress-udr-none'; Mutate = { param($E) Set-DiagTestMonitorPublic $E; Add-DiagTestRouteTable $E @(New-DiagTestRoute 'blackhole' '0.0.0.0/0' 'None') }
       Expect = @{ 'egress.routeTable@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'egress-udr-appliance-without-ip'; Mutate = { param($E) Set-DiagTestMonitorPublic $E; Add-DiagTestRouteTable $E @(New-DiagTestRoute 'default' '0.0.0.0/0' 'VirtualAppliance') }
       Expect = @{ 'egress.routeTable@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'egress-udr-pe-to-internet'; Mutate = { param($E) Add-DiagTestRouteTable $E @(New-DiagTestRoute 'storage-out' '10.1.5.7/32' 'Internet') }
       Expect = @{ 'egress.routeTable@Storage' = 'Problem:High' } }
    @{ Name = 'egress-route-table-unreadable'; Mutate = { param($E) Add-DiagTestRouteTable $E @(); Set-EvStatus $E (Get-DiagTestNetIds).RouteTable 403 }
       Expect = @{ 'egress.routeTable' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'egress-route-table-missing'; Mutate = { param($E) Add-DiagTestRouteTable $E @(); Set-EvStatus $E (Get-DiagTestNetIds).RouteTable 404 }
       Expect = @{ 'egress.routeTable' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'egress-pe-address-unknown'; Mutate = { param($E) Add-DiagTestRouteTable $E @(New-DiagTestRoute 'default' '0.0.0.0/0' 'VirtualAppliance' '10.0.1.4'); Set-EvStatus $E (Get-TestIds).PeStorage 403 }
       Expect = @{ 'egress.routeTable@Storage' = 'CouldNotCheck:KnownLimit' }; Allow = @('egress.nextHopOwner') }
    # Zone-group endpoints often have empty customDnsConfigs; the address must come from the zone group record sets.
    @{ Name = 'egress-pe-address-from-zone-group'; Mutate = { param($E)
            $ids = Get-TestIds
            foreach ($pe in $ids.PeAccount, $ids.PeStorage) { (Get-EvData $E $pe).properties.customDnsConfigs = @() }
            Add-DiagTestRouteTable $E @(New-DiagTestRoute 'default' '0.0.0.0/0' 'VirtualAppliance' '10.0.1.4') }
       Expect = @{ 'egress.routeTable@Storage' = 'OK'; 'egress.routeTable@Foundry' = 'OK' }; Allow = @('egress.nextHopOwner') }
    @{ Name = 'egress-zone-group-pe-route-none'; Mutate = { param($E)
            (Get-EvData $E (Get-TestIds).PeStorage).properties.customDnsConfigs = @()
            Add-DiagTestRouteTable $E @(New-DiagTestRoute 'drop-blob' '10.1.5.7/32' 'None') }
       Expect = @{ 'egress.routeTable@Storage' = 'Problem:High' } }
    @{ Name = 'egress-subnet-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).AgentSubnet 403 }
       Expect = @{ 'egress.routeTable' = 'CouldNotCheck:Blocking' } }

    # egress.peSubnetPolicy
    @{ Name = 'egress-pe-subnet-policy-asymmetric'; Mutate = { param($E)
            $fw = Add-DiagTestFirewall $E
            (Get-EvData $E (Get-TestIds).PeSubnet).properties.privateEndpointNetworkPolicies = 'RouteTableEnabled'
            Add-DiagTestForcedTunnel $E -Owner $fw -ExtraRoutes @(New-DiagTestRoute 'pe-via-fw' '10.1.5.0/24' 'VirtualAppliance' '10.0.1.4') }
       Expect = @{ 'egress.peSubnetPolicy' = 'Problem:Medium'; 'firewall.ruleMatch@Storage' = 'OK' } }
    @{ Name = 'egress-pe-32-route-via-appliance'; Mutate = { param($E)
            $fw = Add-DiagTestFirewall $E
            Add-DiagTestForcedTunnel $E -Owner $fw -ExtraRoutes @(New-DiagTestRoute 'blob-via-fw' '10.1.5.7/32' 'VirtualAppliance' '10.0.1.4') }
       Expect = @{ 'egress.peSubnetPolicy@Storage' = 'Problem:Medium'; 'egress.peSubnetPolicy@Foundry' = 'OK' } }
    @{ Name = 'egress-pe-subnet-policy-off'; Mutate = { param($E)
            $fw = Add-DiagTestFirewall $E
            Add-DiagTestForcedTunnel $E -Owner $fw -ExtraRoutes @(New-DiagTestRoute 'pe-via-fw' '10.1.5.0/24' 'VirtualAppliance' '10.0.1.4') }
       Expect = @{ 'egress.peSubnetPolicy' = 'OK'; 'egress.routeTable' = 'OK' } }

    # egress.peering
    @{ Name = 'egress-peering-disconnected'; Mutate = { param($E) Add-DiagTestPeering $E -State Disconnected }
       Expect = @{ 'egress.peering' = 'Problem:High' } }
    @{ Name = 'egress-peering-no-forwarded-traffic'; Mutate = { param($E) $null = Add-DiagTestFirewall $E; Add-DiagTestForcedTunnel $E -Owner (Get-DiagTestNetIds).Firewall -NoPeering; Add-DiagTestPeering $E -Forwarded $false }
       Expect = @{ 'egress.peering' = 'Problem:Medium' } }
    @{ Name = 'egress-peering-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).Vnet)/virtualNetworkPeerings" 403 }
       Expect = @{ 'egress.peering' = 'CouldNotCheck:Blocking' } }

    # egress.bgp
    @{ Name = 'egress-bgp-gateway-subnet'; Mutate = { param($E) $v = Get-EvData $E (Get-TestIds).Vnet; $v.properties.subnets += @{ name = 'GatewaySubnet'; id = "$((Get-TestIds).Vnet)/subnets/GatewaySubnet" } }
       Expect = @{ 'egress.bgp' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'egress-bgp-remote-gateway'; Mutate = { param($E) Add-DiagTestPeering $E -UseRemoteGateways }
       Expect = @{ 'egress.bgp' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'egress-bgp-overridden-by-udr'; Mutate = { param($E)
            Add-DiagTestPeering $E -UseRemoteGateways -Name 'to-hub-gw'
            $fw = Add-DiagTestFirewall $E
            Set-DiagTestMonitorPublic $E
            Add-DiagTestRouteTable $E @(New-DiagTestRoute 'default' '0.0.0.0/0' 'VirtualAppliance' '10.0.1.4') -BgpOn
            Add-DiagTestNextHop $E '10.0.1.4' $fw AzureFirewall }
       Expect = @{ 'egress.bgp' = 'OK'; 'egress.routeTable' = 'OK' } }

    # egress.vwan
    @{ Name = 'egress-vwan-secured-hub'; Mutate = { param($E) $null = Add-DiagTestHub $E }
       Expect = @{ 'egress.vwan' = 'OK'; 'egress.routeTable' = 'OK'; 'firewall.ruleMatch@MonitorQuery' = 'OK' } }
    @{ Name = 'egress-vwan-hub-routing-failed'; Mutate = { param($E) $null = Add-DiagTestHub $E -RoutingState Failed }
       Expect = @{ 'egress.vwan' = 'Problem:High' } }
    @{ Name = 'egress-vwan-hub-unreadable'; Mutate = { param($E) $null = Add-DiagTestHub $E; $h = (Get-DiagTestNetIds).Hub; Set-EvStatus $E $h 403; Set-EvStatus $E "$h/routingIntent" 403 }
       Expect = @{ 'egress.vwan' = 'CouldNotCheck:Blocking'; 'egress.bgp' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'egress-vwan-intent-unreadable'; Mutate = { param($E) $null = Add-DiagTestHub $E; Set-EvStatus $E "$((Get-DiagTestNetIds).Hub)/routingIntent" 403 }
       Expect = @{ 'egress.vwan' = 'CouldNotCheck:Blocking'; 'egress.bgp' = 'CouldNotCheck:KnownLimit' } }

    # egress.nextHopOwner
    @{ Name = 'egress-next-hop-unknown-owner'; Mutate = { param($E) Add-DiagTestForcedTunnel $E -Ip '192.168.10.4' -Owner $null -NoPeering }
       Expect = @{ 'egress.nextHopOwner' = 'CouldNotCheck:KnownLimit'; 'egress.routeTable' = 'OK' } }
    @{ Name = 'egress-next-hop-not-collected'; Mutate = { param($E) Add-DiagTestForcedTunnel $E -Ip '192.168.10.4' -NoPeering }
       Expect = @{ 'egress.nextHopOwner' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'egress-next-hop-lookup-forbidden'; Mutate = { param($E) Add-DiagTestForcedTunnel $E -Ip '192.168.10.4' -Owner $null -NoPeering
            Set-EvRequest $E '/providers/Microsoft.ResourceGraph/resources#nextHop:192.168.10.4' $null -Status 403 -Method POST -Api ResourceGraph }
       Expect = @{ 'egress.nextHopOwner' = 'CouldNotCheck:Blocking' } }
)
