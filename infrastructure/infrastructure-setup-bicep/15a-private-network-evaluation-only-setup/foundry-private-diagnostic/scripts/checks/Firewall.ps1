# Azure Firewall checks: run for each Azure Firewall the agent traffic goes through (route table next hop or Virtual WAN hub).
# Rule matching is an inference from the firewall configuration; the tool never reads firewall logs.
# Uses the egress plan from Egress.ps1.

$script:FirewallSnatLimit = 80
$script:FirewallLogCategories = @('AZFWApplicationRule', 'AZFWNetworkRule', 'AZFWIdpsSignature', 'AZFWThreatIntel')

function Get-FirewallList {
    param($Value)
    @($Value | Where-Object { $null -ne $_ -and "$_" -ne '' } | ForEach-Object { "$_" })
}

function Test-FirewallFqdnMatch {
    param([string]$Pattern, [string]$HostName)
    if (!$Pattern) { return $false }
    $Pattern = $Pattern.Trim()
    if ($Pattern -eq '*') { return $true }
    if ($Pattern.StartsWith('*')) { return $HostName -like $Pattern }
    $HostName -ieq $Pattern
}

function Test-FirewallPort443 {
    param($Ports)
    foreach ($port in (Get-FirewallList $Ports)) {
        if ($port -eq '*' -or $port -eq '443') { return $true }
        if ($port -match '^(\d+)\s*-\s*(\d+)$' -and [int]$Matches[1] -le 443 -and [int]$Matches[2] -ge 443) { return $true }
    }
    $false
}

# Yes when the rule's sources cover the whole agent subnet; Unknown for IP groups or partial overlap.
function Test-FirewallSource {
    param($Rule, [string[]]$Prefixes)
    $sources = Get-FirewallList (Get-EgressProp $Rule 'sourceAddresses')
    if ($sources -contains '*') { return 'Yes' }
    if ($Prefixes.Count) {
        $covered = @($Prefixes | Where-Object { $p = $_; @($sources | Where-Object { Test-EgressCidrContains $_ $p }).Count })
        if ($covered.Count -eq $Prefixes.Count) { return 'Yes' }
        $overlap = @($sources | Where-Object { $s = $_; @($Prefixes | Where-Object { Test-EgressCidrContains $_ $s }).Count })
        if ($covered.Count -or $overlap.Count) { return 'Unknown' }
    }
    if ((Get-FirewallList (Get-EgressProp $Rule 'sourceIpGroups')).Count) { return 'Unknown' }
    'No'
}

function Test-FirewallRuleMatch {
    param([string]$Kind, $Rule, $Target, [string[]]$Prefixes)
    $no = @{ Match = 'No' }
    $source = Test-FirewallSource $Rule $Prefixes
    if ($source -eq 'No') { return $no }
    $match = 'No'; $viaFqdn = $false; $tls = $false
    if ($Kind -eq 'Network') {
        $protocols = Get-FirewallList $(if (Get-EgressProp $Rule 'ipProtocols') { Get-EgressProp $Rule 'ipProtocols' } else { Get-EgressProp $Rule 'protocols' })
        if (!@($protocols | Where-Object { $_ -in @('TCP', 'Any') }).Count) { return $no }
        if (!(Test-FirewallPort443 (Get-EgressProp $Rule 'destinationPorts'))) { return $no }
        foreach ($dest in (Get-FirewallList (Get-EgressProp $Rule 'destinationAddresses'))) {
            if ($dest -eq '*' -or ($Target.Ip -and (Test-EgressCidrContains $dest $Target.Ip)) -or (!$Target.Ip -and (Test-EgressTagMatch $dest $Target.Path))) { $match = 'Yes' }
        }
        if ($match -eq 'No' -and @(Get-FirewallList (Get-EgressProp $Rule 'destinationFqdns') | Where-Object { Test-FirewallFqdnMatch $_ $Target.Host }).Count) { $match = 'Yes'; $viaFqdn = $true }
    }
    else {
        $https = @(@(Get-EgressProp $Rule 'protocols') | Where-Object { $_ -and (Get-EgressProp $_ 'protocolType') -eq 'Https' -and ("$(Get-EgressProp $_ 'port')" -in @('443', '')) }).Count
        if (!$https) { return $no }
        $urlHosts = @(Get-FirewallList (Get-EgressProp $Rule 'targetUrls') | ForEach-Object { ($_ -replace '^https?://', '' -split '/')[0] })
        if (@(@(Get-FirewallList (Get-EgressProp $Rule 'targetFqdns')) + $urlHosts | Where-Object { Test-FirewallFqdnMatch $_ $Target.Host }).Count) {
            $match = 'Yes'; $tls = [bool](Get-EgressProp $Rule 'terminateTLS')
        }
        elseif ((Get-FirewallList (Get-EgressProp $Rule 'webCategories')).Count) { $match = 'Unknown' }
    }
    if ($match -eq 'No') { return $no }
    @{ Match = $(if ($source -eq 'Unknown') { 'Unknown' } else { $match }); ViaFqdn = $viaFqdn; Tls = $tls }
}

