# Scenarios for Firewall checks. The network builders live in Fixtures.ps1.

function global:Get-DiagTestMonitorHosts { @('api.loganalytics.io', 'api.applicationinsights.io') }
function global:Get-DiagTestClassicApp {
    @(@{ name = 'app-evaluation'; properties = @{ priority = 200; action = @{ type = 'Allow' }; rules = @(
        @{ name = 'monitor-query'; sourceAddresses = @('10.1.2.0/24'); targetFqdns = @(Get-DiagTestMonitorHosts); protocols = @(@{ protocolType = 'Https'; port = 443 }) }) } })
}

@(
    # Positive: rules that allow the traffic.
    @{ Name = 'firewall-app-rule-allows'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E }
       Expect = @{ 'firewall.state' = 'OK'; 'firewall.ruleMatch@MonitorQuery' = 'OK'; 'firewall.dnsProxy' = 'OK'; 'firewall.tlsInspection' = 'OK'; 'firewall.idps' = 'OK'
                   'firewall.threatIntel' = 'OK'; 'firewall.snat' = 'OK'; 'firewall.logs' = 'OK'; 'firewall.logQuery' = 'OK' } }
    @{ Name = 'firewall-wildcard-fqdn-allows'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' @('*.loganalytics.io', '*.applicationinsights.io') -Sources @('10.0.0.0/8')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'OK' } }
    @{ Name = 'firewall-service-tag-network-rule-allows'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'net' 100 Allow @(New-DiagTestNetRule 'monitor-tag' -Destinations @('AzureMonitor')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'OK'; 'firewall.dnsProxy' = 'OK' } }
    @{ Name = 'firewall-parent-policy-allows'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(); ParentGroups = (Get-DiagTestAllowGroups) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'OK' } }
    @{ Name = 'firewall-classic-rules-allow'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Classic = $true; ClassicApp = (Get-DiagTestClassicApp) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'OK'; 'firewall.threatIntel' = 'OK' } }
    @{ Name = 'firewall-fqdn-network-rule-with-dns-proxy'; Mutate = { param($E)
            $null = Add-DiagTestFirewallEgress $E @{ PolicyProps = @{ dnsSettings = @{ enableProxy = $true; servers = @() } }
                Groups = @(New-DiagTestRcg 'rcg' 100 @(New-DiagTestRc 'net' 100 Allow @(New-DiagTestNetRule 'monitor-fqdn' -Fqdns (Get-DiagTestMonitorHosts)))) }
            (Get-EvData $E (Get-TestIds).Vnet).properties.dhcpOptions.dnsServers = @('10.0.1.4') }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'OK'; 'firewall.dnsProxy@MonitorQuery' = 'OK' } }

    # firewall.ruleMatch problems.
    @{ Name = 'firewall-no-allow-rule'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app-web' 100 Allow @(New-DiagTestAppRule 'windows-update' @('*.windowsupdate.com')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-empty-policy'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @() } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-deny-collection-first'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            (New-DiagTestRc 'app-block' 100 Deny @(New-DiagTestAppRule 'block-all' @('*') -Sources @('*')))
            (New-DiagTestRc 'app-allow' 200 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts))))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-rcg-priority-order'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(
            (New-DiagTestRcg 'rcg-allow' 300 @(New-DiagTestRc 'app-allow' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts))))
            (New-DiagTestRcg 'rcg-deny' 200 @(New-DiagTestRc 'app-block' 500 Deny @(New-DiagTestAppRule 'block-monitor' @('*.loganalytics.io', '*.applicationinsights.io'))))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-network-deny-before-app-allow'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            (New-DiagTestRc 'app-allow' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts)))
            (New-DiagTestRc 'net-block' 900 Deny @(New-DiagTestNetRule 'block-https' -Destinations @('*'))))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-parent-policy-deny'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{
            ParentGroups = @(New-DiagTestRcg 'rcg-base' 100 @(New-DiagTestRc 'app-block' 100 Deny @(New-DiagTestAppRule 'block-monitor' @('api.loganalytics.io') -Sources @('*')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-wrong-source'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts) -Sources @('10.9.0.0/16')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-wrong-protocol'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts) -Protocol Http -Port 80))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-classic-no-rule'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Classic = $true } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-pe-traffic-not-allowed'; Mutate = { param($E)
            $fw = Add-DiagTestFirewall $E -Groups @(New-DiagTestRcg 'rcg' 100 @(New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' @('api.loganalytics.io', 'api.applicationinsights.io'))))
            Add-DiagTestForcedTunnel $E -Owner $fw -ExtraRoutes @(New-DiagTestRoute 'blob-via-fw' '10.1.5.7/32' 'VirtualAppliance' '10.0.1.4') }
       Expect = @{ 'firewall.ruleMatch@Storage' = 'Problem:High'; 'firewall.ruleMatch@MonitorQuery' = 'OK' } }
    @{ Name = 'firewall-vwan-hub-no-rule'; Mutate = { param($E) $null = Add-DiagTestHub $E -Firewall @{ Groups = @() } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'Problem:High'; 'egress.vwan' = 'OK' } }

    # firewall.ruleMatch known limits.
    @{ Name = 'firewall-ip-group-source'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts) -Sources @() -IpGroups @('/subscriptions/x/resourceGroups/rg-hub/providers/Microsoft.Network/ipGroups/agents')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'firewall-partial-source'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts) -Sources @('10.1.2.0/25')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'firewall-web-category'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'tech' @() -WebCategories @('ComputersAndTechnology')))) } }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'CouldNotCheck:KnownLimit' } }

    # Read gaps.
    @{ Name = 'firewall-other-subscription-unreadable'; Mutate = { param($E)
            $fw = Add-DiagTestFirewall $E -FirewallId '/subscriptions/99999999-0000-0000-0000-000000000000/resourceGroups/rg-hub-prod/providers/Microsoft.Network/azureFirewalls/fw-prod'
            Add-DiagTestForcedTunnel $E -Owner $fw; Set-EvStatus $E $fw 403 }
       Expect = @{ 'firewall.state@MonitorQuery' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'firewall-policy-unreadable'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E; Set-EvStatus $E (Get-DiagTestNetIds).Policy 403 }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'firewall-parent-policy-unreadable'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ ParentGroups = @() }; Set-EvStatus $E (Get-DiagTestNetIds).ParentPolicy 403 }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'firewall-rule-groups-unreadable'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E; Set-EvStatus $E "$((Get-DiagTestNetIds).Policy)/ruleCollectionGroups" 403 }
       Expect = @{ 'firewall.ruleMatch@MonitorQuery' = 'CouldNotCheck:Blocking' } }

    # firewall.state
    @{ Name = 'firewall-failed'; Mutate = { param($E) $fw = Add-DiagTestFirewallEgress $E; (Get-EvData $E $fw).properties.provisioningState = 'Failed' }
       Expect = @{ 'firewall.state@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'firewall-missing'; Mutate = { param($E) $fw = Add-DiagTestFirewallEgress $E; Set-EvStatus $E $fw 404 }
       Expect = @{ 'firewall.state@MonitorQuery' = 'Problem:High' } }

    # firewall.dnsProxy
    @{ Name = 'firewall-fqdn-network-rule-without-dns-proxy'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'net' 100 Allow @(New-DiagTestNetRule 'monitor-fqdn' -Fqdns (Get-DiagTestMonitorHosts)))) } }
       Expect = @{ 'firewall.dnsProxy@MonitorQuery' = 'Problem:Medium'; 'firewall.ruleMatch@MonitorQuery' = 'OK' } }
    @{ Name = 'firewall-dns-proxy-but-vnet-dns-elsewhere'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ PolicyProps = @{ dnsSettings = @{ enableProxy = $true; servers = @() } }
            Groups = @(New-DiagTestRcg 'rcg' 100 @(New-DiagTestRc 'net' 100 Allow @(New-DiagTestNetRule 'monitor-fqdn' -Fqdns (Get-DiagTestMonitorHosts)))) } }
       Expect = @{ 'firewall.dnsProxy@MonitorQuery' = 'Problem:Medium' } }

    # firewall.tlsInspection
    @{ Name = 'firewall-tls-inspection'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Groups = @(New-DiagTestRcg 'rcg' 100 @(
            New-DiagTestRc 'app' 100 Allow @(New-DiagTestAppRule 'monitor' (Get-DiagTestMonitorHosts) -Tls))) } }
       Expect = @{ 'firewall.tlsInspection@MonitorQuery' = 'Problem:Medium'; 'firewall.ruleMatch@MonitorQuery' = 'OK' } }

    # firewall.idps / threatIntel
    @{ Name = 'firewall-idps-deny'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ PolicyProps = @{ intrusionDetection = @{ mode = 'Deny' } } } }
       Expect = @{ 'firewall.idps@MonitorQuery' = 'Problem:Medium' } }
    @{ Name = 'firewall-idps-deny-in-parent'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ ParentGroups = @(); ParentProps = @{ intrusionDetection = @{ mode = 'Deny' } } } }
       Expect = @{ 'firewall.idps@MonitorQuery' = 'Problem:Medium' } }
    @{ Name = 'firewall-threat-intel-deny'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ PolicyProps = @{ threatIntelMode = 'Deny' } } }
       Expect = @{ 'firewall.threatIntel' = 'Problem:Low' } }
    @{ Name = 'firewall-classic-threat-intel-deny'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ Classic = $true; ClassicApp = (Get-DiagTestClassicApp); ClassicProps = @{ threatIntelMode = 'Deny' } } }
       Expect = @{ 'firewall.threatIntel' = 'Problem:Low' } }

    # firewall.snat
    @{ Name = 'firewall-snat-high'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ SnatMax = 92 } }
       Expect = @{ 'firewall.snat' = 'Problem:Medium' } }
    @{ Name = 'firewall-snat-no-data'; Mutate = { param($E) $null = Add-DiagTestFirewallEgress $E @{ SnatMax = $null } }
       Expect = @{ 'firewall.snat' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'firewall-snat-unreadable'; Mutate = { param($E) $fw = Add-DiagTestFirewallEgress $E; Set-EvStatus $E "$fw/providers/Microsoft.Insights/metrics" 403 }
       Expect = @{ 'firewall.snat' = 'CouldNotCheck:KnownLimit' } }

    # firewall.logs
    @{ Name = 'firewall-no-diagnostic-logs'; Mutate = { param($E) $fw = Add-DiagTestFirewallEgress $E; Set-EvRequest $E "$fw/providers/Microsoft.Insights/diagnosticSettings" @() }
       Expect = @{ 'firewall.logs' = 'Problem:Low'; 'firewall.logQuery' = 'OK' } }
    @{ Name = 'firewall-logs-disabled'; Mutate = { param($E) $fw = Add-DiagTestFirewallEgress $E; (@(Get-EvData $E "$fw/providers/Microsoft.Insights/diagnosticSettings")[0]).properties.logs[0].enabled = $false }
       Expect = @{ 'firewall.logs' = 'Problem:Low' } }
    @{ Name = 'firewall-logs-unreadable'; Mutate = { param($E) $fw = Add-DiagTestFirewallEgress $E; Set-EvStatus $E "$fw/providers/Microsoft.Insights/diagnosticSettings" 403 }
       Expect = @{ 'firewall.logs' = 'CouldNotCheck:KnownLimit' } }
)
