# Scenarios for Monitoring checks (Application Insights, Log Analytics, AMPLS).

# Scenario files run in a child scope; helpers are global so Mutate blocks can call them later.
function global:Remove-MonitorScenarioZone {
    param($E, [string]$Zone)
    $group = @(Get-EvData $E "$((Get-TestIds).PeAmpls)/privateDnsZoneGroups")[0]
    $group.properties.privateDnsZoneConfigs = @($group.properties.privateDnsZoneConfigs | Where-Object { $_.name -ne $Zone })
}

function global:Remove-MonitorScenarioAmpls {
    param($E)
    $ids = Get-TestIds
    $E.discovery.dependencies = @($E.discovery.dependencies | Where-Object { $_.kind -ne 'Ampls' })
    (Get-EvData $E $ids.AppInsights).properties.privateLinkScopedResources = @()
    (Get-EvData $E $ids.Workspace).properties.privateLinkScopedResources = @()
}

@(
    @{ Name = 'monitor-no-connection'; Mutate = { param($E) $E.discovery.connections = @($E.discovery.connections | Where-Object { $_.path -ne 'MonitorQuery' }) }
       Expect = @{ 'monitoring.connection' = 'Problem:High' } }
    @{ Name = 'monitor-connection-wrong-type'; Mutate = { param($E) @($E.discovery.connections | Where-Object { $_.path -eq 'MonitorQuery' })[0].resource = (Get-TestIds).Workspace }
       Expect = @{ 'monitoring.connection' = 'Problem:High' } }
    @{ Name = 'monitor-component-not-found'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).AppInsights 404 }
       Expect = @{ 'monitoring.component' = 'Problem:High' }; Allow = @('monitoring.ampls', 'monitoring.amplsMode', 'monitoring.queryPath') }
    @{ Name = 'monitor-component-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).AppInsights 403 }
       Expect = @{ 'monitoring.component' = 'CouldNotCheck:Blocking' }; Allow = @('monitoring.ampls', 'monitoring.amplsMode', 'monitoring.queryPath') }
    @{ Name = 'monitor-component-classic'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).AppInsights).properties.Remove('WorkspaceResourceId') }
       Expect = @{ 'monitoring.component' = 'Problem:High' }; Allow = @('monitoring.ampls', 'monitoring.amplsMode', 'monitoring.queryPath') }
    @{ Name = 'monitor-workspace-not-found'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Workspace 404 }
       Expect = @{ 'monitoring.workspace' = 'Problem:High' }; Allow = @('monitoring.queryPath') }
    @{ Name = 'monitor-no-ampls'; Mutate = { param($E) Remove-MonitorScenarioAmpls $E }
       Expect = @{ 'monitoring.queryAccess' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    @{ Name = 'monitor-public-query'; Mutate = { param($E) $ids = Get-TestIds; Remove-MonitorScenarioAmpls $E
            (Get-EvData $E $ids.AppInsights).properties.publicNetworkAccessForQuery = 'Enabled'; (Get-EvData $E $ids.Workspace).properties.publicNetworkAccessForQuery = 'Enabled' }
       Expect = @{ 'monitoring.queryAccess' = 'OK'; 'monitoring.queryPath' = 'OK' } }
    @{ Name = 'monitor-ampls-not-found'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Ampls 404 }
       Expect = @{ 'monitoring.ampls' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    @{ Name = 'monitor-ampls-scope-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).Ampls)/scopedResources" 403 }
       Expect = @{ 'monitoring.ampls' = 'CouldNotCheck:Blocking'; 'monitoring.queryPath' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'monitor-workspace-not-scoped'; Mutate = { param($E) $p = "$((Get-TestIds).Ampls)/scopedResources"; Set-EvRequest $E $p @(@(Get-EvData $E $p) | Where-Object { $_.name -ne 'law' }) }
       Expect = @{ 'monitoring.ampls' = 'Problem:High'; 'monitoring.amplsMode' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    @{ Name = 'monitor-component-not-scoped-open'; Mutate = { param($E) $ids = Get-TestIds; $p = "$($ids.Ampls)/scopedResources"
            Set-EvRequest $E $p @(@(Get-EvData $E $p) | Where-Object { $_.name -ne 'appi' })
            (Get-EvData $E $ids.Ampls).properties.accessModeSettings.queryAccessMode = 'Open'
            (Get-EvData $E $ids.AppInsights).properties.publicNetworkAccessForQuery = 'Enabled'; (Get-EvData $E $ids.Workspace).properties.publicNetworkAccessForQuery = 'Enabled' }
       Expect = @{ 'monitoring.ampls' = 'Problem:Medium'; 'monitoring.amplsMode' = 'Problem:Low'; 'monitoring.queryPath' = 'OK' } }
    @{ Name = 'monitor-ampls-open'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Ampls).properties.accessModeSettings.queryAccessMode = 'Open' }
       Expect = @{ 'monitoring.amplsMode' = 'Problem:Low' } }
    @{ Name = 'monitor-ampls-no-pe'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Ampls).properties.privateEndpointConnections = @() }
       Expect = @{ 'monitoring.amplsPe' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    @{ Name = 'monitor-ampls-no-pe-public-query'; Mutate = { param($E) Set-DiagTestMonitorPublic $E }
       Expect = @{ 'monitoring.amplsPe' = 'OK'; 'monitoring.queryPath' = 'OK'; 'monitoring.amplsMode' = 'Problem:Low' } }
    @{ Name = 'monitor-ampls-no-monitor-zone'; Mutate = { param($E) Remove-MonitorScenarioZone $E 'privatelink.monitor.azure.com' }
       Expect = @{ 'monitoring.amplsPe' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    @{ Name = 'monitor-ampls-no-oms-zone'; Mutate = { param($E) Remove-MonitorScenarioZone $E 'privatelink.oms.opinsights.azure.com' }
       Expect = @{ 'monitoring.amplsPe' = 'Problem:Low' } }
    @{ Name = 'monitor-ampls-zone-group-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).PeAmpls)/privateDnsZoneGroups" 403 }
       Expect = @{ 'monitoring.amplsPe' = 'CouldNotCheck:Blocking'; 'monitoring.queryPath' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'monitor-api-record-other-scope'; Mutate = { param($E) $p = "$((Get-TestIds).Zones)/privatelink.monitor.azure.com/A"
            @(Get-EvData $E $p | Where-Object { $_.name -eq 'api' })[0].properties.aRecords = @(@{ ipv4Address = '10.9.0.4' }) }
       Expect = @{ 'monitoring.amplsDnsOwner' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    @{ Name = 'monitor-api-record-missing'; Mutate = { param($E) $p = "$((Get-TestIds).Zones)/privatelink.monitor.azure.com/A"
            Set-EvRequest $E $p @(@(Get-EvData $E $p) | Where-Object { $_.name -ne 'api' }) }
       Expect = @{ 'monitoring.amplsDnsOwner' = 'Problem:High'; 'monitoring.queryPath' = 'Problem:High' } }
    # Azure drops zone-group names from customDnsConfigs; the api IP must come from the zone group record sets.
    @{ Name = 'monitor-api-ip-only-in-zone-group'; Mutate = { param($E)
            (Get-EvData $E (Get-TestIds).PeAmpls).properties.customDnsConfigs = @([ordered]@{ fqdn = 'scadvisorcontentpl.blob.core.windows.net'; ipAddresses = @('10.1.2.99') }) }
       Expect = @{ 'monitoring.amplsDnsOwner' = 'OK'; 'monitoring.queryPath' = 'OK' } }
)