# Reads the policy and its parents. Returns the chain root-first, or the first read that failed.
function Get-FirewallPolicyChain {
    param($Evidence, [string]$PolicyId)
    $chain = [Collections.Generic.List[object]]::new()
    $id = $PolicyId
    $seen = @{}
    while ($id -and !$seen[$id.ToLowerInvariant()] -and $chain.Count -lt 5) {
        $seen[$id.ToLowerInvariant()] = $true
        $policy = Get-Ev $Evidence $id
        if (!$policy.Ok) { return @{ Failed = $policy; FailedWhat = "firewall policy '$(Get-ArmName $id)'"; Chain = @() } }
        $groups = Get-Ev $Evidence "$id/ruleCollectionGroups"
        if (!$groups.Ok) { return @{ Failed = $groups; FailedWhat = "rule collection groups of policy '$(Get-ArmName $id)'"; Chain = @() } }
        $chain.Insert(0, @{ Id = $id; Name = (Get-ArmName $id); Policy = $policy; Groups = $groups })
        $id = $policy.Data.properties.basePolicy.id
    }
    @{ Failed = $null; Chain = $chain.ToArray() }
}

# Rule collections in Azure Firewall processing order: network before application; parent policy before child;
# then rule collection group priority, then rule collection priority.
function Get-FirewallCollections {
    param($Chain, $FirewallData)
    $items = [Collections.Generic.List[object]]::new()
    $child = $(if ($Chain.Count) { $Chain[-1].Id } else { $null })
    foreach ($kind in @('Network', 'Application')) {
        if ($Chain.Count) {
            foreach ($link in $Chain) {
                $groups = @($link.Groups.Data | Where-Object { $_ }) | Sort-Object { [int](Get-EgressProp $_ 'priority') }
                foreach ($group in $groups) {
                    $collections = @(Get-EgressProp $group 'ruleCollections' | Where-Object { $_ -and $_.ruleCollectionType -ne 'FirewallPolicyNatRuleCollection' }) | Sort-Object { [int]$_.priority }
                    foreach ($rc in $collections) {
                        $rules = @($rc.rules | Where-Object { $_ -and ($_.ruleType -eq "${kind}Rule" -or (!$_.ruleType -and $kind -eq 'Network')) })
                        if (!$rules.Count) { continue }
                        $items.Add(@{ Kind = $kind; PolicyId = $link.Id; Policy = $link.Name; Inherited = !(Test-SameArmId $link.Id $child)
                            Group = $group.name; GroupPriority = (Get-EgressProp $group 'priority'); Name = $rc.name; Priority = $rc.priority; Action = $rc.action.type; Rules = $rules })
                    }
                }
            }
        }
        else {
            $field = $(if ($kind -eq 'Network') { 'networkRuleCollections' } else { 'applicationRuleCollections' })
            $collections = @($FirewallData.properties[$field] | Where-Object { $_ }) | Sort-Object { [int](Get-EgressProp $_ 'priority') }
            foreach ($rc in $collections) {
                $items.Add(@{ Kind = $kind; PolicyId = $FirewallData.id; Policy = $null; Inherited = $false; Group = $null; GroupPriority = $null
                    Name = $rc.name; Priority = (Get-EgressProp $rc 'priority'); Action = (Get-EgressProp $rc 'action').type; Rules = @(Get-EgressProp $rc 'rules' | Where-Object { $_ }) })
            }
        }
    }
    , $items.ToArray()
}

