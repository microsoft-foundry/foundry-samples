# Private endpoint checks: one set of results per dependency that can sit behind a private endpoint.
# The helpers here are also used by Dns.ps1 and Nsg.ps1.

$script:DiagPeKinds = @('Account', 'Storage', 'Ampls', 'Model')
$script:DiagPeKindLabels = @{ Account = 'Foundry account'; Storage = 'Storage account'; Ampls = 'Azure Monitor private link scope'; Model = 'Model resource' }
$script:DiagPeKindPhrases = @{ Account = 'Foundry account'; Storage = 'storage account'; Ampls = 'Azure Monitor private link scope'; Model = 'model resource' }

function Get-DiagPeDependencies {
    param($Evidence)
    @($Evidence.discovery.dependencies | Where-Object {
            $_ -and $_.kind -in $script:DiagPeKinds -and $_.resource -and (Test-DiagPathUsed $Evidence $_.path) })
}

function ConvertTo-DiagPublicHost {
    param([string]$Name)
    if (!$Name) { return $null }
    ($Name.Trim().TrimEnd('.') -replace '(?i)\.privatelink\.', '.').ToLowerInvariant()
}

# Private endpoint connections as seen by the target resource (AMPLS keeps them on the scope itself).
function Get-DiagPeConnections {
    param($Evidence, $Dependency)
    if ($Dependency.kind -eq 'Ampls') {
        $read = Get-Ev $Evidence $Dependency.resource
        $items = if ($read.Ok) { @($read.Data.properties.privateEndpointConnections) } else { @() }
    }
    else {
        $read = Get-Ev $Evidence "$($Dependency.resource)/privateEndpointConnections"
        $items = if ($read.Ok) { @($read.Data) } else { @() }
    }
    $list = foreach ($item in $items) {
        if ($item -and $item.properties.privateEndpoint.id) {
            @{ Pe = $item.properties.privateEndpoint.id; Status = $item.properties.privateLinkServiceConnectionState.status }
        }
    }
    @{ Read = $read; Items = @($list) }
}

function Get-DiagPeIds {
    param($Dependency, $Connections)
    $ids = [Collections.Generic.List[string]]::new()
    foreach ($id in @(@($Dependency.privateEndpoints) + @($Connections.Items | ForEach-Object { $_.Pe }))) {
        if ($id -and !@($ids | Where-Object { Test-SameArmId $_ $id }).Count) { $ids.Add($id) }
    }
    $ids.ToArray()
}

# Host -> private IPs served by one private endpoint, from its DNS configs and its zone group record sets.
function Get-DiagPeAddresses {
    param($Evidence, [string]$PeId)
    $map = @{}
    $add = {
        param($Name, $Ips)
        $h = ConvertTo-DiagPublicHost $Name
        if (!$h) { return }
        if (!$map.ContainsKey($h)) { $map[$h] = @() }
        $map[$h] = @(@($map[$h]) + @($Ips | Where-Object { $_ }) | Select-Object -Unique)
    }
    $pe = Get-Ev $Evidence $PeId
    if ($pe.Ok) { foreach ($c in @($pe.Data.properties.customDnsConfigs | Where-Object { $_ })) { & $add $c.fqdn @($c.ipAddresses) } }
    $groups = Get-Ev $Evidence "$PeId/privateDnsZoneGroups"
    if ($groups.Ok) {
        foreach ($group in @($groups.Data | Where-Object { $_ })) {
            foreach ($config in @($group.properties.privateDnsZoneConfigs | Where-Object { $_ })) {
                foreach ($set in @($config.properties.recordSets | Where-Object { $_ })) { & $add $set.fqdn @($set.ipAddresses) }
            }
        }
    }
    $map
}

# Host -> private IPs across every private endpoint of one dependency.
function Get-DiagDependencyAddresses {
    param($Evidence, [string[]]$PeIds)
    $all = @{}
    foreach ($peId in $PeIds) {
        $one = Get-DiagPeAddresses $Evidence $peId
        foreach ($h in $one.Keys) { $all[$h] = @(@($all[$h]) + @($one[$h]) | Where-Object { $_ } | Select-Object -Unique) }
    }
    $all
}

