# Egress checks: how traffic from the agent subnet leaves it (route table, BGP, peerings, Virtual WAN, next hops).
# Also defines the shared egress plan (which next hop each target uses) that Firewall.ps1 and Nva.ps1 read.

$script:EgressMonitorQueryHosts = @('api.loganalytics.io', 'api.applicationinsights.io')
$script:EgressPathTags = @{
    Foundry      = @('CognitiveServicesFrontend', 'CognitiveServicesManagement')
    Models       = @('CognitiveServicesFrontend', 'CognitiveServicesManagement')
    Storage      = @('Storage')
    MonitorQuery = @('AzureMonitor')
}
$script:EgressPathLabels = @{ Foundry = 'Foundry'; Storage = 'Storage'; MonitorQuery = 'Monitor query'; Models = 'Models' }

# Reads a field from properties (ARM shape) or from the object itself (flattened shape). Arrays unroll; wrap callers in @().
function Get-EgressProp {
    param($Obj, [string]$Name)
    if ($null -eq $Obj) { return $null }
    $p = $Obj['properties']
    if ($p -is [Collections.IDictionary] -and $p.Contains($Name)) { return $p[$Name] }
    if ($Obj -is [Collections.IDictionary] -and $Obj.Contains($Name)) { return $Obj[$Name] }
    $null
}

function ConvertTo-EgressIpNumber {
    param([string]$Ip)
    $address = $null
    if (!$Ip -or ![Net.IPAddress]::TryParse($Ip, [ref]$address) -or $address.AddressFamily -ne 'InterNetwork') { return $null }
    $b = $address.GetAddressBytes()
    [uint64]$b[0] * 16777216 + [uint64]$b[1] * 65536 + [uint64]$b[2] * 256 + [uint64]$b[3]
}

# Parses "a.b.c.d/n" or "a.b.c.d" into a range; $null for anything else (service tags, '*').
function Get-EgressCidr {
    param([string]$Cidr)
    if (!$Cidr) { return $null }
    $ip, $len = $Cidr.Trim() -split '/', 2
    $n = ConvertTo-EgressIpNumber $ip
    if ($null -eq $n) { return $null }
    $length = if ($null -ne $len) { $parsed = 0; if (![int]::TryParse($len, [ref]$parsed) -or $parsed -lt 0 -or $parsed -gt 32) { return $null }; $parsed } else { 32 }
    $size = [uint64][math]::Pow(2, 32 - $length)
    $start = $n - ($n % $size)
    @{ Start = $start; End = $start + $size - 1; Length = $length }
}

# True when $Outer (CIDR) contains $Inner (CIDR or IP).
function Test-EgressCidrContains {
    param([string]$Outer, [string]$Inner)
    $o = Get-EgressCidr $Outer; $i = Get-EgressCidr $Inner
    [bool]($o -and $i -and $o.Start -le $i.Start -and $o.End -ge $i.End)
}

function Test-EgressTagMatch {
    param([string]$Prefix, [string]$Path)
    foreach ($tag in @($script:EgressPathTags[$Path])) {
        if ($Prefix -ieq $tag -or $Prefix -like "$tag.*") { return $true }
    }
    $false
}

function Get-EgressRoutePolicyOn {
    param([string]$Policy)
    $Policy -in @('Enabled', 'RouteTableEnabled')
}

function Get-EgressPathLabel {
    param([string]$Path)
    $(if ($script:EgressPathLabels[$Path]) { $script:EgressPathLabels[$Path] } else { $Path })
}

function Get-EgressHostList {
    param($Targets)
    (@($Targets | ForEach-Object { $_.Host } | Select-Object -Unique) -join ', ')
}

