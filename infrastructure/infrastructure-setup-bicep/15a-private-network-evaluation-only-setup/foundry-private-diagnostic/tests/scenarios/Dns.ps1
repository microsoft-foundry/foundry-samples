# Scenarios for Dns checks.

function global:Get-DnsScenarioZoneId { param([string]$Zone) "$((Get-TestIds).Zones)/$Zone" }

function global:Set-DnsScenarioCustomDns {
    param($E, [string[]]$Servers = @('10.1.9.10'))
    (Get-EvData $E (Get-TestIds).Vnet).properties.dhcpOptions.dnsServers = $Servers
}

function global:Remove-DnsScenarioZoneFromGroup {
    param($E, [string]$Zone)
    $group = @(Get-EvData $E "$((Get-TestIds).PeAccount)/privateDnsZoneGroups")[0]
    $group.properties.privateDnsZoneConfigs = @($group.properties.privateDnsZoneConfigs | Where-Object { $_.name -ne $Zone })
}

@(
    @{ Name = 'dns-zone-missing-from-group'; Mutate = { param($E) Remove-DnsScenarioZoneFromGroup $E 'privatelink.openai.azure.com' }
       Expect = @{ 'dns.zoneGroup@Foundry' = 'Problem:High' } }
    @{ Name = 'dns-zone-missing-custom-dns'; Mutate = { param($E) Remove-DnsScenarioZoneFromGroup $E 'privatelink.openai.azure.com'; Set-DnsScenarioCustomDns $E }
       Expect = @{ 'dns.zoneGroup@Foundry' = 'Problem:Medium'; 'dns.customResolver' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'dns-zone-groups-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).PeStorage)/privateDnsZoneGroups" 403 }
       Expect = @{ 'dns.zoneGroup@Storage' = 'CouldNotCheck:Blocking' } }

    @{ Name = 'dns-zone-not-linked'; Mutate = { param($E) Set-EvRequest $E "$(Get-DnsScenarioZoneId 'privatelink.services.ai.azure.com')/virtualNetworkLinks" @() }
       Expect = @{ 'dns.vnetLink@Foundry' = 'Problem:High' } }
    @{ Name = 'dns-zone-linked-elsewhere'; Mutate = { param($E)
            $z = Get-DnsScenarioZoneId 'privatelink.blob.core.windows.net'
            @(Get-EvData $E "$z/virtualNetworkLinks")[0].properties.virtualNetwork.id = (Get-TestIds).Vnet -replace 'vnet-agents$', 'vnet-other' }
       Expect = @{ 'dns.vnetLink@Storage' = 'Problem:High' } }
    @{ Name = 'dns-zone-linked-to-dns-vnet-custom-dns'; Mutate = { param($E)
            $z = Get-DnsScenarioZoneId 'privatelink.blob.core.windows.net'
            @(Get-EvData $E "$z/virtualNetworkLinks")[0].properties.virtualNetwork.id = (Get-TestIds).Vnet -replace 'vnet-agents$', 'vnet-dns'
            Set-DnsScenarioCustomDns $E }
       Expect = @{ 'dns.vnetLink@Storage' = 'CouldNotCheck:KnownLimit'; 'dns.customResolver' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'dns-zone-link-in-progress'; Mutate = { param($E)
            @(Get-EvData $E "$(Get-DnsScenarioZoneId 'privatelink.monitor.azure.com')/virtualNetworkLinks")[0].properties.virtualNetworkLinkState = 'InProgress' }
       Expect = @{ 'dns.vnetLink@MonitorQuery' = 'Problem:Medium' } }
    @{ Name = 'dns-zone-links-unreadable'; Mutate = { param($E) Set-EvStatus $E "$(Get-DnsScenarioZoneId 'privatelink.services.ai.azure.com')/virtualNetworkLinks" 403 }
       Expect = @{ 'dns.vnetLink@Foundry' = 'CouldNotCheck:Blocking' } }

    @{ Name = 'dns-record-stale'; Mutate = { param($E)
            @(Get-EvData $E "$(Get-DnsScenarioZoneId 'privatelink.services.ai.azure.com')/A")[0].properties.aRecords = @(@{ ipv4Address = '10.1.5.99' }) }
       Expect = @{ 'dns.record@Foundry' = 'Problem:High' } }
    @{ Name = 'dns-record-missing'; Mutate = { param($E) Set-EvRequest $E "$(Get-DnsScenarioZoneId 'privatelink.blob.core.windows.net')/A" @() }
       Expect = @{ 'dns.record@Storage' = 'Problem:High' } }
    @{ Name = 'dns-records-unreadable'; Mutate = { param($E) Set-EvStatus $E "$(Get-DnsScenarioZoneId 'privatelink.monitor.azure.com')/A" 403 }
       Expect = @{ 'dns.record@MonitorQuery' = 'CouldNotCheck:Blocking' } }

    @{ Name = 'dns-custom-resolver'; Mutate = { param($E) Set-DnsScenarioCustomDns $E @('10.1.9.10', '10.1.9.11') }
       Expect = @{ 'dns.customResolver' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'dns-custom-resolver-includes-azure-dns'; Mutate = { param($E) Set-DnsScenarioCustomDns $E @('168.63.129.16') }
       Expect = @{ 'dns.customResolver' = 'OK' } }

    # The scope's PE also lists ingestion hosts such as the solution-pack blob; evaluations only need the query zone.
    @{ Name = 'dns-ampls-ingestion-host-ignored'; Mutate = { param($E)
            @($E.discovery.dependencies | Where-Object kind -eq 'Ampls')[0].hosts = @('scadvisorcontentpl.blob.core.windows.net', 'api.monitor.azure.com') }
       Expect = @{ 'dns.zoneGroup@MonitorQuery' = 'OK' } }
)