# Whether the target accepts public traffic: Disabled, Selected (firewall default deny) or Enabled; $null when unknown.
function Get-DiagPePublicAccess {
    param($Evidence, $Dependency)
    if ($Dependency.kind -eq 'Ampls') {
        $state = $null; $failed = $null
        foreach ($dep in @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.kind -in @('AppInsights', 'Workspace') })) {
            $read = Get-Ev $Evidence $dep.resource
            if (!$read.Ok) { if (!$read.NotFound -and !$failed) { $failed = $read }; continue }
            if ($read.Data.properties.publicNetworkAccessForQuery -eq 'Disabled') { return @{ State = 'Disabled'; Read = $read } }
            $state = 'Enabled'
        }
        return @{ State = $(if ($failed) { $null } else { $state }); Read = $failed }
    }
    $read = Get-Ev $Evidence $Dependency.resource
    if (!$read.Ok) { return @{ State = $null; Read = $read } }
    $p = $read.Data.properties
    $state = if ($p.publicNetworkAccess -eq 'Disabled') { 'Disabled' } elseif ($p.networkAcls.defaultAction -eq 'Deny') { 'Selected' } else { 'Enabled' }
    @{ State = $state; Read = $read }
}

function Test-DiagPrivateEndpoint {
    param($Evidence)
    $out = [Collections.Generic.List[object]]::new()
    $agentSubnet = $Evidence.discovery.agentSubnet
    $agentVnet = if ($agentSubnet) { Get-ArmParent $agentSubnet } else { $null }

    foreach ($dep in Get-DiagPeDependencies $Evidence) {
        if ((Get-Ev $Evidence $dep.resource).NotFound) { continue }   # the dependency's own area reports a missing resource
        $kind = $script:DiagPeKindLabels[$dep.kind]
        $name = Get-ArmName $dep.resource
        $label = "$($script:DiagPeKindPhrases[$dep.kind]) '$name'"
        $path = $dep.path

        # pe.exists
        $title = "$kind private endpoint"
        $conn = Get-DiagPeConnections $Evidence $dep
        $peIds = @(Get-DiagPeIds $dep $conn)
        $gap = New-ReadGap $conn.Read -Id pe.exists -Area PrivateEndpoint -Title $title -Layer Config -Path $path -Resource $dep.resource `
            -What "the private endpoint connections of $label"
        if ($gap) { $out.Add($gap) }
        elseif (!$peIds.Count -and $dep.kind -eq 'Ampls') { }   # monitoring.amplsPe reports a scope without a private endpoint
        elseif (!$peIds.Count) {
            $public = Get-DiagPePublicAccess $Evidence $dep
            $ref = @($(if ($conn.Read.Read) { Get-EvRef $conn.Read }))
            if ($public.State -eq 'Disabled') {
                $out.Add((New-DiagResult -Id pe.exists -Area PrivateEndpoint -Title $title -Status Problem -Severity High -Layer Config -Path $path -Resource $dep.resource `
                    -Seen "The $label has no private endpoint and doesn't accept public traffic." `
                    -Likely 'Consistent with evaluation traffic to this resource being refused.' -Owner NetworkTeam `
                    -Action "Create a private endpoint for the $label in a subnet the agent subnet can reach, with private DNS zone integration." -Evidence $ref))
            }
            elseif ($public.State -eq 'Selected') {
                $out.Add((New-DiagResult -Id pe.exists -Area PrivateEndpoint -Title $title -Status Problem -Severity Medium -Layer Config -Path $path -Resource $dep.resource `
                    -Seen "The $label has no private endpoint and accepts public traffic only from selected networks." -Owner NetworkTeam `
                    -Action "Create a private endpoint for the $label, or allow the agent subnet in its network rules." -Evidence $ref))
            }
            elseif ($public.State -eq 'Enabled') {
                $out.Add((New-DiagResult -Id pe.exists -Area PrivateEndpoint -Title $title -Status OK -Layer Config -Path $path -Resource $dep.resource `
                    -Seen "The $label has no private endpoint; traffic uses its public network access." -Evidence $ref))
            }
            else {
                $readGap = if ($public.Read) { New-ReadGap $public.Read -Id pe.exists -Area PrivateEndpoint -Title $title -Layer Config -Path $path -Resource $dep.resource }
                if ($readGap) { $out.Add($readGap) }
                else {
                    $out.Add((New-DiagResult -Id pe.exists -Area PrivateEndpoint -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Path $path -Resource $dep.resource `
                        -Seen "The $label has no private endpoint and its public access setting is unknown." -Needs "Check in the portal whether the $label accepts public traffic."))
                }
            }
            continue
        }
        else {
            $out.Add((New-DiagResult -Id pe.exists -Area PrivateEndpoint -Title $title -Status OK -Layer Config -Path $path -Resource $dep.resource `
                -Seen "Private endpoint $(($peIds | ForEach-Object { "'$(Get-ArmName $_)'" }) -join ', ') for the $label." -Evidence @(Get-EvRef $conn.Read)))
        }

        $statuses = @{}
        foreach ($peId in $peIds) {
            $pe = Get-Ev $Evidence $peId
            $status = @($conn.Items | Where-Object { Test-SameArmId $_.Pe $peId } | ForEach-Object { $_.Status } | Where-Object { $_ })[0]
            if (!$status -and $pe.Ok) {
                $links = @(@($pe.Data.properties.privateLinkServiceConnections) + @($pe.Data.properties.manualPrivateLinkServiceConnections) | Where-Object { $_ })
                $own = @($links | Where-Object { Test-SameArmId $_.properties.privateLinkServiceId $dep.resource })
                if (!$own.Count -and $links.Count -eq 1) { $own = $links }
                $status = @($own | ForEach-Object { $_.properties.privateLinkServiceConnectionState.status } | Where-Object { $_ })[0]
            }
            $statuses[$peId] = $status
        }
        $anyApproved = @($peIds | Where-Object { $statuses[$_] -eq 'Approved' -and !(Get-Ev $Evidence $_).NotFound }).Count -gt 0

        foreach ($peId in $peIds) {
            $peName = Get-ArmName $peId
            $pe = Get-Ev $Evidence $peId
            if ($pe.NotFound) {
                $out.Add((New-DiagResult -Id pe.addresses -Area PrivateEndpoint -Title "$kind private endpoint addresses" -Status Problem -Severity $(if ($anyApproved) { 'Low' } else { 'High' }) `
                    -Layer Config -Path $path -Resource $peId -Seen "Private endpoint '$peName' is listed on the $label but no longer exists." -Owner NetworkTeam `
                    -Action "Remove the stale connection from the $label and create a new private endpoint if needed." -Evidence @(Get-EvRef $pe)))
                continue
            }

            # pe.approval
            $title = "$kind private endpoint approval"
            $status = $statuses[$peId]
            if ($status -eq 'Approved') {
                $out.Add((New-DiagResult -Id pe.approval -Area PrivateEndpoint -Title $title -Status OK -Layer Config -Path $path -Resource $peId `
                    -Seen "Private endpoint '$peName' is approved." -Evidence @(Get-EvRef $conn.Read)))
            }
            elseif ($status) {
                $out.Add((New-DiagResult -Id pe.approval -Area PrivateEndpoint -Title $title -Status Problem -Severity $(if ($anyApproved) { 'Low' } else { 'High' }) `
                    -Layer Config -Path $path -Resource $peId -Seen "Private endpoint '$peName' to the $label is $status, not Approved." `
                    -Likely $(if ($anyApproved) { $null } else { 'Consistent with connections to this resource being refused.' }) -Owner ResourceOwner `
                    -Action $(if ($status -eq 'Pending') { "Approve the private endpoint connection '$peName' on the $label (Networking > Private endpoint connections)." } else { "Delete private endpoint '$peName' and create a new one, then approve it on the $label." }) `
                    -Evidence @(Get-EvRef $conn.Read) -Details @{ status = $status }))
            }
            else {
                $gap = New-ReadGap $pe -Id pe.approval -Area PrivateEndpoint -Title $title -Layer Config -Path $path -Resource $peId -What "private endpoint '$peName'"
                if (!$gap) {
                    $gap = New-DiagResult -Id pe.approval -Area PrivateEndpoint -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Path $path -Resource $peId `
                        -Seen "No connection state was found for private endpoint '$peName'." -Needs "Check the connection state on the $label (Networking > Private endpoint connections)."
                }
                $out.Add($gap)
            }

            # pe.placement
            $title = "$kind private endpoint network"
            $gap = New-ReadGap $pe -Id pe.placement -Area PrivateEndpoint -Title $title -Layer Route -Path $path -Resource $peId -What "private endpoint '$peName'"
            if ($gap) { $out.Add($gap) }
            elseif ($agentVnet -and $pe.Data.properties.subnet.id) {
                $out.Add((Test-DiagPePlacement $Evidence -PeId $peId -PeSubnet $pe.Data.properties.subnet.id -AgentVnet $agentVnet -Path $path -Title $title -PeRef (Get-EvRef $pe)))
            }

            # pe.addresses
            $title = "$kind private endpoint addresses"
            $gap = New-ReadGap $pe -Id pe.addresses -Area PrivateEndpoint -Title $title -Layer Config -Path $path -Resource $peId -What "private endpoint '$peName'"
            if ($gap) { $out.Add($gap); continue }
            $addresses = Get-DiagPeAddresses $Evidence $peId
            $pairs = @($addresses.Keys | Sort-Object | Where-Object { @($addresses[$_]).Count } | ForEach-Object { "$_ = $(@($addresses[$_]) -join ', ')" })
            if (!$pairs.Count) {
                $out.Add((New-DiagResult -Id pe.addresses -Area PrivateEndpoint -Title $title -Status Problem -Severity High -Layer Config -Path $path -Resource $peId `
                    -Seen "Private endpoint '$peName' has no private IP addresses for any host name." -Owner NetworkTeam `
                    -Action "Recreate private endpoint '$peName' for the $label; it should get one private IP per host name." -Evidence @(Get-EvRef $pe)))
            }
            else {
                $out.Add((New-DiagResult -Id pe.addresses -Area PrivateEndpoint -Title $title -Status OK -Layer Config -Path $path -Resource $peId `
                    -Seen "$($pairs -join '; ')." -Evidence @(Get-EvRef $pe) -Details @{ addresses = $addresses }))
            }
        }
    }
    , $out.ToArray()
}

