# DNS checks: private DNS zone groups, zone links, A records and custom resolvers. What this machine resolves is a Probe check.

$script:DiagPrivateLinkSuffixes = @(
    'services.ai.azure.com', 'openai.azure.com', 'cognitiveservices.azure.com',
    'blob.core.windows.net', 'file.core.windows.net', 'queue.core.windows.net', 'table.core.windows.net', 'dfs.core.windows.net',
    'monitor.azure.com', 'oms.opinsights.azure.com', 'ods.opinsights.azure.com', 'agentsvc.azure-automation.net')
# Public hosts that resolve through another private link name (CNAME).
$script:DiagDnsAliases = @{ 'api.loganalytics.io' = 'api.monitor.azure.com'; 'api.applicationinsights.io' = 'api.monitor.azure.com' }
$script:AzureDnsIp = '168.63.129.16'

# Maps a host to its private DNS zone and record name, e.g. acct.services.ai.azure.com -> privatelink.services.ai.azure.com / acct.
function Get-DiagDnsZoneFor {
    param([string]$HostName, [string[]]$ExtraSuffixes = @())
    $h = ConvertTo-DiagPublicHost $HostName
    if (!$h) { return $null }
    $best = $null
    foreach ($s in @($script:DiagPrivateLinkSuffixes) + @($ExtraSuffixes)) {
        if ($s -and $h.EndsWith(".$s") -and (!$best -or $s.Length -gt $best.Length)) { $best = $s }
    }
    if (!$best) { return $null }
    @{ Host = $h; Zone = "privatelink.$best"; Record = $h.Substring(0, $h.Length - $best.Length - 1) }
}

function Get-DiagCustomDnsServers {
    param($VnetRead)
    if (!$VnetRead.Ok) { return @() }
    @($VnetRead.Data.properties.dhcpOptions.dnsServers | Where-Object { $_ -and $_ -ne $script:AzureDnsIp })
}