function Get-FirewallDecision {
    param($Collections, $Target, [string[]]$Prefixes)
    $unknown = $null; $decisive = $null
    foreach ($rc in $Collections) {
        foreach ($rule in $rc.Rules) {
            $m = Test-FirewallRuleMatch $rc.Kind $rule $Target $Prefixes
            if ($m.Match -eq 'No') { continue }
            $hit = @{ Action = $rc.Action; Collection = $rc; Rule = $rule.name; ViaFqdn = $m.ViaFqdn; Tls = $m.Tls }
            if ($m.Match -eq 'Unknown') { if (!$unknown) { $unknown = $hit }; continue }
            $decisive = $hit; break
        }
        if ($decisive) { break }
    }
    $outcome = $(if ($decisive) { $decisive.Action } else { 'NoMatch' })
    if ($unknown -and (!$decisive -or $unknown.Action -ne $decisive.Action)) { $outcome = 'Unknown' }
    @{ Target = $Target; Outcome = $outcome; Hit = $decisive; Unknown = $unknown }
}

function Get-FirewallCollectionText {
    param($Rc)
    $where = $(if ($Rc.Group) { " in group '$($Rc.Group)' (priority $($Rc.GroupPriority))" } else { '' })
    $policy = $(if ($Rc.Policy) { " of policy '$($Rc.Policy)'$(if ($Rc.Inherited) { ' (parent)' })" } else { '' })
    "$($Rc.Kind.ToLowerInvariant()) rule collection '$($Rc.Name)' (priority $($Rc.Priority), $($Rc.Action))$where$policy"
}

# A policy setting from the child policy, falling back to its parents.
function Get-FirewallPolicySetting {
    param($Chain, [scriptblock]$Pick)
    $links = @($Chain)
    for ($i = $links.Count - 1; $i -ge 0; $i--) {
        $v = & $Pick $links[$i].Policy.Data
        if ($null -ne $v -and "$v" -ne '') { return $v }
    }
    $null
}

# Threat intelligence and IDPS: a child policy can only make the parent's mode stricter, so the strictest mode applies.
function Get-FirewallStrictestMode {
    param($Chain, [scriptblock]$Pick)
    $rank = @{ Off = 0; Alert = 1; Deny = 2 }
    $best = $null
    foreach ($link in @($Chain)) {
        $v = "$(& $Pick $link.Policy.Data)"
        if ($rank.ContainsKey($v) -and ($null -eq $best -or $rank[$v] -gt $rank[$best])) { $best = $v }
    }
    $best
}