# Builds (once per evidence) the egress plan: agent subnet, route table, hub, and the next hop each target uses.
function Get-EgressPlan {
    param($Evidence)
    if ($Evidence.Contains('_egressPlan')) { return $Evidence['_egressPlan'] }
    $d = $Evidence.discovery
    $plan = @{
        Ready = $false; SubnetId = $d.agentSubnet; Subnet = $null; AgentPrefixes = @(); RouteTableId = $null; RouteTable = $null
        Routes = @(); BgpOn = $true; VnetId = $null; Vnet = $null; VnetPrefixes = @(); VnetDns = @(); Peerings = $null
        HubId = $d.virtualHub; Hub = $null; Intent = $null; HubPolicies = @(); InternetPolicy = $null; PrivatePolicy = $null
        Targets = @(); NextHops = @($d.nextHops | Where-Object { $_ }); Firewalls = @($d.firewalls | Where-Object { $_ })
        FirewallIps = @{}; PeSubnets = @{}
    }
    $Evidence['_egressPlan'] = $plan
    if (!$plan.SubnetId) { return $plan }
    $plan.Subnet = Get-Ev $Evidence $plan.SubnetId
    if (!$plan.Subnet.Ok) { return $plan }
    $sp = $plan.Subnet.Data.properties
    $plan.AgentPrefixes = @(@($sp.addressPrefix) + @($sp.addressPrefixes) | Where-Object { $_ } | Select-Object -Unique)
    $plan.VnetId = Get-ArmParent $plan.SubnetId
    $plan.Vnet = Get-Ev $Evidence $plan.VnetId
    if ($plan.Vnet.Ok) {
        $plan.VnetPrefixes = @($plan.Vnet.Data.properties.addressSpace.addressPrefixes | Where-Object { $_ })
        $plan.VnetDns = @($plan.Vnet.Data.properties.dhcpOptions.dnsServers | Where-Object { $_ })
    }
    $plan.Peerings = Get-Ev $Evidence "$($plan.VnetId)/virtualNetworkPeerings"

    $plan.RouteTableId = $sp.routeTable.id
    if ($plan.RouteTableId) {
        $plan.RouteTable = Get-Ev $Evidence $plan.RouteTableId
        if ($plan.RouteTable.Ok) {
            $plan.BgpOn = !$plan.RouteTable.Data.properties.disableBgpRoutePropagation
            $plan.Routes = @($plan.RouteTable.Data.properties.routes | Where-Object { $_ } | ForEach-Object {
                @{ Name = $_.name; Prefix = (Get-EgressProp $_ 'addressPrefix'); Type = (Get-EgressProp $_ 'nextHopType'); Ip = (Get-EgressProp $_ 'nextHopIpAddress') } })
        }
    }

    if ($plan.HubId) {
        $plan.Hub = Get-Ev $Evidence $plan.HubId
        $plan.Intent = Get-Ev $Evidence "$($plan.HubId)/routingIntent"
        if ($plan.Intent.Ok) {
            $plan.HubPolicies = @(@($plan.Intent.Data) | Where-Object { $_ } | ForEach-Object {
                $own = Get-EgressProp $_ 'routingPolicies'
                if ($own) { @($own) } elseif ($_.Contains('name') -and (Get-EgressProp $_ 'nextHop')) { $_ }
            } | Where-Object { $_ })
            $plan.InternetPolicy = $plan.HubPolicies | Where-Object { @(Get-EgressProp $_ 'destinations') -contains 'Internet' } | Select-Object -First 1
            $plan.PrivatePolicy = $plan.HubPolicies | Where-Object { @(Get-EgressProp $_ 'destinations') -contains 'PrivateTraffic' } | Select-Object -First 1
        }
    }

    foreach ($fw in $plan.Firewalls) {
        $fwEv = Get-Ev $Evidence $fw
        if (!$fwEv.Ok) { continue }
        $fp = $fwEv.Data.properties
        foreach ($ip in @(@($fp.ipConfigurations | ForEach-Object { Get-EgressProp $_ 'privateIPAddress' }) + @($fp.hubIPAddresses.privateIPAddress)) | Where-Object { $_ }) {
            $plan.FirewallIps[$ip] = $fw
        }
    }

    $plan.Targets = @(foreach ($path in (Get-DiagPathsUsed $Evidence)) { Get-EgressPathTargets $Evidence $plan $path })
    foreach ($t in $plan.Targets) { Resolve-EgressTargetHop $plan $t }
    $plan.Ready = $true
    $plan
}

function Get-EgressPathTargets {
    param($Evidence, $Plan, [string]$Path)
    $deps = @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.path -eq $Path })
    $peIps = @{}
    $hasPe = @{}
    foreach ($dep in $deps) {
        foreach ($pe in @($dep.privateEndpoints | Where-Object { $_ })) {
            foreach ($h in @($dep.hosts)) { if ($h) { $hasPe[$h.ToLowerInvariant()] = $true } }
            $peEv = Get-Ev $Evidence $pe
            if (!$peEv.Ok) { continue }
            $peSubnet = $peEv.Data.properties.subnet.id
            # Zone-group endpoints usually have empty customDnsConfigs, so include their record sets too.
            $addresses = Get-DiagPeAddresses $Evidence $pe
            foreach ($fqdn in $addresses.Keys) {
                $ip = @($addresses[$fqdn] | Where-Object { $_ })[0]
                if ($ip) { $peIps[$fqdn] = @{ Ip = $ip; Pe = $pe; PeSubnet = $peSubnet } }
            }
        }
    }
    if ($Path -eq 'MonitorQuery') {
        $amplsPrivate = [bool]@($deps | Where-Object { $_.kind -eq 'Ampls' -and @($_.privateEndpoints | Where-Object { $_ }).Count }).Count
        $hosts = $script:EgressMonitorQueryHosts
    }
    else { $hosts = @($deps | ForEach-Object { $_.hosts } | Where-Object { $_ } | Select-Object -Unique) }
    foreach ($h in $hosts) {
        $key = $h.ToLowerInvariant()
        if ($Path -eq 'MonitorQuery') { $info = $peIps['api.monitor.azure.com']; $private = $amplsPrivate }
        else { $info = $peIps[$key]; $private = [bool]($info -or $hasPe[$key]) }
        $policy = $null
        if ($info -and $info.PeSubnet) {
            if (!$Plan.PeSubnets.Contains($info.PeSubnet)) { $Plan.PeSubnets[$info.PeSubnet] = Get-Ev $Evidence $info.PeSubnet }
            $peSubnetEv = $Plan.PeSubnets[$info.PeSubnet]
            if ($peSubnetEv.Ok) { $policy = $peSubnetEv.Data.properties.privateEndpointNetworkPolicies }
        }
        @{
            Path = $Path; Host = $h; Private = $private; Ip = $(if ($info) { $info.Ip } else { $null })
            Pe = $(if ($info) { $info.Pe } else { $null }); PeSubnet = $(if ($info) { $info.PeSubnet } else { $null }); PePolicy = $policy
            HopType = $null; HopIp = $null; Via = $null; Route = $null; RoutePrefix = $null; Owner = $null; OwnerType = $null; HopRequest = $null
        }
    }
}

