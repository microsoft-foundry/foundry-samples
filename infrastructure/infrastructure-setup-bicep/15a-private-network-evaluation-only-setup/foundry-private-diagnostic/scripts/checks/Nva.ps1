# Third-party appliance (NVA) and on-premises checks: run when agent traffic goes to a VM / load balancer next hop
# or to a virtual network gateway. Appliance rules can't be read, so those are known limits with a checklist.
# Uses the egress plan from Egress.ps1.

function Get-NvaChecklist {
    param([string]$Hosts, [string]$Prefix)
    "Ask the appliance owner to confirm: (1) $Hosts are allowed on TCP 443 from $Prefix; (2) no TLS inspection for them (or the agent trusts the inspection CA); (3) the idle timeout is at least 4 minutes; (4) return traffic comes back through the same appliance (SNAT if needed)."
}

function Test-NvaNsgAddress {
    param([string[]]$Values, $Target, [string[]]$Prefixes, [switch]$Source)
    foreach ($v in $Values) {
        if ($v -eq '*' -or $v -ieq 'VirtualNetwork' -or $v -ieq 'Any') { return $true }
        if ($Source) {
            if ($Prefixes.Count -and @($Prefixes | Where-Object { Test-EgressCidrContains $v $_ }).Count -eq $Prefixes.Count) { return $true }
        }
        elseif ($Target.Ip) { if (Test-EgressCidrContains $v $Target.Ip) { return $true } }
        elseif ($v -ieq 'Internet' -or (Test-EgressTagMatch $v $Target.Path)) { return $true }
    }
    $false
}

# First inbound NSG rule (by priority) that matches agent traffic forwarded to the appliance for one target.
# Forwarded packets keep their real destination, so the destination is the target, not the appliance.
function Get-NvaNsgDecision {
    param($NsgData, $Target, [string[]]$Prefixes)
    $rules = @(@($NsgData.properties.securityRules) + @($NsgData.properties.defaultSecurityRules) | Where-Object { $_ } | ForEach-Object {
        @{ Name = $_.name; Priority = [int](Get-EgressProp $_ 'priority'); Direction = (Get-EgressProp $_ 'direction'); Access = (Get-EgressProp $_ 'access')
           Protocol = (Get-EgressProp $_ 'protocol')
           Sources = @(@(Get-EgressProp $_ 'sourceAddressPrefix') + @(Get-EgressProp $_ 'sourceAddressPrefixes') | Where-Object { $_ })
           Destinations = @(@(Get-EgressProp $_ 'destinationAddressPrefix') + @(Get-EgressProp $_ 'destinationAddressPrefixes') | Where-Object { $_ })
           Ports = @(@(Get-EgressProp $_ 'destinationPortRange') + @(Get-EgressProp $_ 'destinationPortRanges') | Where-Object { $_ }) }
    } | Where-Object { $_.Direction -eq 'Inbound' } | Sort-Object { $_.Priority })
    foreach ($r in $rules) {
        if ($r.Protocol -notin @('*', 'Tcp', 'TCP')) { continue }
        if (!(Test-FirewallPort443 $r.Ports)) { continue }
        if (!(Test-NvaNsgAddress $r.Sources $Target $Prefixes -Source)) { continue }
        if (!(Test-NvaNsgAddress $r.Destinations $Target $Prefixes)) { continue }
        return $r
    }
    $null
}