function Test-DiagDnsVnetLink {
    param($Evidence, [string]$ZoneId, [string]$AgentVnet, [string[]]$CustomServers, [string]$Path)
    $zone = Get-ArmName $ZoneId
    $common = @{ Id = 'dns.vnetLink'; Area = 'Dns'; Title = "Private DNS zone link for $zone"; Layer = 'Name'; Path = $Path; Resource = $ZoneId }
    $links = Get-Ev $Evidence "$ZoneId/virtualNetworkLinks"
    $gap = New-ReadGap $links @common -What "the virtual network links of zone '$zone'"
    if ($gap) { return $gap }
    $items = @($links.Data | Where-Object { $_ })
    $refs = @(Get-EvRef $links)
    $agentVnetName = Get-ArmName $AgentVnet
    $link = @($items | Where-Object { Test-SameArmId $_.properties.virtualNetwork.id $AgentVnet })[0]
    $linked = @($items | ForEach-Object { "'$(Get-ArmName $_.properties.virtualNetwork.id)'" })
    if ($link) {
        $state = $link.properties.virtualNetworkLinkState
        if ($state -and $state -ne 'Completed') {
            return New-DiagResult @common -Status Problem -Severity Medium -Seen "Zone '$zone' link '$($link.name)' to virtual network '$agentVnetName' is $state." -Owner NetworkTeam `
                -Action "Wait for the link to finish, or recreate the virtual network link from zone '$zone' to '$agentVnetName'." -Evidence $refs
        }
        return New-DiagResult @common -Status OK -Seen "Zone '$zone' is linked to the agent virtual network '$agentVnetName'." -Evidence $refs
    }
    if ($CustomServers.Count -and $items.Count) {
        return New-DiagResult @common -Status CouldNotCheck -Gap KnownLimit `
            -Seen "Zone '$zone' is linked to $($linked -join ', '), not to the agent virtual network; the agent uses custom DNS servers $($CustomServers -join ', ')." `
            -Needs "Confirm that DNS servers $($CustomServers -join ', ') run in, or forward to a resolver in, one of these virtual networks: $($linked -join ', ')." -Evidence $refs
    }
    New-DiagResult @common -Status Problem -Severity High `
        -Seen $(if ($items.Count) { "Zone '$zone' is linked to $($linked -join ', ') but not to the agent virtual network '$agentVnetName'." } else { "Zone '$zone' isn't linked to any virtual network." }) `
        -Likely 'Consistent with the agent resolving the public address and being refused.' -Owner NetworkTeam `
        -Action "Link private DNS zone '$zone' to virtual network '$agentVnetName'$(if ($CustomServers.Count) { ' (or to the virtual network of your DNS resolver)' })." -Evidence $refs
}

function Test-DiagDnsRecord {
    param($Evidence, [string]$ZoneId, $HostZone, [string[]]$Expected, [string]$Path)
    $zone = Get-ArmName $ZoneId
    $recordId = "$ZoneId/A/$($HostZone.Record)"
    $common = @{ Id = 'dns.record'; Area = 'Dns'; Title = "DNS record for $($HostZone.Host)"; Layer = 'Name'; Path = $Path; Resource = $recordId }
    $read = Get-Ev $Evidence "$ZoneId/A"
    $gap = New-ReadGap $read @common -What "the A records of zone '$zone'"
    if ($gap) { return $gap }
    $refs = @(Get-EvRef $read)
    $record = @($read.Data | Where-Object { $_ -and ($_.name -ieq $HostZone.Record -or (ConvertTo-DiagPublicHost $_.properties.fqdn) -eq $HostZone.Host) })[0]
    $ips = @($record.properties.aRecords | ForEach-Object { $_.ipv4Address } | Where-Object { $_ })
    $details = @{ zone = $zone; record = $HostZone.Record; addresses = $ips; expected = $Expected }
    if (!$record -or !$ips.Count) {
        return New-DiagResult @common -Status Problem -Severity High -Seen "Zone '$zone' has no A record '$($HostZone.Record)' for $($HostZone.Host)." `
            -Likely 'Consistent with the agent resolving the public address and being refused.' -Owner NetworkTeam `
            -Action "Add A record '$($HostZone.Record)' pointing to $(if ($Expected.Count) { $Expected -join ', ' } else { "the private endpoint's IP" }) in zone '$zone' (or recreate the private endpoint's DNS zone group)." `
            -Evidence $refs -Details $details
    }
    if (!$Expected.Count) {
        return New-DiagResult @common -Status CouldNotCheck -Gap KnownLimit -Seen "Record '$($HostZone.Record)' in zone '$zone' points to $($ips -join ', '); the private endpoint's IP for this host is unknown." `
            -Needs "Compare the record with the private endpoint's DNS configuration in the portal." -Evidence $refs -Details $details
    }
    $missing = @($Expected | Where-Object { $_ -notin $ips })
    if ($missing.Count) {
        return New-DiagResult @common -Status Problem -Severity High -Seen "Record '$($HostZone.Record)' in zone '$zone' points to $($ips -join ', '); the private endpoint uses $($Expected -join ', ')." `
            -Likely 'Consistent with a stale record left from a deleted or recreated private endpoint.' -Owner NetworkTeam `
            -Action "Update A record '$($HostZone.Record)' in zone '$zone' to $($Expected -join ', ')." -Evidence $refs -Details $details
    }
    New-DiagResult @common -Status OK -Seen "$($HostZone.Host) points to $($ips -join ', ') in zone '$zone'." -Evidence $refs -Details $details
}

function Test-DiagDns {
    param($Evidence)
    $out = [Collections.Generic.List[object]]::new()
    $agentSubnet = $Evidence.discovery.agentSubnet
    $agentVnet = if ($agentSubnet) { Get-ArmParent $agentSubnet } else { $null }
    $vnet = if ($agentVnet) { Get-Ev $Evidence $agentVnet } else { $null }
    $custom = @(if ($vnet) { Get-DiagCustomDnsServers $vnet })
    $privatePaths = @{}
    $allZones = [ordered]@{}
    $done = @{}

    foreach ($dep in Get-DiagPeDependencies $Evidence) {
        if ((Get-Ev $Evidence $dep.resource).NotFound) { continue }
        $peIds = @(Get-DiagPeIds $dep (Get-DiagPeConnections $Evidence $dep) | Where-Object { !(Get-Ev $Evidence $_).NotFound })
        if (!$peIds.Count) { continue }
        $path = $dep.path
        $privatePaths[$path] = $true
        $kind = $script:DiagPeKindLabels[$dep.kind]
        $label = "$($script:DiagPeKindPhrases[$dep.kind]) '$(Get-ArmName $dep.resource)'"
        $addresses = Get-DiagDependencyAddresses $Evidence $peIds

        # dns.zoneGroup — the private endpoints register their records in the private DNS zones the hosts need.
        $title = "$kind private DNS zone group"
        $zones = [ordered]@{}
        $gap = $null
        $refs = @()
        foreach ($peId in $peIds) {
            $groups = Get-Ev $Evidence "$peId/privateDnsZoneGroups"
            if (!$gap) { $gap = New-ReadGap $groups -Id dns.zoneGroup -Area Dns -Title $title -Layer Name -Path $path -Resource $dep.resource -What "the DNS zone groups of private endpoint '$(Get-ArmName $peId)'" }
            if (!$groups.Ok) { continue }
            $refs += Get-EvRef $groups
            foreach ($group in @($groups.Data | Where-Object { $_ })) {
                foreach ($config in @($group.properties.privateDnsZoneConfigs | Where-Object { $_ })) {
                    $zoneId = $config.properties.privateDnsZoneId
                    if ($zoneId) { $zones[(Get-ArmName $zoneId).ToLowerInvariant()] = $zoneId }
                }
            }
        }
        $extra = @($zones.Keys | Where-Object { $_ -like 'privatelink.*' } | ForEach-Object { $_.Substring(12) })
        # Evaluations only query through the scope; its ingestion and solution-pack zones are monitoring.amplsPe's concern.
        $depHosts = $(if ($dep.kind -eq 'Ampls') { @('api.monitor.azure.com') } else { @($dep.hosts) })
        $hostZones = @($depHosts | Where-Object { $_ } | ForEach-Object { Get-DiagDnsZoneFor $_ $extra } | Where-Object { $_ })
        $required = @($hostZones | ForEach-Object { $_.Zone } | Select-Object -Unique)
        $missing = @($required | Where-Object { !$zones.Contains($_) })
        $peNames = ($peIds | ForEach-Object { "'$(Get-ArmName $_)'" }) -join ', '
        if ($gap) { $out.Add($gap) }
        elseif ($missing.Count) {
            $out.Add((New-DiagResult -Id dns.zoneGroup -Area Dns -Title $title -Status Problem -Severity $(if ($custom.Count) { 'Medium' } else { 'High' }) -Layer Name -Path $path -Resource $dep.resource `
                -Seen "Private endpoint $peNames for the $label has no DNS zone group entry for $(($missing | ForEach-Object { "'$_'" }) -join ', ')." `
                -Likely $(if ($custom.Count) { $null } else { 'Consistent with the agent resolving the public address and being refused.' }) -Owner NetworkTeam `
                -Action "Add $(($missing | ForEach-Object { "'$_'" }) -join ', ') to the private endpoint's DNS zone group$(if ($custom.Count) { ', or confirm your DNS servers hold these records' })." `
                -Evidence $refs -Details @{ required = $required; present = @($zones.Keys) }))
        }
        else {
            $out.Add((New-DiagResult -Id dns.zoneGroup -Area Dns -Title $title -Status OK -Layer Name -Path $path -Resource $dep.resource `
                -Seen "Private endpoint $peNames registers in $(($zones.Keys | ForEach-Object { "'$_'" }) -join ', ')." -Evidence $refs -Details @{ required = $required; present = @($zones.Keys) }))
        }

        # dns.vnetLink and dns.record for the zones these hosts use.
        $relevant = if ($hostZones.Count) { @($required | Where-Object { $zones.Contains($_) }) } else { @($zones.Keys) }
        foreach ($zoneName in $relevant) {
            $zoneId = $zones[$zoneName]
            $allZones[$zoneName] = $zoneId
            $key = "$($zoneId.ToLowerInvariant())|$path"
            if ($agentVnet -and !$done.ContainsKey("link|$key")) {
                $done["link|$key"] = $true
                $out.Add((Test-DiagDnsVnetLink $Evidence $zoneId $agentVnet $custom $path))
            }
            foreach ($hz in @($hostZones | Where-Object { $_.Zone -eq $zoneName })) {
                $recordKey = "record|$($hz.Host)|$path"
                if ($done.ContainsKey($recordKey)) { continue }
                $done[$recordKey] = $true
                $result = Test-DiagDnsRecord $Evidence $zoneId $hz @($addresses[$hz.Host] | Where-Object { $_ }) $path
                # One read gap per zone, not per record.
                if ($result.status -eq 'CouldNotCheck' -and $result.gap -eq 'Blocking') {
                    if ($done.ContainsKey("recordgap|$key")) { continue }
                    $done["recordgap|$key"] = $true
                    $result.resource = "$zoneId/A"; $result.key = "dns.record|$zoneId/A|$path"; $result.title = "DNS records in $zoneName"
                }
                $out.Add($result)
            }
        }
    }

    # dns.customResolver — custom DNS servers: their forwarding can't be read from Azure.
    if ($privatePaths.Count -and $vnet -and $vnet.Ok) {
        $common = @{ Id = 'dns.customResolver'; Area = 'Dns'; Title = 'Custom DNS servers for private zones'; Layer = 'Name'; Resource = $agentVnet }
        if ($custom.Count) {
            $zoneList = ($allZones.Keys | ForEach-Object { "'$_'" }) -join ', '
            $out.Add((New-DiagResult @common -Status CouldNotCheck -Gap KnownLimit `
                -Seen "Virtual network '$(Get-ArmName $agentVnet)' uses custom DNS servers $($custom -join ', '); the diagnostic can't read how they forward private zones." `
                -Needs "Confirm DNS servers $($custom -join ', ') forward $(if ($zoneList) { $zoneList } else { 'the privatelink zones' }) (or the parent public zones) to Azure DNS $script:AzureDnsIp from a virtual network linked to those zones." `
                -Evidence @(Get-EvRef $vnet) -Details @{ dnsServers = $custom; zones = @($allZones.Keys) }))
        }
        else {
            $out.Add((New-DiagResult @common -Status OK -Seen "Virtual network '$(Get-ArmName $agentVnet)' uses Azure-provided DNS, which answers from linked private zones." -Evidence @(Get-EvRef $vnet)))
        }
    }

    , $out.ToArray()
}