function Set-EgressHop {
    param($Target, [string]$Type, [string]$Via, $Route, [string]$Ip)
    $Target.HopType = $Type; $Target.Via = $Via; $Target.HopIp = $Ip
    if ($Route) { $Target.Route = $Route.Name; $Target.RoutePrefix = $Route.Prefix }
}

function Resolve-EgressTargetHop {
    param($Plan, $Target)
    $udrs = @($Plan.Routes)
    $chosen = $null
    if ($Target.Private) {
        if (!$Target.Ip) {
            if ($udrs.Count) { Set-EgressHop $Target 'Unknown' 'unknown' $null $null } else { Set-EgressHop $Target 'InterfaceEndpoint' 'system' $null $null }
            return
        }
        $cands = [Collections.Generic.List[object]]::new()
        foreach ($r in $udrs) {
            $c = Get-EgressCidr $r.Prefix
            if ($c -and (Test-EgressCidrContains $r.Prefix $Target.Ip)) { $cands.Add(@{ Len = $c.Length; Rank = 0; Type = $r.Type; Via = 'udr'; Route = $r; Ip = $r.Ip }) }
        }
        # A private endpoint's /32 route wins over broader UDRs unless route-table policies are on for its subnet.
        if (!((Get-EgressRoutePolicyOn $Target.PePolicy) -and $cands.Count)) { $cands.Add(@{ Len = 32; Rank = 1; Type = 'InterfaceEndpoint'; Via = 'system' }) }
        foreach ($prefix in $Plan.VnetPrefixes) {
            $c = Get-EgressCidr $prefix
            if ($c -and (Test-EgressCidrContains $prefix $Target.Ip)) { $cands.Add(@{ Len = $c.Length; Rank = 1; Type = 'VnetLocal'; Via = 'system' }) }
        }
        $chosen = $cands | Sort-Object @{ Expression = { $_.Len }; Descending = $true }, @{ Expression = { $_.Rank } } | Select-Object -First 1
        $local = [bool]@($Plan.VnetPrefixes | Where-Object { Test-EgressCidrContains $_ $Target.Ip }).Count
        if ($chosen.Via -ne 'udr' -and $Plan.PrivatePolicy -and !$local -and $chosen.Type -ne 'InterfaceEndpoint') {
            Set-EgressHubHop $Plan $Target $Plan.PrivatePolicy; return
        }
    }
    else {
        $tagRoute = $udrs | Where-Object { !(Get-EgressCidr $_.Prefix) -and (Test-EgressTagMatch $_.Prefix $Target.Path) } | Select-Object -First 1
        if ($tagRoute) { $chosen = @{ Type = $tagRoute.Type; Via = 'udr'; Route = $tagRoute; Ip = $tagRoute.Ip } }
        else {
            $default = $udrs | Where-Object { $c = Get-EgressCidr $_.Prefix; $c -and $c.Length -le 1 } |
                Sort-Object @{ Expression = { (Get-EgressCidr $_.Prefix).Length }; Descending = $true } | Select-Object -First 1
            if ($default) { $chosen = @{ Type = $default.Type; Via = 'udr'; Route = $default; Ip = $default.Ip } }
            elseif ($Plan.InternetPolicy) { Set-EgressHubHop $Plan $Target $Plan.InternetPolicy; return }
            else { $chosen = @{ Type = 'Internet'; Via = 'system' } }
        }
    }
    Set-EgressHop $Target $chosen.Type $chosen.Via $chosen.Route $chosen.Ip
    if ($Target.HopType -eq 'VirtualAppliance' -and $Target.HopIp) {
        $hop = $Plan.NextHops | Where-Object { $_.ip -eq $Target.HopIp } | Select-Object -First 1
        if ($hop) { $Target.Owner = $hop.owner; $Target.OwnerType = $hop.ownerType; $Target.HopRequest = $hop.request }
        if (!$Target.Owner -and $Plan.FirewallIps[$Target.HopIp]) { $Target.Owner = $Plan.FirewallIps[$Target.HopIp]; $Target.OwnerType = 'AzureFirewall' }
    }
}