function Test-DiagNva {
    param($Evidence)
    $plan = Get-EgressPlan $Evidence
    if (!$plan.Ready) { return , @() }
    $out = [Collections.Generic.List[object]]::new()
    $prefixes = @($plan.AgentPrefixes)
    $prefixText = $(if ($prefixes.Count) { $prefixes -join ', ' } else { 'the agent subnet' })

    # Appliances: next hops owned by a VM network interface or an internal load balancer.
    $appliances = [ordered]@{}
    foreach ($hop in @($plan.NextHops | Where-Object { $_.owner -and $_.ownerType -in @('NetworkInterface', 'LoadBalancer') })) {
        $appliances[$hop.owner.ToLowerInvariant()] = @{ Id = $hop.owner; Type = $hop.ownerType; Ip = $hop.ip }
    }
    foreach ($t in @($plan.Targets | Where-Object { $_.Owner -and $_.OwnerType -in @('NetworkInterface', 'LoadBalancer') })) {
        if (!$appliances.Contains($t.Owner.ToLowerInvariant())) { $appliances[$t.Owner.ToLowerInvariant()] = @{ Id = $t.Owner; Type = $t.OwnerType; Ip = $t.HopIp } }
    }

    foreach ($a in $appliances.Values) {
        $name = Get-ArmName $a.Id
        $targets = @($plan.Targets | Where-Object { Test-SameArmId $_.Owner $a.Id })
        $paths = @($targets | ForEach-Object { $_.Path } | Select-Object -Unique)
        $ev = Get-Ev $Evidence $a.Id
        $title = 'Network virtual appliance'
        $gap = New-ReadGap $ev -Id nva.identified -Area Nva -Title $title -Layer Route -Resource $a.Id -What "appliance '$name'"
        if ($gap) { $out.Add($gap); continue }
        if ($ev.NotFound) {
            $out.Add((New-DiagResult -Id nva.identified -Area Nva -Title $title -Status Problem -Severity High -Layer Route -Resource $a.Id `
                -Seen "Agent traffic is routed to $($a.Ip), owned by '$name', which no longer exists." -Owner NetworkTeam `
                -Action "Update the agent subnet's routes to point at a working appliance IP." -Evidence (Get-EvRef $ev)))
            continue
        }

        # NICs that actually forward the traffic.
        $nicIds = @()
        if ($a.Type -eq 'LoadBalancer') {
            $lb = $ev.Data
            $nicIds = @($lb.properties.backendAddressPools | ForEach-Object { Get-EgressProp $_ 'backendIPConfigurations' } | Where-Object { $_ -and $_.id } |
                ForEach-Object { Get-ArmParent $_.id } | Select-Object -Unique)
            if (!$nicIds.Count) {
                $out.Add((New-DiagResult -Id nva.identified -Area Nva -Title $title -Status Problem -Severity High -Layer Route -Resource $a.Id `
                    -Seen "Agent traffic is routed to load balancer '$name' ($($a.Ip)), which has no backend appliances." `
                    -Likely 'Consistent with all traffic sent to the load balancer being dropped.' -Owner NetworkTeam `
                    -Action "Add the appliance network interfaces to a backend pool of '$name' (with an HA-ports rule), or route the agent subnet to a working appliance." -Evidence (Get-EvRef $ev)))
                continue
            }
            $out.Add((New-DiagResult -Id nva.identified -Area Nva -Title $title -Status OK -Layer Route -Resource $a.Id `
                -Seen "Next hop $($a.Ip) is load balancer '$name' ($($lb.sku.name)) in front of $($nicIds.Count) appliance interface(s)." -Evidence (Get-EvRef $ev) -Details @{ backends = $nicIds }))
        }
        else { $nicIds = @($a.Id) }

        $nicResults = foreach ($nicId in $nicIds) {
            $nicName = Get-ArmName $nicId
            $nic = $(if (Test-SameArmId $nicId $a.Id) { $ev } else { Get-Ev $Evidence $nicId })
            $gap = New-ReadGap $nic -Id nva.identified -Area Nva -Title $title -Layer Route -Resource $nicId -What "appliance interface '$nicName'"
            if ($gap) { $out.Add($gap); continue }
            if (!$nic.Ok) { continue }
            $np = $nic.Data.properties
            $vmId = $np.virtualMachine.id
            $image = $null
            if ($vmId) {
                $vm = Get-Ev $Evidence $vmId
                if ($vm.Ok) {
                    $plan2 = $vm.Data.plan; $img = $vm.Data.properties.storageProfile.imageReference
                    $image = $(if ($plan2.publisher) { "$($plan2.publisher)/$($plan2.product)" } elseif ($img.publisher) { "$($img.publisher)/$($img.offer)" } else { $null })
                }
            }
            if ($a.Type -ne 'LoadBalancer') {
                $out.Add((New-DiagResult -Id nva.identified -Area Nva -Title $title -Status OK -Layer Route -Resource $nicId `
                    -Seen "Next hop $($a.Ip) is $(if ($vmId) { "virtual machine '$(Get-ArmName $vmId)'" } else { "network interface '$nicName'" })$(if ($image) { " (image $image)" })." `
                    -Evidence (Get-EvRef $nic) -Details @{ vm = $vmId; image = $image }))
            }
            @{ Id = $nicId; Name = $nicName; Ev = $nic; Data = $nic.Data; Vm = $vmId; Image = $image }
        }
        $nicResults = @($nicResults)

        foreach ($path in $paths) {
            $pathTargets = @($targets | Where-Object { $_.Path -eq $path })
            $hosts = Get-EgressHostList $pathTargets
            $label = Get-EgressPathLabel $path
            foreach ($n in $nicResults) {
                $np = $n.Data.properties
                # nva.ipForwarding
                $title = "Appliance IP forwarding for $label traffic"
                if (!$np.enableIPForwarding) {
                    $out.Add((New-DiagResult -Id nva.ipForwarding -Area Nva -Title $title -Status Problem -Severity High -Path $path -Layer Route -Resource $n.Id `
                        -Seen "Agent traffic to $hosts is routed through '$($n.Name)', but IP forwarding is off on that network interface, so Azure drops traffic not addressed to it." `
                        -Likely "Consistent with $label connections from the agent subnet timing out." -Owner NetworkTeam `
                        -Action "Enable IP forwarding on network interface '$($n.Name)' (and make sure forwarding is on inside the appliance's operating system)." -Evidence (Get-EvRef $n.Ev)))
                }
                else {
                    $out.Add((New-DiagResult -Id nva.ipForwarding -Area Nva -Title $title -Status OK -Path $path -Layer Route -Resource $n.Id `
                        -Seen "IP forwarding is on for '$($n.Name)'." -Evidence (Get-EvRef $n.Ev)))
                }

                # nva.nsg — NIC and subnet NSGs must allow forwarded agent traffic in.
                $title = "Appliance network security groups for $label traffic"
                $nsgIds = @(@($np.networkSecurityGroup.id) | Where-Object { $_ })
                $subnetId = (Get-EgressProp @($np.ipConfigurations)[0] 'subnet').id
                $limit = $null
                if ($subnetId) {
                    $subnet = Get-Ev $Evidence $subnetId
                    $gap = New-ReadGap $subnet -Id nva.nsg -Area Nva -Title $title -Layer Nsg -Path $path -Resource $n.Id -What "appliance subnet '$(Get-ArmName $subnetId)'"
                    if ($gap) { $limit = $gap }
                    elseif ($subnet.Ok -and $subnet.Data.properties.networkSecurityGroup.id) { $nsgIds += $subnet.Data.properties.networkSecurityGroup.id }
                }
                $denied = $null; $refs = @(Get-EvRef $n.Ev)
                foreach ($nsgId in ($nsgIds | Select-Object -Unique)) {
                    $nsg = Get-Ev $Evidence $nsgId
                    $gap = New-ReadGap $nsg -Id nva.nsg -Area Nva -Title $title -Layer Nsg -Path $path -Resource $n.Id -What "network security group '$(Get-ArmName $nsgId)'"
                    if ($gap) { $limit = $gap; continue }
                    if (!$nsg.Ok) { continue }
                    $refs += Get-EvRef $nsg
                    foreach ($t in $pathTargets) {
                        $rule = Get-NvaNsgDecision $nsg.Data $t $prefixes
                        if (!$rule -or $rule.Access -eq 'Deny') { $denied = @{ Nsg = $nsgId; Rule = $rule; Target = $t }; break }
                    }
                    if ($denied) { break }
                }
                if ($denied) {
                    $ruleText = $(if ($denied.Rule) { "rule '$($denied.Rule.Name)' (priority $($denied.Rule.Priority))" } else { 'no rule' })
                    $out.Add((New-DiagResult -Id nva.nsg -Area Nva -Title $title -Status Problem -Severity High -Path $path -Layer Nsg -Resource $n.Id `
                        -Seen "Network security group '$(Get-ArmName $denied.Nsg)' on appliance '$($n.Name)' denies TCP 443 from $prefixText to $($denied.Target.Host) with $ruleText." `
                        -Likely "Consistent with $label connections being dropped before they reach the appliance." -Owner NetworkTeam `
                        -Action "Add an inbound rule to '$(Get-ArmName $denied.Nsg)' allowing TCP 443 from $prefixText to $(if ($denied.Target.Ip) { $denied.Target.Ip } else { 'Internet' })$(if ($denied.Rule) { " with a priority number lower than $($denied.Rule.Priority)" })." `
                        -Evidence $refs -Details @{ nsg = $denied.Nsg; rule = $denied.Rule.Name }))
                }
                elseif ($limit) { $out.Add($limit) }
                else {
                    $out.Add((New-DiagResult -Id nva.nsg -Area Nva -Title $title -Status OK -Path $path -Layer Nsg -Resource $n.Id `
                        -Seen $(if ($nsgIds.Count) { "The appliance's network security groups allow TCP 443 from $prefixText (assuming the VirtualNetwork tag covers forwarded destinations)." } else { "No network security group on appliance '$($n.Name)' or its subnet." }) `
                        -Evidence $refs))
                }
            }

            # nva.rules — can't read third-party rules.
            $out.Add((New-DiagResult -Id nva.rules -Area Nva -Title "Appliance rules for $label traffic" -Status CouldNotCheck -Gap KnownLimit -Path $path -Layer Firewall -Resource $a.Id `
                -Seen "Agent traffic to $hosts goes through appliance '$name'$(if (@($nicResults | Where-Object { $_.Image }).Count) { " ($(@($nicResults | Where-Object { $_.Image })[0].Image))" }); its rules can't be read from Azure." `
                -Needs (Get-NvaChecklist $hosts $prefixText) -Details @{ appliance = $a.Id; nextHop = $a.Ip; hosts = @($pathTargets | ForEach-Object { $_.Host }) }))
        }
    }

    # onprem.route — UDR sends evaluation traffic to the virtual network gateway.
    foreach ($path in @($plan.Targets | Where-Object { $_.HopType -eq 'VirtualNetworkGateway' } | ForEach-Object { $_.Path } | Select-Object -Unique)) {
        $pathTargets = @($plan.Targets | Where-Object { $_.Path -eq $path -and $_.HopType -eq 'VirtualNetworkGateway' })
        $hosts = Get-EgressHostList $pathTargets
        $out.Add((New-DiagResult -Id onprem.route -Area Nva -Title "On-premises route for $(Get-EgressPathLabel $path) traffic" -Status CouldNotCheck -Gap KnownLimit -Path $path -Layer Route `
            -Resource $plan.RouteTableId -Seen "Route '$($pathTargets[0].Route)' sends $hosts to the virtual network gateway, so the traffic leaves Azure through on-premises devices this tool can't read." `
            -Needs "Ask the network team to confirm the on-premises path: $(Get-NvaChecklist $hosts $prefixText)" -Details @{ route = $pathTargets[0].Route; prefix = $pathTargets[0].RoutePrefix }))
    }

    , $out.ToArray()
}
