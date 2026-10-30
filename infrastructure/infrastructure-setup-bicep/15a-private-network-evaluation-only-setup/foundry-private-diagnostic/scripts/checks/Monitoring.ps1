# Monitoring checks: the Application Insights component, its Log Analytics workspace and the Azure Monitor
# private link scope (AMPLS) that evaluation trace queries (api.loganalytics.io, api.applicationinsights.io) go through.

$script:MonitorQueryZone = 'privatelink.monitor.azure.com'
$script:MonitorOtherZones = @('privatelink.oms.opinsights.azure.com', 'privatelink.ods.opinsights.azure.com', 'privatelink.agentsvc.azure-automation.net')

function Get-MonitorScopeIds {
    param($Evidence, $ComponentData, $WorkspaceData)
    $ids = [ordered]@{}
    foreach ($dep in @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.kind -eq 'Ampls' -and $_.resource })) { $ids[$dep.resource.ToLowerInvariant()] = $dep.resource }
    $links = @($ComponentData.properties.privateLinkScopedResources) + @($WorkspaceData.properties.privateLinkScopedResources)
    foreach ($link in $links) {
        if (!$link) { continue }
        $rid = $(if ($link.ResourceId) { $link.ResourceId } else { $link.resourceId })
        if ($rid -match '(?i)^(/subscriptions/[^/]+/resourceGroups/[^/]+/providers/microsoft\.insights/privatelinkscopes/[^/]+)') {
            if (!$ids.Contains($Matches[1].ToLowerInvariant())) { $ids[$Matches[1].ToLowerInvariant()] = $Matches[1] }
        }
    }
    @($ids.Values)
}

function Get-MonitorZoneName {
    param($Config)
    $zoneId = $Config.properties.privateDnsZoneId
    $(if ($zoneId) { (Get-ArmName $zoneId).ToLowerInvariant() } elseif ($Config.name) { $Config.name.ToLowerInvariant() })
}