function Set-EgressHubHop {
    param($Plan, $Target, $Policy)
    $hop = $Plan.NextHops | Where-Object { $_.source -eq 'virtualHub' } | Select-Object -First 1
    Set-EgressHop $Target 'VirtualHub' 'hub' $null $(if ($hop) { $hop.ip } else { $null })
    $Target.Route = Get-EgressProp $Policy 'name'
    $nextHop = Get-EgressProp $Policy 'nextHop'
    $Target.Owner = $nextHop
    $Target.OwnerType = $(if ($nextHop -match '(?i)/azureFirewalls/') { 'AzureFirewall' } elseif ($hop) { $hop.ownerType } else { $null })
    if ($hop) { $Target.HopRequest = $hop.request }
}

function Get-EgressHopText {
    param($Target)
    $dest = $(if ($Target.Ip) { "$($Target.Host) ($($Target.Ip))" } else { $Target.Host })
    $how = switch ($Target.HopType) {
        'VirtualAppliance' { "the appliance at $($Target.HopIp)" }
        'VirtualHub' { "the Virtual WAN hub (routing policy '$($Target.Route)')" }
        'VirtualNetworkGateway' { 'the virtual network gateway (on-premises)' }
        'InterfaceEndpoint' { 'its private endpoint directly' }
        'VnetLocal' { 'the virtual network directly' }
        'VNetPeering' { 'the peered virtual network' }
        'Internet' { 'the internet directly' }
        'None' { 'nowhere (dropped)' }
        default { "next hop $($Target.HopType)" }
    }
    $by = $(if ($Target.Via -eq 'udr' -and $Target.Route) { " by route '$($Target.Route)' ($($Target.RoutePrefix))" } else { '' })
    "$dest goes to $how$by"
}

function New-EgressReadGap {
    param($Read, [string]$Id, [string]$Title, [string]$Layer, [string]$Path, [string]$Resource, [string]$What, [switch]$Soft)
    $gap = New-ReadGap $Read -Id $Id -Area Egress -Title $Title -Layer $Layer -Path $Path -Resource $Resource -What $What
    if ($gap -and $Soft) { $gap.gap = 'KnownLimit' }
    $gap
}

