# Scenarios for NVA checks. The network builders live in Fixtures.ps1.

@(
    # Positive: a reachable NVA. Its own rules can't be read, so nva.rules is always a known limit.
    @{ Name = 'nva-healthy'; Mutate = { param($E) Add-DiagTestNva $E }
       Expect = @{ 'nva.identified' = 'OK'; 'nva.ipForwarding@MonitorQuery' = 'OK'; 'nva.nsg@MonitorQuery' = 'OK'; 'nva.rules@MonitorQuery' = 'CouldNotCheck:KnownLimit'
                   'egress.nextHopOwner' = 'OK'; 'egress.routeTable' = 'OK' } }
    @{ Name = 'nva-nsg-explicit-allow'; Mutate = { param($E) Add-DiagTestNva $E -NicRules @(
            (New-DiagTestNsgRule 'allow-agents' 100 -Access Allow -Source '10.1.2.0/24')
            (New-DiagTestNsgRule 'deny-all' 200 -Source '*' -Port '*' -Protocol '*')) }
       Expect = @{ 'nva.nsg@MonitorQuery' = 'OK' }; Allow = @('nva.rules') }
    @{ Name = 'nva-behind-load-balancer'; Mutate = { param($E) Add-DiagTestNva $E -ViaLb }
       Expect = @{ 'nva.identified' = 'OK'; 'nva.ipForwarding@MonitorQuery' = 'OK'; 'nva.nsg@MonitorQuery' = 'OK' }; Allow = @('nva.rules') }

    # nva.identified
    @{ Name = 'nva-load-balancer-no-backends'; Mutate = { param($E) Add-DiagTestNva $E -ViaLb -NoBackends }
       Expect = @{ 'nva.identified' = 'Problem:High' }; Allow = @('nva.rules') }
    @{ Name = 'nva-nic-missing'; Mutate = { param($E) Add-DiagTestNva $E; Set-EvStatus $E (Get-DiagTestNetIds).NvaNic 404 }
       Expect = @{ 'nva.identified' = 'Problem:High' }; Allow = @('nva.rules') }
    @{ Name = 'nva-nic-unreadable'; Mutate = { param($E) Add-DiagTestNva $E; Set-EvStatus $E (Get-DiagTestNetIds).NvaNic 403 }
       Expect = @{ 'nva.identified' = 'CouldNotCheck:Blocking' }; Allow = @('nva.rules') }

    # nva.ipForwarding
    @{ Name = 'nva-ip-forwarding-off'; Mutate = { param($E) Add-DiagTestNva $E -IpForwarding $false }
       Expect = @{ 'nva.ipForwarding@MonitorQuery' = 'Problem:High'; 'nva.identified' = 'OK' }; Allow = @('nva.rules') }

    # nva.nsg
    @{ Name = 'nva-nic-nsg-denies-agents'; Mutate = { param($E) Add-DiagTestNva $E -NicRules @(New-DiagTestNsgRule 'deny-spokes' 100 -Source '10.1.0.0/16') }
       Expect = @{ 'nva.nsg@MonitorQuery' = 'Problem:High' }; Allow = @('nva.rules') }
    @{ Name = 'nva-subnet-nsg-denies-agents'; Mutate = { param($E) Add-DiagTestNva $E -SubnetRules @(New-DiagTestNsgRule 'deny-https' 100 -Source 'VirtualNetwork') }
       Expect = @{ 'nva.nsg@MonitorQuery' = 'Problem:High' }; Allow = @('nva.rules') }
    @{ Name = 'nva-nsg-unreadable'; Mutate = { param($E) Add-DiagTestNva $E; Set-EvStatus $E (Get-DiagTestNetIds).NvaNsg 403 }
       Expect = @{ 'nva.nsg@MonitorQuery' = 'CouldNotCheck:Blocking' }; Allow = @('nva.rules') }

    # Peering towards the NVA's VNet does not allow forwarded traffic.
    @{ Name = 'nva-peering-no-forwarded-traffic'; Mutate = { param($E) Add-DiagTestNva $E; Add-DiagTestPeering $E -Forwarded $false }
       Expect = @{ 'egress.peering' = 'Problem:Medium' }; Allow = @('nva.rules') }

    # onprem.route
    @{ Name = 'nva-forced-tunnel-to-gateway'; Mutate = { param($E) Add-DiagTestForcedTunnel $E -Type VirtualNetworkGateway }
       Expect = @{ 'onprem.route@MonitorQuery' = 'CouldNotCheck:KnownLimit' }; Allow = @('egress.bgp') }
)