function Test-DiagMonitoring {
    param($Evidence)
    if (!(Test-DiagPathUsed $Evidence 'MonitorQuery')) { return , @() }
    $out = [Collections.Generic.List[object]]::new()
    $P = 'MonitorQuery'
    $conn = @($Evidence.discovery.connections | Where-Object { $_ -and $_.path -eq $P })[0]
    $aiId = $conn.resource

    # monitoring.connection — the Application Insights connection resolves to a component.
    $title = 'Application Insights connection target'
    if (!$conn -or !$aiId) {
        $out.Add((New-DiagResult -Id monitoring.connection -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $Evidence.discovery.project `
            -Seen $(if ($conn) { "Connection '$($conn.name)' has no Application Insights resource ID." } else { 'The project has no Application Insights connection.' }) -Owner Customer `
            -Action 'Add (or fix) the project Application Insights connection so it references the component by its resource ID.' -Details @{ connection = $conn.name }))
        return , $out.ToArray()
    }
    if ($aiId -notmatch '(?i)/providers/Microsoft\.Insights/components/[^/]+$') {
        $out.Add((New-DiagResult -Id monitoring.connection -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $aiId `
            -Seen "Connection '$($conn.name)' points at '$(Get-ArmName $aiId)', which is not an Application Insights component." -Owner Customer `
            -Action "Point connection '$($conn.name)' at the resource ID of the Application Insights component." -Details @{ connection = $conn.name; resource = $aiId }))
        return , $out.ToArray()
    }
    $aiName = Get-ArmName $aiId
    $out.Add((New-DiagResult -Id monitoring.connection -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $aiId `
        -Seen "Connection '$($conn.name)' points at Application Insights '$aiName'." -Details @{ connection = $conn.name }))

    # monitoring.component — exists and is workspace-based.
    $ai = Get-Ev $Evidence $aiId
    $title = 'Application Insights component'
    $workspaceId = $null
    $gap = New-ReadGap $ai -Id monitoring.component -Area Monitoring -Title $title -Layer Config -Path $P -Resource $aiId -What "Application Insights '$aiName'"
    if ($gap) { $out.Add($gap) }
    elseif ($ai.NotFound) {
        $out.Add((New-DiagResult -Id monitoring.component -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $aiId `
            -Seen "Application Insights '$aiName' was not found." -Owner Customer `
            -Action "Recreate Application Insights '$aiName' or point connection '$($conn.name)' at an existing component." -Evidence @(Get-EvRef $ai)))
    }
    else {
        $workspaceId = $ai.Data.properties.WorkspaceResourceId
        $state = $ai.Data.properties.provisioningState
        if (!$workspaceId) {
            $out.Add((New-DiagResult -Id monitoring.component -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $aiId `
                -Seen "Application Insights '$aiName' is a classic component with no Log Analytics workspace." -Owner ResourceOwner `
                -Action "Migrate Application Insights '$aiName' to a workspace-based component." -Evidence @(Get-EvRef $ai)))
        }
        elseif ($state -and $state -ne 'Succeeded') {
            $out.Add((New-DiagResult -Id monitoring.component -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $aiId `
                -Seen "Application Insights '$aiName' is in state '$state'." -Owner ResourceOwner `
                -Action "Wait for Application Insights '$aiName' to finish provisioning, or check its deployment error." -Evidence @(Get-EvRef $ai) -Details @{ provisioningState = $state }))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.component -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $aiId `
                -Seen "Application Insights '$aiName' is workspace-based (workspace '$(Get-ArmName $workspaceId)')." -Evidence @(Get-EvRef $ai) -Details @{ workspace = $workspaceId }))
        }
    }
    if (!$workspaceId) {
        $workspaceId = @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.kind -eq 'Workspace' -and $_.resource })[0].resource
    }

    # monitoring.workspace — the Log Analytics workspace exists.
    $law = Get-Ev $Evidence $workspaceId
    if ($workspaceId) {
        $lawName = Get-ArmName $workspaceId
        $title = 'Log Analytics workspace'
        $gap = New-ReadGap $law -Id monitoring.workspace -Area Monitoring -Title $title -Layer Config -Path $P -Resource $workspaceId -What "Log Analytics workspace '$lawName'"
        if ($gap) { $out.Add($gap) }
        elseif ($law.NotFound) {
            $out.Add((New-DiagResult -Id monitoring.workspace -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $workspaceId `
                -Seen "Log Analytics workspace '$lawName' used by Application Insights '$aiName' was not found." -Owner ResourceOwner `
                -Action "Link Application Insights '$aiName' to an existing Log Analytics workspace." -Evidence @(Get-EvRef $law)))
        }
        elseif ($law.Data.properties.provisioningState -and $law.Data.properties.provisioningState -ne 'Succeeded') {
            $state = $law.Data.properties.provisioningState
            $out.Add((New-DiagResult -Id monitoring.workspace -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $workspaceId `
                -Seen "Log Analytics workspace '$lawName' is in state '$state'." -Owner ResourceOwner `
                -Action "Wait for workspace '$lawName' to finish provisioning, or check its deployment error." -Evidence @(Get-EvRef $law) -Details @{ provisioningState = $state }))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.workspace -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $workspaceId `
                -Seen "Log Analytics workspace '$lawName' exists." -Evidence @(Get-EvRef $law)))
        }
    }

    $aiData = $(if ($ai.Ok) { $ai.Data })
    $lawData = $(if ($law.Ok) { $law.Data })
    $aiQuery = $aiData.properties.publicNetworkAccessForQuery
    $lawQuery = $lawData.properties.publicNetworkAccessForQuery
    $scopeIds = @(Get-MonitorScopeIds $Evidence $aiData $lawData)

    # monitoring.queryAccess — public query disabled needs a private path (AMPLS).
    if ($ai.Ok) {
        $title = 'Monitor query network access'
        $disabled = @($(if ($aiQuery -eq 'Disabled') { "Application Insights '$aiName'" }), $(if ($lawQuery -eq 'Disabled') { "workspace '$(Get-ArmName $workspaceId)'" }) | Where-Object { $_ })
        $queryRefs = @((Get-EvRef $ai)) + @($(if ($law.Ok) { Get-EvRef $law }))
        $details = @{ appInsightsQuery = $aiQuery; workspaceQuery = $lawQuery; privateLinkScopes = $scopeIds }
        if ($disabled.Count -and !$scopeIds.Count) {
            $out.Add((New-DiagResult -Id monitoring.queryAccess -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $aiId `
                -Seen "Public query access is disabled on $($disabled -join ' and '), and they are not in an Azure Monitor private link scope." -Owner AzureAdmin `
                -Likely 'Consistent with evaluation trace queries being rejected (403).' `
                -Action "Add Application Insights '$aiName' and its workspace to an Azure Monitor private link scope with a private endpoint in the agent network, or enable public query access." `
                -Evidence $queryRefs -Details $details))
        }
        else {
            $seen = if ($disabled.Count) { "Public query access is disabled on $($disabled -join ' and '); queries use the private link scope." }
            elseif ($scopeIds.Count) { 'Public query access is enabled; a private link scope is also configured.' }
            else { 'Public query access is enabled; queries use the public endpoints.' }
            $out.Add((New-DiagResult -Id monitoring.queryAccess -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $aiId -Seen $seen -Evidence $queryRefs -Details $details))
        }
    }

    # Per-AMPLS checks.
    $privateRoute = $false
    $privateUnknown = $false
    $privateOnlyScope = $false
    foreach ($scopeId in $scopeIds) {
        $sName = Get-ArmName $scopeId
        $scope = Get-Ev $Evidence $scopeId
        $scoped = Get-Ev $Evidence "$scopeId/scopedResources"

        # monitoring.ampls — exists and scopes both the component and the workspace.
        $title = 'Azure Monitor private link scope resources'
        $gap = New-ReadGap $scope -Id monitoring.ampls -Area Monitoring -Title $title -Layer Config -Path $P -Resource $scopeId -What "private link scope '$sName'"
        if (!$gap) { $gap = New-ReadGap $scoped -Id monitoring.ampls -Area Monitoring -Title $title -Layer Config -Path $P -Resource $scopeId -What "the scoped resources of private link scope '$sName'" }
        if ($gap) { $out.Add($gap); $privateUnknown = $true; continue }
        if ($scope.NotFound) {
            $out.Add((New-DiagResult -Id monitoring.ampls -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $scopeId `
                -Seen "Private link scope '$sName' referenced by Application Insights '$aiName' was not found." -Owner AzureAdmin `
                -Action "Add Application Insights '$aiName' and its workspace to an existing Azure Monitor private link scope." -Evidence @(Get-EvRef $scope)))
            continue
        }
        $linked = @($(if ($scoped.Ok) { @($scoped.Data | ForEach-Object { $_.properties.linkedResourceId } | Where-Object { $_ }) }))
        $aiScoped = [bool]@($linked | Where-Object { Test-SameArmId $_ $aiId }).Count
        $lawScoped = (!$workspaceId) -or [bool]@($linked | Where-Object { Test-SameArmId $_ $workspaceId }).Count
        $sp = $scope.Data.properties
        $queryMode = $sp.accessModeSettings.queryAccessMode
        $ingestMode = $sp.accessModeSettings.ingestionAccessMode
        if ($queryMode -eq 'PrivateOnly') { $privateOnlyScope = $true }
        $missing = @($(if (!$aiScoped) { "Application Insights '$aiName'" }), $(if (!$lawScoped) { "workspace '$(Get-ArmName $workspaceId)'" }) | Where-Object { $_ })
        $refs = @((Get-EvRef $scope), (Get-EvRef $scoped))
        if ($missing.Count) {
            $strict = $queryMode -eq 'PrivateOnly' -or $aiQuery -eq 'Disabled' -or $lawQuery -eq 'Disabled'
            $out.Add((New-DiagResult -Id monitoring.ampls -Area Monitoring -Title $title -Status Problem -Severity $(if ($strict) { 'High' } else { 'Medium' }) -Path $P -Layer Config -Resource $scopeId `
                -Seen "Private link scope '$sName' doesn't include $($missing -join ' or ')." -Owner AzureAdmin `
                -Likely $(if ($strict) { 'Consistent with evaluation trace queries being rejected (403).' } else { 'Consistent with trace queries leaving the private network.' }) `
                -Action "Add $($missing -join ' and ') to private link scope '$sName'." -Evidence $refs -Details @{ linkedResources = $linked; queryAccessMode = $queryMode }))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.ampls -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $scopeId `
                -Seen "Private link scope '$sName' includes Application Insights '$aiName' and its workspace." -Evidence $refs -Details @{ linkedResources = $linked }))
        }

        # monitoring.amplsMode — access modes.
        $title = 'Azure Monitor private link scope access mode'
        $modeDetails = @{ queryAccessMode = $queryMode; ingestionAccessMode = $ingestMode }
        if ($queryMode -eq 'PrivateOnly' -and $missing.Count) {
            $out.Add((New-DiagResult -Id monitoring.amplsMode -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $scopeId `
                -Seen "Private link scope '$sName' only allows queries to resources in the scope, and $($missing -join ' and ') aren't in it." -Owner AzureAdmin `
                -Likely 'Consistent with evaluation trace queries being rejected (403).' `
                -Action "Add $($missing -join ' and ') to private link scope '$sName' (or set its query access mode to Open)." -Evidence @(Get-EvRef $scope) -Details $modeDetails))
        }
        elseif ($queryMode -eq 'Open' -or $ingestMode -eq 'Open') {
            $open = @($(if ($queryMode -eq 'Open') { 'query' }), $(if ($ingestMode -eq 'Open') { 'ingestion' }) | Where-Object { $_ })
            $out.Add((New-DiagResult -Id monitoring.amplsMode -Area Monitoring -Title $title -Status Problem -Severity Low -Path $P -Layer Config -Resource $scopeId `
                -Seen "Private link scope '$sName' uses Open $($open -join ' and ') access, so traffic to resources outside the scope can still leave the private network." -Owner AzureAdmin `
                -Action "Set the $($open -join ' and ') access mode of private link scope '$sName' to Private Only once every resource the network uses is in the scope." `
                -Evidence @(Get-EvRef $scope) -Details $modeDetails))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.amplsMode -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $scopeId `
                -Seen "Private link scope '$sName' query access: $queryMode; ingestion access: $ingestMode." -Evidence @(Get-EvRef $scope) -Details $modeDetails))
        }

        # monitoring.amplsPe — a private endpoint with the Azure Monitor zones.
        $title = 'Azure Monitor private endpoint and DNS zones'
        $peIds = @($sp.privateEndpointConnections | Where-Object { $_ -and $_.properties.privateEndpoint.id } | Sort-Object { $_.properties.privateLinkServiceConnectionState.status -ne 'Approved' } | ForEach-Object { $_.properties.privateEndpoint.id })
        $approved = [bool]@($sp.privateEndpointConnections | Where-Object { $_ -and $_.properties.privateLinkServiceConnectionState.status -eq 'Approved' }).Count
        if (!$peIds.Count) {
            $publicHere = $queryMode -ne 'PrivateOnly' -and $aiQuery -eq 'Enabled' -and ($lawQuery -eq 'Enabled' -or !$workspaceId)
            if ($publicHere) {
                $out.Add((New-DiagResult -Id monitoring.amplsPe -Area Monitoring -Title $title -Status OK -Path $P -Layer Name -Resource $scopeId `
                    -Seen "Private link scope '$sName' has no private endpoint; trace queries use the public endpoints." -Evidence @(Get-EvRef $scope)))
                continue
            }
            $out.Add((New-DiagResult -Id monitoring.amplsPe -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Name -Resource $scopeId `
                -Seen "Private link scope '$sName' has no private endpoint." -Owner NetworkTeam `
                -Likely 'Consistent with evaluation trace queries failing from the agent network.' `
                -Action "Create a private endpoint for private link scope '$sName' in a subnet the agent subnet can reach, with the privatelink.monitor.azure.com, oms, ods and agentsvc zones." `
                -Evidence @(Get-EvRef $scope)))
            continue
        }
        $peId = $peIds[0]
        $groups = Get-Ev $Evidence "$peId/privateDnsZoneGroups"
        $gap = New-ReadGap $groups -Id monitoring.amplsPe -Area Monitoring -Title $title -Layer Name -Path $P -Resource $scopeId -What "the DNS zone group of private endpoint '$(Get-ArmName $peId)'"
        if ($gap) { $out.Add($gap); $privateUnknown = $true; continue }
        $configs = @($(if ($groups.Ok) { @($groups.Data | ForEach-Object { @($_.properties.privateDnsZoneConfigs) } | Where-Object { $_ }) }))
        $zones = @($configs | ForEach-Object { Get-MonitorZoneName $_ } | Where-Object { $_ } | Sort-Object -Unique)
        $peDetails = @{ privateEndpoint = $peId; zones = $zones }
        $hasQueryZone = $script:MonitorQueryZone -in $zones
        $otherMissing = @($script:MonitorOtherZones | Where-Object { $_ -notin $zones })
        if (!$hasQueryZone) {
            $out.Add((New-DiagResult -Id monitoring.amplsPe -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Name -Resource $scopeId `
                -Seen "Private endpoint '$(Get-ArmName $peId)' of private link scope '$sName' has no $script:MonitorQueryZone zone." -Owner NetworkTeam `
                -Likely 'Consistent with api.loganalytics.io and api.applicationinsights.io resolving to public addresses from the agent network.' `
                -Action "Add the $script:MonitorQueryZone zone to the DNS zone group of private endpoint '$(Get-ArmName $peId)' and link the zone to the agent virtual network." `
                -Evidence @((Get-EvRef $scope), (Get-EvRef $groups)) -Details $peDetails))
        }
        elseif ($otherMissing.Count) {
            $out.Add((New-DiagResult -Id monitoring.amplsPe -Area Monitoring -Title $title -Status Problem -Severity Low -Path $P -Layer Name -Resource $scopeId `
                -Seen "Private endpoint '$(Get-ArmName $peId)' has no $($otherMissing -join ', ') zone(s)." -Owner NetworkTeam `
                -Action "Add $($otherMissing -join ', ') to the DNS zone group of private endpoint '$(Get-ArmName $peId)'." `
                -Evidence @((Get-EvRef $scope), (Get-EvRef $groups)) -Details $peDetails))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.amplsPe -Area Monitoring -Title $title -Status OK -Path $P -Layer Name -Resource $scopeId `
                -Seen "Private endpoint '$(Get-ArmName $peId)' has the Azure Monitor zones." -Evidence @((Get-EvRef $scope), (Get-EvRef $groups)) -Details $peDetails))
        }
        if (!$hasQueryZone) { continue }

        # monitoring.amplsDnsOwner — the shared api record points at this scope's private endpoint.
        $title = 'Azure Monitor query DNS record owner'
        $zoneId = @($configs | Where-Object { (Get-MonitorZoneName $_) -eq $script:MonitorQueryZone } | ForEach-Object { $_.properties.privateDnsZoneId } | Where-Object { $_ })[0]
        $pe = Get-Ev $Evidence $peId
        $records = Get-Ev $Evidence "$zoneId/A"
        $gap = New-ReadGap $pe -Id monitoring.amplsDnsOwner -Area Monitoring -Title $title -Layer Name -Path $P -Resource $scopeId -What "private endpoint '$(Get-ArmName $peId)'"
        if (!$gap -and $zoneId) { $gap = New-ReadGap $records -Id monitoring.amplsDnsOwner -Area Monitoring -Title $title -Layer Name -Path $P -Resource $scopeId -What "the records of zone $script:MonitorQueryZone" }
        if ($gap) { $out.Add($gap); $privateUnknown = $true; continue }
        if (!$zoneId -or !$pe.Ok -or !$records.Ok) { $privateUnknown = $true; continue }
        # Azure drops zone-group names from customDnsConfigs, so the api IP usually comes from the zone group record sets.
        $peAddresses = Get-DiagPeAddresses $Evidence $peId
        $peIps = @($peAddresses['api.monitor.azure.com'] | Where-Object { $_ })
        if (!$peIps.Count) { $peIps = @($peAddresses.Values | ForEach-Object { @($_) } | Where-Object { $_ } | Select-Object -Unique) }
        $api = @($records.Data | Where-Object { $_ -and $_.name -ieq 'api' })[0]
        $recordIps = @($api.properties.aRecords | ForEach-Object { $_.ipv4Address } | Where-Object { $_ })
        $dnsDetails = @{ zone = $zoneId; recordIps = $recordIps; privateEndpointIps = $peIps }
        $refs = @((Get-EvRef $pe), (Get-EvRef $records))
        if (!$recordIps.Count) {
            $out.Add((New-DiagResult -Id monitoring.amplsDnsOwner -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Name -Resource $scopeId `
                -Seen "Zone $script:MonitorQueryZone has no 'api' record, so api.loganalytics.io and api.applicationinsights.io don't resolve to private link scope '$sName'." -Owner NetworkTeam `
                -Action "Recreate the DNS zone group of private endpoint '$(Get-ArmName $peId)' so it writes the 'api' record." -Evidence $refs -Details $dnsDetails))
        }
        elseif ($peIps.Count -and !@($recordIps | Where-Object { $_ -in $peIps }).Count) {
            $out.Add((New-DiagResult -Id monitoring.amplsDnsOwner -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Name -Resource $scopeId `
                -Seen "The 'api' record in zone $script:MonitorQueryZone points at $($recordIps -join ', '), not at private endpoint '$(Get-ArmName $peId)' ($($peIps -join ', ')) of private link scope '$sName'." `
                -Likely 'Consistent with another private link scope owning the shared Azure Monitor DNS records, so queries reach a scope that does not include these resources.' -Owner NetworkTeam `
                -Action "Use a single Azure Monitor private link scope per DNS zone: add Application Insights '$aiName' and its workspace to the scope that owns the record, or point the record back at '$(Get-ArmName $peId)'." `
                -Evidence $refs -Details $dnsDetails))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.amplsDnsOwner -Area Monitoring -Title $title -Status OK -Path $P -Layer Name -Resource $scopeId `
                -Seen "The 'api' record points at private endpoint '$(Get-ArmName $peId)' ($($recordIps -join ', '))." -Evidence $refs -Details $dnsDetails))
            if (!$missing.Count -and $approved) { $privateRoute = $true }
        }
    }

    # monitoring.queryPath — at least one complete route (private or public) for trace queries.
    if ($ai.Ok) {
        $title = 'Monitor query route'
        $publicRoute = $aiQuery -eq 'Enabled' -and ($lawQuery -eq 'Enabled' -or !$workspaceId) -and !$privateOnlyScope
        if ($privateRoute -or $publicRoute) {
            $out.Add((New-DiagResult -Id monitoring.queryPath -Area Monitoring -Title $title -Status OK -Path $P -Layer Config -Resource $aiId `
                -Seen $(if ($privateRoute) { 'Trace queries have a complete private route through the Azure Monitor private link scope.' } else { 'Trace queries can use the public endpoints.' }) `
                -Details @{ privateRoute = $privateRoute; publicRoute = $publicRoute }))
        }
        elseif ($privateUnknown -or ($workspaceId -and !$law.Ok)) {
            $out.Add((New-DiagResult -Id monitoring.queryPath -Area Monitoring -Title $title -Status CouldNotCheck -Gap Blocking -Path $P -Layer Config -Resource $aiId `
                -Seen 'Some Azure Monitor settings could not be read, so the query route could not be confirmed.' `
                -Needs 'Read access (Reader) on the Application Insights, workspace, private link scope and its private endpoint.' -Details @{ privateRoute = $false; publicRoute = $false }))
        }
        else {
            $out.Add((New-DiagResult -Id monitoring.queryPath -Area Monitoring -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $aiId `
                -Seen 'Neither a complete private route nor a public route is available for trace queries.' -Owner AzureAdmin `
                -Likely 'Consistent with evaluation trace queries failing.' `
                -Action 'Fix the Azure Monitor private link scope problems listed above, or enable public query access on Application Insights and its workspace.' `
                -Details @{ privateRoute = $false; publicRoute = $false; appInsightsQuery = $aiQuery; workspaceQuery = $lawQuery }))
        }
    }

    , $out.ToArray()
}