function Test-DiagEgress {
    param($Evidence)
    $plan = Get-EgressPlan $Evidence
    if (!$plan.SubnetId) { return , @() }
    $out = [Collections.Generic.List[object]]::new()
    $paths = @(Get-DiagPathsUsed $Evidence)
    $subnetName = Get-ArmName $plan.SubnetId
    $prefixText = $(if ($plan.AgentPrefixes.Count) { $plan.AgentPrefixes -join ', ' } else { "subnet '$subnetName'" })

    if (!$plan.Subnet.Ok) {
        foreach ($path in $paths) {
            $gap = New-EgressReadGap $plan.Subnet -Id egress.routeTable -Title 'Agent subnet route table' -Layer Route -Path $path -Resource $plan.SubnetId -What "agent subnet '$subnetName'"
            if ($gap) { $out.Add($gap) }
        }
        return , $out.ToArray()
    }

    # egress.routeTable — next hop for each target of each used path.
    $title = 'Agent subnet route table'
    $rtName = Get-ArmName $plan.RouteTableId
    $rtGap = $null
    if ($plan.RouteTableId -and !$plan.RouteTable.Ok) {
        foreach ($path in $paths) {
            if ($plan.RouteTable.NotFound) {
                $out.Add((New-DiagResult -Id egress.routeTable -Area Egress -Title $title -Status CouldNotCheck -Gap Blocking -Path $path -Layer Route -Resource $plan.RouteTableId `
                    -Seen "Subnet '$subnetName' points at route table '$rtName', which was not found." -Needs "Check the route table attached to subnet '$subnetName' in the portal." -Evidence (Get-EvRef $plan.RouteTable)))
            }
            else {
                $rtGap = New-EgressReadGap $plan.RouteTable -Id egress.routeTable -Title $title -Layer Route -Path $path -Resource $plan.RouteTableId -What "route table '$rtName'"
                $out.Add($rtGap)
            }
        }
    }
    else {
        foreach ($path in $paths) {
            $targets = @($plan.Targets | Where-Object { $_.Path -eq $path })
            $resource = $(if ($plan.RouteTableId) { $plan.RouteTableId } else { $plan.SubnetId })
            $refs = @(Get-EvRef $plan.Subnet) + @(if ($plan.RouteTable) { Get-EvRef $plan.RouteTable })
            $details = @{ routeTable = $plan.RouteTableId; hops = @($targets | ForEach-Object { @{ host = $_.Host; ip = $_.Ip; hopType = $_.HopType; hopIp = $_.HopIp; route = $_.Route; via = $_.Via } }) }
            $dropped = @($targets | Where-Object { $_.HopType -eq 'None' -or ($_.HopType -eq 'VirtualAppliance' -and !$_.HopIp) -or ($_.Private -and $_.Via -eq 'udr' -and $_.HopType -eq 'Internet') })
            $unknown = @($targets | Where-Object { $_.HopType -eq 'Unknown' })
            if ($dropped.Count) {
                $r = $dropped[0]
                $why = switch ($r.HopType) { 'None' { 'next hop None drops it' } 'Internet' { 'it sends private endpoint traffic to the internet, where it is dropped' } default { 'the appliance next hop has no IP address' } }
                $out.Add((New-DiagResult -Id egress.routeTable -Area Egress -Title $title -Status Problem -Severity High -Path $path -Layer Route -Resource $resource `
                    -Seen "Route '$($r.Route)' ($($r.RoutePrefix)) in route table '$rtName' covers $(Get-EgressHostList $dropped) and $why." `
                    -Likely "Consistent with $(Get-EgressPathLabel $path) traffic failing fast from the agent subnet." -Owner NetworkTeam `
                    -Action "In route table '$rtName', remove route '$($r.Route)' or point it at your firewall/appliance (next hop VirtualAppliance with its IP), so $(Get-EgressHostList $dropped) on TCP 443 can leave $prefixText." `
                    -Evidence $refs -Details $details))
            }
            elseif ($unknown.Count) {
                $out.Add((New-DiagResult -Id egress.routeTable -Area Egress -Title $title -Status CouldNotCheck -Gap KnownLimit -Path $path -Layer Route -Resource $resource `
                    -Seen "Couldn't tell which route $(Get-EgressHostList $unknown) uses because its private endpoint address wasn't readable." `
                    -Needs 'Read access to the private endpoint (see the private endpoint results).' -Evidence $refs -Details $details))
            }
            else {
                $seen = $(if (!$plan.RouteTableId -and !$plan.HubId) { 'No route table; traffic uses Azure default routing.' } else { ((@($targets | ForEach-Object { Get-EgressHopText $_ }) -join '; ') + '.') })
                if (!$targets.Count) { $seen = 'No targets found for this path.' }
                $out.Add((New-DiagResult -Id egress.routeTable -Area Egress -Title $title -Status OK -Path $path -Layer Route -Resource $resource -Seen $seen -Evidence $refs -Details $details))
            }
        }
    }

    # egress.peSubnetPolicy — private endpoint traffic forced through an appliance.
    if ($plan.RouteTableId -and $plan.RouteTable.Ok) {
        $title = 'Private endpoint traffic routing'
        foreach ($path in $paths) {
            $private = @($plan.Targets | Where-Object { $_.Path -eq $path -and $_.Private -and $_.Ip })
            if (!$private.Count) { continue }
            $via = @($private | Where-Object { $_.Via -eq 'udr' -and $_.HopType -eq 'VirtualAppliance' })
            $refs = @(Get-EvRef $plan.RouteTable)
            if ($via.Count) {
                $r = $via[0]
                $peSubnetName = Get-ArmName $r.PeSubnet
                $why = $(if ((Get-EgressCidr $r.RoutePrefix).Length -eq 32) { 'a /32 route' } else { "route-table policies on subnet '$peSubnetName' ($($r.PePolicy))" })
                $out.Add((New-DiagResult -Id egress.peSubnetPolicy -Area Egress -Title $title -Status Problem -Severity Medium -Path $path -Layer Route -Resource $plan.RouteTableId `
                    -Seen "Traffic to private endpoint $($r.Ip) ($(Get-EgressHostList $via)) goes through the appliance at $($r.HopIp) by route '$($r.Route)' because of $why; the private endpoint replies directly, so the path can be asymmetric." `
                    -Likely "Consistent with connections to $(Get-EgressHostList $via) hanging or being reset when the appliance doesn't SNAT them." -Owner NetworkTeam `
                    -Action "Either SNAT traffic from $prefixText to $($r.Ip) on TCP 443 at the appliance (Azure Firewall: allow it with an application rule, or include it in private SNAT ranges), or remove route '$($r.Route)' from '$rtName' so the private endpoint's own route is used." `
                    -Evidence $refs -Details @{ peSubnet = $r.PeSubnet; privateEndpointNetworkPolicies = $r.PePolicy; route = $r.Route; prefix = $r.RoutePrefix; nextHop = $r.HopIp }))
            }
            else {
                $out.Add((New-DiagResult -Id egress.peSubnetPolicy -Area Egress -Title $title -Status OK -Path $path -Layer Route -Resource $plan.RouteTableId `
                    -Seen "Private endpoint traffic ($(Get-EgressHostList $private)) uses the endpoints' own routes, not the appliance." -Evidence $refs))
            }
        }
    }

    # egress.peering — peerings connected; forwarded traffic accepted from an appliance in the peer.
    $title = 'Virtual network peerings'
    $peerGap = New-EgressReadGap $plan.Peerings -Id egress.peering -Title $title -Layer Route -Resource "$($plan.VnetId)/virtualNetworkPeerings" -What "peerings of '$(Get-ArmName $plan.VnetId)'"
    $peerings = @()
    if ($peerGap) { $out.Add($peerGap) }
    elseif ($plan.Peerings.Ok) {
        $peerings = @($plan.Peerings.Data | Where-Object { $_ })
        $remoteAppliances = @($plan.Targets | Where-Object { $_.HopType -eq 'VirtualAppliance' -and $_.HopIp })
        $remoteAppliances = @($remoteAppliances | Where-Object { $hopIp = $_.HopIp; !@($plan.VnetPrefixes | Where-Object { Test-EgressCidrContains $_ $hopIp }).Count })
        $connected = @($peerings | Where-Object { (Get-EgressProp $_ 'peeringState') -eq 'Connected' })
        $applianceVnets = @(foreach ($t in $remoteAppliances) {
            if ($t.OwnerType -eq 'NetworkInterface') {
                $nic = Get-Ev $Evidence $t.Owner
                if ($nic.Ok) { Get-ArmParent (Get-EgressProp @($nic.Data.properties.ipConfigurations)[0] 'subnet').id }
            }
        })
        if (!$peerings.Count) {
            $out.Add((New-DiagResult -Id egress.peering -Area Egress -Title $title -Status OK -Layer Route -Resource $plan.VnetId -Seen "Virtual network '$(Get-ArmName $plan.VnetId)' has no peerings." -Evidence (Get-EvRef $plan.Peerings)))
        }
        foreach ($peer in $peerings) {
            $state = Get-EgressProp $peer 'peeringState'
            $remote = (Get-EgressProp $peer 'remoteVirtualNetwork').id
            $name = $peer.name
            $holdsAppliance = $remoteAppliances.Count -and ((@($applianceVnets | Where-Object { Test-SameArmId $_ $remote }).Count) -or (!$applianceVnets.Count -and $connected.Count -eq 1 -and $state -eq 'Connected'))
            $resource = $(if ($peer.id) { $peer.id } else { "$($plan.VnetId)/virtualNetworkPeerings/$name" })
            if ($state -ne 'Connected') {
                $out.Add((New-DiagResult -Id egress.peering -Area Egress -Title $title -Status Problem -Severity High -Layer Route -Resource $resource `
                    -Seen "Peering '$name' to '$(Get-ArmName $remote)' is $state, so no traffic crosses it." -Owner NetworkTeam `
                    -Action "Reconnect peering '$name': re-create the matching peering on '$(Get-ArmName $remote)' (or sync it) until both sides show Connected." `
                    -Evidence (Get-EvRef $plan.Peerings) -Details @{ peeringState = $state; remoteVirtualNetwork = $remote }))
            }
            elseif ($holdsAppliance -and !(Get-EgressProp $peer 'allowForwardedTraffic')) {
                $out.Add((New-DiagResult -Id egress.peering -Area Egress -Title $title -Status Problem -Severity Medium -Layer Route -Resource $resource `
                    -Seen "Agent traffic goes through an appliance in '$(Get-ArmName $remote)', but peering '$name' doesn't allow forwarded traffic." `
                    -Likely 'Consistent with return traffic forwarded by the appliance being dropped.' -Owner NetworkTeam `
                    -Action "Turn on 'Allow forwarded traffic' on peering '$name' (from '$(Get-ArmName $plan.VnetId)' to '$(Get-ArmName $remote)')." `
                    -Evidence (Get-EvRef $plan.Peerings) -Details @{ allowForwardedTraffic = $false; remoteVirtualNetwork = $remote }))
            }
            else {
                $out.Add((New-DiagResult -Id egress.peering -Area Egress -Title $title -Status OK -Layer Route -Resource $resource `
                    -Seen "Peering '$name' to '$(Get-ArmName $remote)' is Connected." -Evidence (Get-EvRef $plan.Peerings) `
                    -Details @{ allowForwardedTraffic = (Get-EgressProp $peer 'allowForwardedTraffic'); useRemoteGateways = (Get-EgressProp $peer 'useRemoteGateways') }))
            }
        }
    }

    # egress.bgp — a default route learned over BGP never shows in the route table.
    $title = 'Routes learned over BGP'
    $signals = @()
    if ($plan.Vnet.Ok -and @($plan.Vnet.Data.properties.subnets | Where-Object { $_.name -eq 'GatewaySubnet' }).Count) { $signals += "virtual network '$(Get-ArmName $plan.VnetId)' has a gateway subnet" }
    foreach ($peer in @($peerings | Where-Object { Get-EgressProp $_ 'useRemoteGateways' })) { $signals += "peering '$($peer.name)' uses the remote gateway" }
    if ($plan.HubId -and !$plan.Intent.Ok) { $signals += "it is connected to Virtual WAN hub '$(Get-ArmName $plan.HubId)' whose routing couldn't be read" }
    $hasDefaultUdr = [bool]@($plan.Routes | Where-Object { $c = Get-EgressCidr $_.Prefix; $c -and $c.Length -eq 0 }).Count
    $bgpResource = $(if ($plan.RouteTableId) { $plan.RouteTableId } else { $plan.SubnetId })
    $hosts = @($plan.Targets | Where-Object { !$_.Private } | ForEach-Object { $_.Host } | Select-Object -Unique)
    $hostText = $(if ($hosts.Count) { $hosts -join ', ' } else { 'the evaluation endpoints' })
    if ($plan.BgpOn -and $signals.Count -and !$hasDefaultUdr) {
        $out.Add((New-DiagResult -Id egress.bgp -Area Egress -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Route -Resource $bgpResource `
            -Seen "BGP route propagation is on for the agent subnet and $($signals -join '; '). A default route learned over BGP (forced tunneling) wouldn't appear in any route table, and the agent subnet has no network interface, so effective routes can't be read." `
            -Needs "Ask the network team whether 0.0.0.0/0 is advertised over BGP (ExpressRoute, VPN or the Virtual WAN hub). If it is, the device it points to must allow $hostText on TCP 443 from $prefixText, without TLS inspection." `
            -Evidence @(Get-EvRef $plan.Subnet) -Details @{ signals = $signals; bgpPropagation = $true }))
    }
    else {
        $seen = if (!$plan.BgpOn) { "BGP route propagation is off on route table '$rtName'." }
                elseif ($hasDefaultUdr -and $signals.Count) { "A 0.0.0.0/0 route in '$rtName' overrides any default route learned over BGP." }
                else { 'No gateway or remote-gateway peering, so no BGP routes are expected.' }
        $out.Add((New-DiagResult -Id egress.bgp -Area Egress -Title $title -Status OK -Layer Route -Resource $bgpResource -Seen $seen -Evidence @(Get-EvRef $plan.Subnet)))
    }

    # egress.vwan — Virtual WAN hub and routing intent.
    $title = 'Virtual WAN hub routing'
    if (!$plan.HubId) {
        $out.Add((New-DiagResult -Id egress.vwan -Area Egress -Title $title -Status OK -Layer Route -Resource $plan.VnetId -Seen 'The agent virtual network is not connected to a Virtual WAN hub.'))
    }
    else {
        $hubName = Get-ArmName $plan.HubId
        $gap = New-EgressReadGap $plan.Hub -Id egress.vwan -Title $title -Layer Route -Resource $plan.HubId -What "Virtual WAN hub '$hubName'"
        if ($gap) { $out.Add($gap) }
        elseif ($plan.Hub.NotFound) {
            $out.Add((New-DiagResult -Id egress.vwan -Area Egress -Title $title -Status CouldNotCheck -Gap Blocking -Layer Route -Resource $plan.HubId `
                -Seen "Virtual WAN hub '$hubName' was not found." -Needs 'Check the hub connection of the agent virtual network in the portal.' -Evidence (Get-EvRef $plan.Hub)))
        }
        else {
            $hp = $plan.Hub.Data.properties
            $intentGap = New-EgressReadGap $plan.Intent -Id egress.vwan -Title $title -Layer Route -Resource "$($plan.HubId)/routingIntent" -What "routing intent of hub '$hubName'"
            if ($hp.provisioningState -and $hp.provisioningState -ne 'Succeeded' -or ($hp.routingState -and $hp.routingState -notin @('Provisioned', 'None'))) {
                $out.Add((New-DiagResult -Id egress.vwan -Area Egress -Title $title -Status Problem -Severity High -Layer Route -Resource $plan.HubId `
                    -Seen "Virtual WAN hub '$hubName' is in state '$($hp.provisioningState)' with routing state '$($hp.routingState)'." -Owner NetworkTeam `
                    -Action "Fix hub '$hubName' (check its last operation in the portal and reset the hub router if routing is Failed)." -Evidence (Get-EvRef $plan.Hub) `
                    -Details @{ provisioningState = $hp.provisioningState; routingState = $hp.routingState }))
            }
            elseif ($intentGap) { $out.Add($intentGap) }
            else {
                $policies = @($plan.HubPolicies | ForEach-Object { "$(Get-EgressProp $_ 'name') ($(@(Get-EgressProp $_ 'destinations') -join ', ') → $(Get-ArmName (Get-EgressProp $_ 'nextHop')))" })
                $seen = if ($policies.Count) { "Hub '$hubName' routing intent: $($policies -join '; '). Firewall checks cover the traffic it sends to the firewall." }
                        elseif ($hp.azureFirewall.id) { "Hub '$hubName' is a secured hub with firewall '$(Get-ArmName $hp.azureFirewall.id)' but no routing intent; traffic only goes through the firewall if hub route tables send it there." }
                        else { "Hub '$hubName' has no firewall or routing intent." }
                $out.Add((New-DiagResult -Id egress.vwan -Area Egress -Title $title -Status OK -Layer Route -Resource $plan.HubId -Seen $seen `
                    -Evidence @((Get-EvRef $plan.Hub), (Get-EvRef $plan.Intent)) -Details @{ azureFirewall = $hp.azureFirewall.id; routingPolicies = $policies }))
            }
        }
    }

    # egress.nextHopOwner — what owns each appliance next hop.
    $title = 'Next hop owner'
    $hopIps = @(@($plan.NextHops | ForEach-Object { $_.ip }) + @($plan.Targets | Where-Object { $_.HopType -eq 'VirtualAppliance' -and $_.HopIp } | ForEach-Object { $_.HopIp }) | Where-Object { $_ } | Select-Object -Unique)
    foreach ($ip in $hopIps) {
        $hop = $plan.NextHops | Where-Object { $_.ip -eq $ip } | Select-Object -First 1
        $usedBy = @($plan.Targets | Where-Object { $_.HopIp -eq $ip })
        $usedText = $(if ($usedBy.Count) { " ($(Get-EgressHostList $usedBy) go there)" } else { '' })
        if (!$hop) {
            if ($plan.FirewallIps[$ip]) {
                $out.Add((New-DiagResult -Id egress.nextHopOwner -Area Egress -Title $title -Status OK -Layer Route -Resource $plan.FirewallIps[$ip] -Seen "Next hop $ip is Azure Firewall '$(Get-ArmName $plan.FirewallIps[$ip])'$usedText."))
                continue
            }
            $out.Add((New-DiagResult -Id egress.nextHopOwner -Area Egress -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Route -Resource $ip `
                -Seen "This evidence file doesn't say which resource owns next hop $ip." -Needs 'Run the current version of the diagnostic to collect it.'))
            continue
        }
        $reqPath = $(if ($hop.request) { ($hop.request -replace '^\s*POST\s+', '') } else { $null })
        $read = Get-Ev $Evidence $reqPath 'POST'
        if ($read.Read -and !$read.Ok) {
            $out.Add((New-EgressReadGap $read -Id egress.nextHopOwner -Title $title -Layer Route -Resource $ip -What "the owner of next hop $ip"))
            continue
        }
        $refs = @(if ($read.Read) { Get-EvRef $read })
        if ($hop.owner) {
            $kind = switch ($hop.ownerType) { 'AzureFirewall' { 'Azure Firewall' } 'LoadBalancer' { 'internal load balancer' } 'NetworkInterface' { 'virtual machine network interface' } default { $hop.ownerType } }
            $out.Add((New-DiagResult -Id egress.nextHopOwner -Area Egress -Title $title -Status OK -Layer Route -Resource $hop.owner `
                -Seen "Next hop $ip is $kind '$(Get-ArmName $hop.owner)'$usedText." -Evidence $refs -Details @{ ip = $ip; ownerType = $hop.ownerType; source = $hop.source }))
        }
        else {
            $hostList = $(if ($usedBy.Count) { Get-EgressHostList $usedBy } else { 'the evaluation endpoints' })
            $out.Add((New-DiagResult -Id egress.nextHopOwner -Area Egress -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Route -Resource $ip `
                -Seen "No resource this account can see owns next hop $ip$usedText; it may be on-premises, in another subscription, or in another tenant." `
                -Needs "Ask the network team which device owns $ip and confirm it allows $hostList on TCP 443 from $prefixText, without TLS inspection, with an idle timeout of at least 4 minutes." `
                -Evidence $refs -Details @{ ip = $ip; source = $hop.source }))
        }
    }

    # egress.natGateway — information only.
    $title = 'Agent subnet outbound access'
    $sp = $plan.Subnet.Data.properties
    $seen = if ($sp.natGateway.id) { "NAT gateway '$(Get-ArmName $sp.natGateway.id)' handles outbound internet traffic not sent elsewhere by routes." }
            elseif ($sp.defaultOutboundAccess -eq $false) { 'No NAT gateway and default outbound access is off; internet traffic needs a route to a firewall or appliance.' }
            else { 'No NAT gateway; internet traffic not sent elsewhere by routes uses Azure default outbound access.' }
    $out.Add((New-DiagResult -Id egress.natGateway -Area Egress -Title $title -Status OK -Layer Route -Resource $plan.SubnetId -Seen $seen -Evidence (Get-EvRef $plan.Subnet) `
        -Details @{ natGateway = $sp.natGateway.id; defaultOutboundAccess = $sp.defaultOutboundAccess }))

    , $out.ToArray()
}