function Get-FirewallLogQuery {
    param([string[]]$Prefixes, [string[]]$Hosts, [string[]]$Ips)
    $prefixList = ($Prefixes | ForEach-Object { "`"$_`"" }) -join ', '
    $targetList = (@($Hosts) + @($Ips) | Where-Object { $_ } | ForEach-Object { "`"$_`"" }) -join ', '
    @"
// Azure Firewall decisions for the agent subnet around the incident (resource-specific log tables).
// Replace <INCIDENT_TIME_UTC> with the time an evaluation failed, e.g. 2026-10-22T17:00:00Z.
let incident = datetime(<INCIDENT_TIME_UTC>);
let agentPrefixes = dynamic([$prefixList]);
let targets = dynamic([$targetList]);
union isfuzzy=true
    (AZFWApplicationRule | project TimeGenerated, Log = "Application", SourceIp, Target = Fqdn, DestinationPort, Action, Policy, RuleCollectionGroup, RuleCollection, Rule, ActionReason, IsTlsInspected),
    (AZFWNetworkRule | project TimeGenerated, Log = "Network", SourceIp, Target = DestinationIp, DestinationPort, Action, Policy, RuleCollectionGroup, RuleCollection, Rule, ActionReason),
    (AZFWIdpsSignature | project TimeGenerated, Log = "IDPS", SourceIp, Target = DestinationIp, DestinationPort, Action, Rule = tostring(SignatureId), ActionReason = Description),
    (AZFWThreatIntel | project TimeGenerated, Log = "ThreatIntel", SourceIp, Target = Fqdn, DestinationPort, Action, ActionReason = ThreatDescription)
| where TimeGenerated between ((incident - 30m) .. (incident + 30m))
| where ipv4_is_in_any_range(SourceIp, agentPrefixes)
| extend IsTarget = Target in~ (targets) or Log in ("IDPS", "ThreatIntel")
| summarize Count = count(), First = min(TimeGenerated), Last = max(TimeGenerated)
    by Log, Target, DestinationPort, Action, Policy, RuleCollectionGroup, RuleCollection, Rule, ActionReason, IsTarget
| order by IsTarget desc, Count desc
"@
}

function Test-DiagFirewall {
    param($Evidence)
    $plan = Get-EgressPlan $Evidence
    if (!$plan.Ready) { return , @() }
    $out = [Collections.Generic.List[object]]::new()
    $prefixes = @($plan.AgentPrefixes)
    $prefixText = $(if ($prefixes.Count) { $prefixes -join ', ' } else { 'the agent subnet' })

    $ids = @(@($plan.Firewalls) + @($plan.Targets | Where-Object { $_.OwnerType -eq 'AzureFirewall' -and $_.Owner } | ForEach-Object { $_.Owner }))
    $firewalls = [Collections.Generic.List[string]]::new()
    foreach ($id in $ids) { if (!@($firewalls | Where-Object { Test-SameArmId $_ $id }).Count) { $firewalls.Add($id) } }

    foreach ($fwId in $firewalls) {
        $fwName = Get-ArmName $fwId
        $fwTargets = @($plan.Targets | Where-Object { $_.OwnerType -eq 'AzureFirewall' -and (Test-SameArmId $_.Owner $fwId) })
        $paths = @($fwTargets | ForEach-Object { $_.Path } | Select-Object -Unique)
        $pathSlots = $(if ($paths.Count) { $paths } else { @($null) })
        $fw = Get-Ev $Evidence $fwId

        # firewall.state
        $title = 'Azure Firewall state'
        if (!$fw.Ok) {
            foreach ($path in $pathSlots) {
                $gap = New-ReadGap $fw -Id firewall.state -Area Firewall -Title $title -Layer Firewall -Path $path -Resource $fwId -What "Azure Firewall '$fwName'"
                if ($gap) { $out.Add($gap) }
                else {
                    $out.Add((New-DiagResult -Id firewall.state -Area Firewall -Title $title -Status Problem -Severity High -Path $path -Layer Firewall -Resource $fwId `
                        -Seen "Agent traffic is routed to Azure Firewall '$fwName', which was not found." -Owner NetworkTeam `
                        -Action "Point the agent subnet's routes at a firewall that exists, or redeploy '$fwName'." -Evidence (Get-EvRef $fw)))
                }
            }
            continue
        }
        $fp = $fw.Data.properties
        $sku = "$($fp.sku.tier)"
        $policyId = $fp.firewallPolicy.id
        $state = $fp.provisioningState
        foreach ($path in $pathSlots) {
            if ($state -and $state -ne 'Succeeded') {
                $out.Add((New-DiagResult -Id firewall.state -Area Firewall -Title $title -Status Problem -Severity High -Path $path -Layer Firewall -Resource $fwId `
                    -Seen "Azure Firewall '$fwName' is in state '$state'." -Likely 'Consistent with traffic through the firewall being dropped.' -Owner NetworkTeam `
                    -Action "Fix firewall '$fwName': check its last operation in the portal and re-apply its configuration." -Evidence (Get-EvRef $fw) -Details @{ provisioningState = $state }))
            }
            else {
                $how = $(if ($policyId) { "policy '$(Get-ArmName $policyId)'" } else { 'classic rules (no firewall policy)' })
                $out.Add((New-DiagResult -Id firewall.state -Area Firewall -Title $title -Status OK -Path $path -Layer Firewall -Resource $fwId `
                    -Seen "Azure Firewall '$fwName' ($sku) is provisioned and uses $how." -Evidence (Get-EvRef $fw) -Details @{ sku = $sku; firewallPolicy = $policyId }))
            }
        }

        # Policy chain and rule collections.
        $chain = @(); $policyOk = $true
        if ($policyId) {
            $c = Get-FirewallPolicyChain $Evidence $policyId
            if ($c.Failed) {
                $policyOk = $false
                foreach ($path in $paths) {
                    $gap = New-ReadGap $c.Failed -Id firewall.ruleMatch -Area Firewall -Title 'Firewall rules for agent traffic' -Layer Firewall -Path $path -Resource $policyId -What $c.FailedWhat
                    if (!$gap) {
                        $gap = New-DiagResult -Id firewall.ruleMatch -Area Firewall -Title 'Firewall rules for agent traffic' -Status CouldNotCheck -Gap Blocking -Path $path -Layer Firewall -Resource $policyId `
                            -Seen "Couldn't find $($c.FailedWhat)." -Needs "Check the policy attached to firewall '$fwName' in the portal." -Evidence (Get-EvRef $c.Failed)
                    }
                    $out.Add($gap)
                }
            }
            else { $chain = $c.Chain }
        }
        $resource = $(if ($policyId) { $policyId } else { $fwId })
        $resourceName = Get-ArmName $resource
        $where = $(if ($policyId) { "policy '$resourceName'" } else { "firewall '$fwName'" })
        $refs = @(Get-EvRef $fw) + @($chain | ForEach-Object { (Get-EvRef $_.Policy), (Get-EvRef $_.Groups) })
        $fwIps = @(@($fp.ipConfigurations | ForEach-Object { Get-EgressProp $_ 'privateIPAddress' }) + @($fp.hubIPAddresses.privateIPAddress) | Where-Object { $_ })

        if ($policyOk) {
            $collections = Get-FirewallCollections $chain $fw.Data
            foreach ($path in $paths) {
                $targets = @($fwTargets | Where-Object { $_.Path -eq $path })
                $decisions = @($targets | ForEach-Object { Get-FirewallDecision $collections $_ $prefixes })
                $label = Get-EgressPathLabel $path
                $title = "Firewall rules for $label traffic"
                $details = @{ inferredFromConfiguration = $true; firewall = $fwId; decisions = @($decisions | ForEach-Object {
                    @{ host = $_.Target.Host; ip = $_.Target.Ip; outcome = $_.Outcome; collection = $_.Hit.Collection.Name; group = $_.Hit.Collection.Group; policy = $_.Hit.Collection.Policy; rule = $_.Hit.Rule; kind = $_.Hit.Collection.Kind } }) }
                $blocked = @($decisions | Where-Object { $_.Outcome -in @('NoMatch', 'Deny') })
                $unknown = @($decisions | Where-Object { $_.Outcome -eq 'Unknown' })
                if ($blocked.Count) {
                    $hosts = Get-EgressHostList @($blocked | ForEach-Object { $_.Target })
                    $ips = @($blocked | ForEach-Object { $_.Target.Ip } | Where-Object { $_ } | Select-Object -Unique)
                    $deny = $blocked | Where-Object { $_.Outcome -eq 'Deny' } | Select-Object -First 1
                    if ($deny) {
                        $rc = $deny.Hit.Collection
                        $seen = "Based on the configuration of $where, $(Get-FirewallCollectionText $rc) (rule '$($deny.Hit.Rule)') matches $hosts on TCP 443 from $prefixText before any allow rule."
                        $placement = $(if ($rc.Inherited) { "The deny is in parent policy '$($rc.Policy)', which is processed before '$resourceName': add the allow rule there, or narrow its deny rule '$($deny.Hit.Rule)'." }
                            else { "Put it in a rule collection processed before '$($rc.Name)' (lower priority number), or narrow deny rule '$($deny.Hit.Rule)'." })
                        if ($rc.Kind -eq 'Network') { $placement += ' Network rules are processed before application rules, so an application rule alone will not get past this deny.' }
                    }
                    else {
                        $seen = "Based on the configuration of $where, no rule allows $hosts on TCP 443 from $prefixText, so the firewall denies it by default."
                        $placement = ''
                    }
                    $action = $(if ($policyId) { "In $where, add" } else { "On firewall '$fwName', add" }) + " an application rule (Allow): source $prefixText, protocol Https:443, target FQDNs $hosts."
                    if ($deny -and $deny.Hit.Collection.Kind -eq 'Network') {
                        $tags = $(if ($ips.Count) { $ips -join ', ' } else { "service tag $(@($script:EgressPathTags[$path])[0])" })
                        $action = $(if ($policyId) { "In $where, add" } else { "On firewall '$fwName', add" }) + " a network rule (Allow): source $prefixText, protocol TCP, port 443, destination $tags."
                    }
                    elseif ($ips.Count) { $action += " For the private endpoint, a network rule (Allow) TCP 443 from $prefixText to $($ips -join ', ') also works." }
                    if ($placement) { $action += " $placement" }
                    $out.Add((New-DiagResult -Id firewall.ruleMatch -Area Firewall -Title $title -Status Problem -Severity High -Path $path -Layer Firewall -Resource $resource `
                        -Seen $seen -Likely "Consistent with $label connections being accepted and then dropped by the firewall (a read timeout or 504 after about 15 s)." `
                        -Owner NetworkTeam -Action $action -Evidence $refs -Details $details))
                }
                elseif ($unknown.Count) {
                    $u = $unknown[0].Unknown
                    $out.Add((New-DiagResult -Id firewall.ruleMatch -Area Firewall -Title $title -Status CouldNotCheck -Gap KnownLimit -Path $path -Layer Firewall -Resource $resource `
                        -Seen "Rule '$($u.Rule)' in $(Get-FirewallCollectionText $u.Collection) decides $(Get-EgressHostList @($unknown | ForEach-Object { $_.Target })), but it uses IP groups, partial source ranges or web categories this tool can't evaluate." `
                        -Needs "Confirm rule '$($u.Rule)' covers source $prefixText and the target FQDNs on TCP 443 ($($u.Action) rule)." -Evidence $refs -Details $details))
                }
                elseif ($decisions.Count) {
                    $by = @($decisions | ForEach-Object { "$($_.Target.Host) by '$($_.Hit.Collection.Name)'/'$($_.Hit.Rule)'" }) -join '; '
                    $out.Add((New-DiagResult -Id firewall.ruleMatch -Area Firewall -Title $title -Status OK -Path $path -Layer Firewall -Resource $resource `
                        -Seen "Based on the configuration of ${where}: allowed on TCP 443 from $prefixText — $by." -Evidence $refs -Details $details))
                }

                # firewall.dnsProxy — FQDN network rules only work when the firewall resolves DNS for the clients.
                $title = "Firewall DNS proxy for $label traffic"
                $fqdnRules = @($decisions | Where-Object { $_.Outcome -eq 'Allow' -and $_.Hit.ViaFqdn })
                if ($fqdnRules.Count) {
                    $proxyOn = $(if ($policyId) { [bool](Get-FirewallPolicySetting $chain { param($d) $d.properties.dnsSettings.enableProxy }) } else { "$($fp.additionalProperties.'Network.DNS.EnableProxy')" -eq 'true' })
                    $dnsToFw = [bool]@($plan.VnetDns | Where-Object { $_ -in $fwIps }).Count
                    $ruleNames = (@($fqdnRules | ForEach-Object { $_.Hit.Rule } | Select-Object -Unique) -join ', ')
                    if (!$proxyOn -or !$dnsToFw) {
                        $missing = @(if (!$proxyOn) { "DNS proxy is off on $where" }) + @(if (!$dnsToFw) { "the agent virtual network's DNS servers ($(if ($plan.VnetDns.Count) { $plan.VnetDns -join ', ' } else { 'Azure-provided' })) don't point at the firewall" })
                        $out.Add((New-DiagResult -Id firewall.dnsProxy -Area Firewall -Title $title -Status Problem -Severity Medium -Path $path -Layer Firewall -Resource $resource `
                            -Seen "Network rule(s) $ruleNames allow $(Get-EgressHostList @($fqdnRules | ForEach-Object { $_.Target })) by FQDN, but $($missing -join ' and ')." `
                            -Likely 'Consistent with intermittent drops when the agent and the firewall resolve the name to different IPs.' -Owner NetworkTeam `
                            -Action "Enable DNS proxy on $where and set the agent virtual network's DNS servers to the firewall's private IP ($($fwIps -join ', ')), or replace the FQDN network rule with an application rule (Https:443)." `
                            -Evidence $refs -Details @{ dnsProxy = $proxyOn; vnetDnsServers = $plan.VnetDns; firewallIps = $fwIps }))
                    }
                    else {
                        $out.Add((New-DiagResult -Id firewall.dnsProxy -Area Firewall -Title $title -Status OK -Path $path -Layer Firewall -Resource $resource `
                            -Seen 'DNS proxy is on and the agent virtual network uses the firewall for DNS, as FQDN network rules need.' -Evidence $refs))
                    }
                }
                else {
                    $out.Add((New-DiagResult -Id firewall.dnsProxy -Area Firewall -Title $title -Status OK -Path $path -Layer Firewall -Resource $resource `
                        -Seen 'No FQDN network rule is needed for this traffic, so DNS proxy is not required.' -Evidence $refs))
                }

                # firewall.tlsInspection
                $title = "Firewall TLS inspection for $label traffic"
                $tls = @($decisions | Where-Object { $_.Outcome -eq 'Allow' -and $_.Hit.Tls })
                if ($tls.Count) {
                    $ruleNames = (@($tls | ForEach-Object { "'$($_.Hit.Rule)' in '$($_.Hit.Collection.Name)'" } | Select-Object -Unique) -join ', ')
                    $hosts = Get-EgressHostList @($tls | ForEach-Object { $_.Target })
                    $out.Add((New-DiagResult -Id firewall.tlsInspection -Area Firewall -Title $title -Status Problem -Severity Medium -Path $path -Layer Firewall -Resource $resource `
                        -Seen "Rule $ruleNames allows $hosts with TLS inspection on, so the firewall re-signs these connections with its own certificate." `
                        -Likely 'Consistent with the agent rejecting the certificate or long calls stalling.' -Owner NetworkTeam `
                        -Action "Turn off TLS inspection (terminateTLS) for $hosts on Https:443: edit rule $ruleNames, or add a rule without TLS inspection for these FQDNs from $prefixText in a collection processed earlier." `
                        -Evidence $refs -Details @{ certificateAuthority = (Get-FirewallPolicySetting $chain { param($d) $d.properties.transportSecurity.certificateAuthority.name }) }))
                }
                else {
                    $out.Add((New-DiagResult -Id firewall.tlsInspection -Area Firewall -Title $title -Status OK -Path $path -Layer Firewall -Resource $resource `
                        -Seen 'The matching rules do not use TLS inspection.' -Evidence $refs))
                }

                # firewall.idps
                if ($policyId) {
                    $title = "Firewall intrusion detection for $label traffic"
                    $mode = Get-FirewallStrictestMode $chain { param($d) $d.properties.intrusionDetection.mode }
                    if ($mode -eq 'Deny') {
                        $out.Add((New-DiagResult -Id firewall.idps -Area Firewall -Title $title -Status Problem -Severity Medium -Path $path -Layer Firewall -Resource $resource `
                            -Seen "Intrusion detection (IDPS) on $where is in Deny mode, so signature matches drop connections silently." `
                            -Likely 'Consistent with some connections stalling after they were accepted.' -Owner NetworkTeam `
                            -Action "Check AZFWIdpsSignature logs for $prefixText at the incident time (query in the firewall log query result); add an IDPS bypass for $prefixText to $(Get-EgressHostList $targets) on TCP 443, or switch IDPS to Alert while you investigate." `
                            -Evidence $refs -Details @{ mode = $mode }))
                    }
                    else {
                        $out.Add((New-DiagResult -Id firewall.idps -Area Firewall -Title $title -Status OK -Path $path -Layer Firewall -Resource $resource `
                            -Seen "Intrusion detection is $(if ($mode) { $mode } else { 'off' })." -Evidence $refs -Details @{ mode = $mode }))
                    }
                }
            }

            # firewall.threatIntel
            $title = 'Firewall threat intelligence'
            $mode = $(if ($policyId) { Get-FirewallStrictestMode $chain { param($d) $d.properties.threatIntelMode } } else { $fp.threatIntelMode })
            if ($mode -eq 'Deny') {
                $out.Add((New-DiagResult -Id firewall.threatIntel -Area Firewall -Title $title -Status Problem -Severity Low -Layer Firewall -Resource $resource `
                    -Seen "Threat intelligence on $where is in Deny mode." -Owner NetworkTeam `
                    -Action 'Keep Deny if your policy needs it; if evaluations fail, check AZFWThreatIntel logs at the incident time and add the evaluation FQDNs to the threat intelligence allow list.' `
                    -Evidence $refs -Details @{ mode = $mode }))
            }
            else {
                $out.Add((New-DiagResult -Id firewall.threatIntel -Area Firewall -Title $title -Status OK -Layer Firewall -Resource $resource `
                    -Seen "Threat intelligence is $(if ($mode) { $mode } else { 'Alert (default)' })." -Evidence $refs))
            }
        }

        # firewall.snat
        $title = 'Firewall SNAT port use'
        $metrics = Get-Ev $Evidence "$fwId/providers/Microsoft.Insights/metrics"
        $gap = New-ReadGap $metrics -Id firewall.snat -Area Firewall -Title $title -Layer Firewall -Resource $fwId -What "SNAT metrics of '$fwName'"
        if ($gap) { $gap.gap = 'KnownLimit'; $out.Add($gap) }
        elseif ($metrics.Ok) {
            $m = @($metrics.Data)[0]
            if ($null -eq $m.maximum) {
                $out.Add((New-DiagResult -Id firewall.snat -Area Firewall -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Firewall -Resource $fwId `
                    -Seen "Azure Monitor returned no SNAT port data for '$fwName' in the last 24 hours." -Needs 'Check the SNAT port utilization metric in the portal.' -Evidence (Get-EvRef $metrics)))
            }
            elseif ([double]$m.maximum -ge $script:FirewallSnatLimit) {
                $out.Add((New-DiagResult -Id firewall.snat -Area Firewall -Title $title -Status Problem -Severity Medium -Layer Firewall -Resource $fwId `
                    -Seen "SNAT port use on '$fwName' peaked at $([math]::Round([double]$m.maximum))% in the last 24 hours (average $([math]::Round([double]$m.average))%)." `
                    -Likely 'Consistent with new outbound connections failing or stalling at busy times.' -Owner NetworkTeam `
                    -Action "Add public IP addresses to firewall '$fwName' (or attach a NAT gateway to its subnet) to increase SNAT ports." -Evidence (Get-EvRef $metrics) -Details @{ maximum = $m.maximum; average = $m.average; timespan = $m.timespan }))
            }
            else {
                $out.Add((New-DiagResult -Id firewall.snat -Area Firewall -Title $title -Status OK -Layer Firewall -Resource $fwId `
                    -Seen "SNAT port use peaked at $([math]::Round([double]$m.maximum))% in the last 24 hours." -Evidence (Get-EvRef $metrics) -Details @{ maximum = $m.maximum; average = $m.average }))
            }
        }

        # firewall.logs
        $title = 'Firewall diagnostic logs'
        $diag = Get-Ev $Evidence "$fwId/providers/Microsoft.Insights/diagnosticSettings"
        $gap = New-ReadGap $diag -Id firewall.logs -Area Firewall -Title $title -Layer Firewall -Resource $fwId -What "diagnostic settings of '$fwName'"
        $workspace = $null
        if ($gap) { $gap.gap = 'KnownLimit'; $out.Add($gap) }
        elseif ($diag.Ok) {
            $sending = @(@($diag.Data) | Where-Object {
                $_ -and ((Get-EgressProp $_ 'workspaceId') -or (Get-EgressProp $_ 'storageAccountId') -or (Get-EgressProp $_ 'eventHubName')) -and
                @(@(Get-EgressProp $_ 'logs') | Where-Object { $_ -and $_.enabled }).Count })
            $workspace = @($sending | ForEach-Object { Get-EgressProp $_ 'workspaceId' } | Where-Object { $_ })[0]
            if ($sending.Count) {
                $out.Add((New-DiagResult -Id firewall.logs -Area Firewall -Title $title -Status OK -Layer Firewall -Resource $fwId `
                    -Seen "Diagnostic setting '$($sending[0].name)' sends firewall logs$(if ($workspace) { " to workspace '$(Get-ArmName $workspace)'" })." -Evidence (Get-EvRef $diag)))
            }
            else {
                $out.Add((New-DiagResult -Id firewall.logs -Area Firewall -Title $title -Status Problem -Severity Low -Layer Firewall -Resource $fwId `
                    -Seen "Firewall '$fwName' doesn't send its logs anywhere, so dropped connections can't be investigated." -Owner NetworkTeam `
                    -Action "Add a diagnostic setting on '$fwName' sending $($script:FirewallLogCategories -join ', ') (resource-specific tables) to a Log Analytics workspace." -Evidence (Get-EvRef $diag)))
            }
        }

        # firewall.logQuery — output only.
        $hosts = @($fwTargets | ForEach-Object { $_.Host } | Select-Object -Unique)
        $ips = @($fwTargets | ForEach-Object { $_.Ip } | Where-Object { $_ } | Select-Object -Unique)
        if (!$hosts.Count) { $hosts = $script:EgressMonitorQueryHosts }
        $out.Add((New-DiagResult -Id firewall.logQuery -Area Firewall -Title 'Firewall log query' -Status OK -Layer Firewall -Resource $fwId `
            -Seen "Run the query in the details $(if ($workspace) { "in workspace '$(Get-ArmName $workspace)'" } else { "in the workspace that receives '$fwName' logs" }) after replacing <INCIDENT_TIME_UTC> with the failure time; it lists what the firewall did with agent traffic." `
            -Details @{ kql = (Get-FirewallLogQuery $prefixes $hosts $ips); workspace = $workspace }))
    }
    , $out.ToArray()
}