# The private endpoint must be in the agent VNet or a VNet peered with it.
function Test-DiagPePlacement {
    param($Evidence, [string]$PeId, [string]$PeSubnet, [string]$AgentVnet, [string]$Path, [string]$Title, [string]$PeRef)
    $peName = Get-ArmName $PeId
    $peVnet = Get-ArmParent $PeSubnet
    $common = @{ Id = 'pe.placement'; Area = 'PrivateEndpoint'; Title = $Title; Layer = 'Route'; Path = $Path; Resource = $PeId }
    if (Test-SameArmId $peVnet $AgentVnet) {
        return New-DiagResult @common -Status OK -Seen "Private endpoint '$peName' is in the agent virtual network '$(Get-ArmName $AgentVnet)'." -Evidence @($PeRef)
    }
    $peerings = Get-Ev $Evidence "$AgentVnet/virtualNetworkPeerings"
    $gap = New-ReadGap $peerings @common -What "the peerings of virtual network '$(Get-ArmName $AgentVnet)'"
    if ($gap) { return $gap }
    $peering = @($peerings.Data | Where-Object { $_ -and (Test-SameArmId $_.properties.remoteVirtualNetwork.id $peVnet) })[0]
    $refs = @($PeRef; $(if ($peerings.Read) { Get-EvRef $peerings }))
    if ($peering -and $peering.properties.peeringState -eq 'Connected') {
        return New-DiagResult @common -Status OK -Seen "Private endpoint '$peName' is in virtual network '$(Get-ArmName $peVnet)', peered with the agent virtual network." -Evidence $refs
    }
    if ($peering) {
        return New-DiagResult @common -Status Problem -Severity High -Seen "Peering '$($peering.name)' to virtual network '$(Get-ArmName $peVnet)', where private endpoint '$peName' is, is $($peering.properties.peeringState)." `
            -Likely 'Consistent with traffic to the private endpoint not being routed.' -Owner NetworkTeam `
            -Action "Reconnect the peering between '$(Get-ArmName $AgentVnet)' and '$(Get-ArmName $peVnet)' (recreate it on both sides if it is Disconnected)." -Evidence $refs
    }
    $agent = Get-Ev $Evidence $Evidence.discovery.agentSubnet
    if ($Evidence.discovery.virtualHub -or ($agent.Ok -and $agent.Data.properties.routeTable.id)) {
        return New-DiagResult @common -Status CouldNotCheck -Gap KnownLimit `
            -Seen "Private endpoint '$peName' is in virtual network '$(Get-ArmName $peVnet)', which is not peered with the agent virtual network; traffic may reach it through a hub." `
            -Needs "Confirm that '$(Get-ArmName $peVnet)' is reachable from the agent subnet through your hub (Virtual WAN or appliance)." -Evidence $refs
    }
    New-DiagResult @common -Status Problem -Severity High -Seen "Private endpoint '$peName' is in virtual network '$(Get-ArmName $peVnet)', which is not peered with the agent virtual network '$(Get-ArmName $AgentVnet)'." `
        -Likely 'Consistent with traffic to the private endpoint not being routed.' -Owner NetworkTeam `
        -Action "Peer '$(Get-ArmName $peVnet)' with '$(Get-ArmName $AgentVnet)', or create the private endpoint in the agent virtual network." -Evidence $refs
}
