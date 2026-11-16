# NSG checks: agent subnet outbound, private endpoint subnet inbound, and the runner's NSG vs the agent subnet's.

$script:DiagNsgPathTags = @{ Foundry = @('CognitiveServicesFrontend'); Models = @('CognitiveServicesFrontend'); Storage = @('Storage'); MonitorQuery = @('AzureMonitor') }
$script:DiagNsgBuiltInRules = @(
    @{ name = 'AllowVnetInBound'; properties = @{ priority = 65000; direction = 'Inbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = 'VirtualNetwork'; destinationAddressPrefix = 'VirtualNetwork'; destinationPortRange = '*' } }
    @{ name = 'AllowAzureLoadBalancerInBound'; properties = @{ priority = 65001; direction = 'Inbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = 'AzureLoadBalancer'; destinationAddressPrefix = '*'; destinationPortRange = '*' } }
    @{ name = 'DenyAllInBound'; properties = @{ priority = 65500; direction = 'Inbound'; access = 'Deny'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = '*'; destinationPortRange = '*' } }
    @{ name = 'AllowVnetOutBound'; properties = @{ priority = 65000; direction = 'Outbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = 'VirtualNetwork'; destinationAddressPrefix = 'VirtualNetwork'; destinationPortRange = '*' } }
    @{ name = 'AllowInternetOutBound'; properties = @{ priority = 65001; direction = 'Outbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = 'Internet'; destinationPortRange = '*' } }
    @{ name = 'DenyAllOutBound'; properties = @{ priority = 65500; direction = 'Outbound'; access = 'Deny'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = '*'; destinationPortRange = '*' } }
)

function ConvertTo-DiagIpRange {
    param([string]$Prefix)
    if (!$Prefix -or $Prefix.Trim() -notmatch '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?:/(\d{1,2}))?$') { return $null }
    $octets = @([uint64]$Matches[1], [uint64]$Matches[2], [uint64]$Matches[3], [uint64]$Matches[4])
    if (@($octets | Where-Object { $_ -gt 255 }).Count) { return $null }
    $bits = if ($Matches[5]) { [int]$Matches[5] } else { 32 }
    if ($bits -gt 32) { return $null }
    $value = $octets[0] * 16777216 + $octets[1] * 65536 + $octets[2] * 256 + $octets[3]
    $size = [uint64][math]::Pow(2, 32 - $bits)
    $start = $value - ($value % $size)
    @{ Start = $start; End = $start + $size - 1 }
}

function Test-DiagIpInRanges {
    param([string]$Ip, $Ranges)
    $r = ConvertTo-DiagIpRange $Ip
    $r -and @($Ranges | Where-Object { $_ -and $_.Start -le $r.Start -and $r.End -le $_.End }).Count -gt 0
}

function Test-DiagPrivateIp {
    param([string]$Ip)
    Test-DiagIpInRanges $Ip @((ConvertTo-DiagIpRange '10.0.0.0/8'), (ConvertTo-DiagIpRange '172.16.0.0/12'), (ConvertTo-DiagIpRange '192.168.0.0/16'), (ConvertTo-DiagIpRange '100.64.0.0/10'))
}

function Get-DiagNsgValues {
    param($Properties, [string]$Single, [string]$Plural)
    @(@($Properties[$Single]) + @($Properties[$Plural]) | Where-Object { ![string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { ([string]$_).Trim() })
}

# Yes / No / Unknown: does a rule's destination cover the target (an IP, or a public service named by tags)?
function Get-DiagNsgDestinationMatch {
    param($Properties, $Target, $VnetRanges)
    if (@($Properties.destinationApplicationSecurityGroups | Where-Object { $_ }).Count) { return $(if ($Target.Ip) { 'Unknown' } else { 'No' }) }
    $prefixes = @(Get-DiagNsgValues $Properties 'destinationAddressPrefix' 'destinationAddressPrefixes')
    if (!$prefixes.Count) { return 'Unknown' }
    $unknown = $false
    foreach ($prefix in $prefixes) {
        if ($prefix -in @('*', 'Any', '0.0.0.0/0')) { return 'Yes' }
        $range = ConvertTo-DiagIpRange $prefix
        if ($Target.Ip) {
            if ($range) { if (Test-DiagIpInRanges $Target.Ip @($range)) { return 'Yes' }; continue }
            if ($prefix -eq 'VirtualNetwork') { if (Test-DiagIpInRanges $Target.Ip $VnetRanges) { return 'Yes' }; $unknown = $true; continue }
            # Other service tags (Internet, AzureMonitor, Storage, ...) hold public ranges only.
            if (Test-DiagPrivateIp $Target.Ip) { continue }
            $unknown = $true
        }
        else {
            if ($range -or $prefix -in @('VirtualNetwork', 'AzureLoadBalancer')) { continue }
            if ($prefix -eq 'Internet' -or @($Target.Tags | Where-Object { $prefix -ieq $_ -or $prefix -like "$_.*" }).Count) { return 'Yes' }
            $unknown = $true
        }
    }
    $(if ($unknown) { 'Unknown' } else { 'No' })
}

function Get-DiagNsgSourceMatch {
    param($Properties, [string[]]$Sources, [bool]$SourcesInVnet)
    if (@($Properties.sourceApplicationSecurityGroups | Where-Object { $_ }).Count) { return 'Unknown' }
    $prefixes = @(Get-DiagNsgValues $Properties 'sourceAddressPrefix' 'sourceAddressPrefixes')
    if (!$prefixes.Count) { return 'Unknown' }
    $sourceRanges = @($Sources | ForEach-Object { ConvertTo-DiagIpRange $_ } | Where-Object { $_ })
    $unknown = $false
    foreach ($prefix in $prefixes) {
        if ($prefix -in @('*', 'Any', '0.0.0.0/0')) { return 'Yes' }
        if ($prefix -eq 'VirtualNetwork') { if ($SourcesInVnet) { return 'Yes' }; $unknown = $true; continue }
        if ($prefix -in @('AzureLoadBalancer', 'Internet')) { continue }
        $range = ConvertTo-DiagIpRange $prefix
        if (!$range -or !$sourceRanges.Count) { $unknown = $true; continue }
        $covered = @($sourceRanges | Where-Object { $range.Start -le $_.Start -and $_.End -le $range.End }).Count
        if ($covered -eq $sourceRanges.Count) { return 'Yes' }
        if (@($sourceRanges | Where-Object { $_.Start -le $range.End -and $range.Start -le $_.End }).Count) { $unknown = $true }
    }
    $(if ($unknown) { 'Unknown' } else { 'No' })
}

function Get-DiagNsgPortMatch {
    param($Properties, [int]$Port = 443)
    $ranges = @(Get-DiagNsgValues $Properties 'destinationPortRange' 'destinationPortRanges')
    if (!$ranges.Count) { return 'Unknown' }
    $unknown = $false
    foreach ($range in $ranges) {
        if ($range -in @('*', 'Any', '0-65535')) { return 'Yes' }
        if ($range -match '^(\d+)(?:-(\d+))?$') {
            $low = [int]$Matches[1]; $high = if ($Matches[2]) { [int]$Matches[2] } else { $low }
            if ($low -le $Port -and $Port -le $high) { return 'Yes' }
        }
        else { $unknown = $true }
    }
    $(if ($unknown) { 'Unknown' } else { 'No' })
}

# First matching rule for TCP 443 in priority order: Allow, Deny or Unknown (a rule that may match uses something we can't evaluate).
function Get-DiagNsgDecision {
    param($NsgData, [string]$Direction, $Target, [string[]]$Sources, $VnetRanges, [bool]$SourcesInVnet)
    $defaults = @($NsgData.properties.defaultSecurityRules | Where-Object { $_ })
    if (!$defaults.Count) { $defaults = $script:DiagNsgBuiltInRules }
    $rules = @(@($NsgData.properties.securityRules | Where-Object { $_ }) + $defaults |
        Where-Object { $_.properties.direction -eq $Direction } | Sort-Object { [int]$_.properties.priority })
    foreach ($rule in $rules) {
        $p = $rule.properties
        $protocol = [string]$p.protocol
        $proto = if ($protocol -in @('*', 'Tcp', 'Any')) { 'Yes' } elseif ($protocol -in @('Udp', 'Icmp', 'Esp', 'Ah')) { 'No' } else { 'Unknown' }
        $parts = @($proto, (Get-DiagNsgPortMatch $p), (Get-DiagNsgDestinationMatch $p $Target $VnetRanges), (Get-DiagNsgSourceMatch $p $Sources $SourcesInVnet))
        if ('No' -in $parts) { continue }
        $decision = if ('Unknown' -in $parts -or $p.access -notin @('Allow', 'Deny')) { 'Unknown' } else { [string]$p.access }
        return @{ Decision = $decision; Rule = $rule.name; Priority = $p.priority }
    }
    @{ Decision = 'Unknown'; Rule = $null; Priority = $null }
}

function Get-DiagVnetRanges {
    param($Evidence, [string[]]$VnetIds)
    $ranges = foreach ($id in @($VnetIds | Where-Object { $_ })) {
        $vnet = Get-Ev $Evidence $id
        if ($vnet.Ok) { foreach ($prefix in @($vnet.Data.properties.addressSpace.addressPrefixes)) { ConvertTo-DiagIpRange $prefix } }
    }
    @($ranges | Where-Object { $_ })
}

# VNets that count as "VirtualNetwork" for the agent subnet: its own VNet plus Connected peerings.
function Get-DiagAgentVnetSet {
    param($Evidence, [string]$AgentVnet)
    $ids = @($AgentVnet)
    $peerings = Get-Ev $Evidence "$AgentVnet/virtualNetworkPeerings"
    if ($peerings.Ok) { $ids += @($peerings.Data | Where-Object { $_ -and $_.properties.peeringState -eq 'Connected' } | ForEach-Object { $_.properties.remoteVirtualNetwork.id }) }
    @($ids | Where-Object { $_ })
}

# What the agent reaches on one path: private endpoint IPs when the path is private, otherwise the service tag.
function Get-DiagNsgPathTargets {
    param($Evidence, [string]$Path)
    $targets = [Collections.Generic.List[object]]::new()
    $private = $false
    foreach ($dep in @(Get-DiagPeDependencies $Evidence | Where-Object { $_.path -eq $Path })) {
        $peIds = @(Get-DiagPeIds $dep (Get-DiagPeConnections $Evidence $dep))
        if (!$peIds.Count) { continue }
        $private = $true
        foreach ($peId in $peIds) {
            $pe = Get-Ev $Evidence $peId
            $addresses = Get-DiagPeAddresses $Evidence $peId
            foreach ($h in ($addresses.Keys | Sort-Object)) {
                foreach ($ip in @($addresses[$h])) {
                    if ($ip -and !@($targets | Where-Object { $_.Ip -eq $ip }).Count) {
                        $targets.Add(@{ Ip = $ip; Label = "$ip ($h)"; Pe = $peId; Subnet = $(if ($pe.Ok) { $pe.Data.properties.subnet.id } else { $null }) })
                    }
                }
            }
        }
    }
    if (!$private -and $script:DiagNsgPathTags[$Path]) {
        $tags = $script:DiagNsgPathTags[$Path]
        $targets.Add(@{ Ip = $null; Tags = $tags; Label = "the $($tags -join '/') service tag" })
    }
    @{ Private = $private; Targets = $targets.ToArray() }
}

function Get-DiagSubnetPrefixes {
    param($SubnetData)
    @(@($SubnetData.properties.addressPrefix) + @($SubnetData.properties.addressPrefixes) | Where-Object { $_ } | Select-Object -Unique)
}

function Format-DiagNsgRule {
    param($Decision)
    if ($Decision.Rule) { "rule '$($Decision.Rule)' (priority $($Decision.Priority))" } else { 'no rule' }
}

# Evaluates a list of targets and returns one result.
function New-DiagNsgCoverageResult {
    param([hashtable]$Common, $NsgRead, [string]$Direction, $Targets, [string[]]$Sources, $VnetRanges, [bool]$SourcesInVnet, [string]$What, [string]$Action, [string]$Refs)
    $nsgName = Get-ArmName $NsgRead.Path
    $evals = @($Targets | ForEach-Object { @{ Target = $_; D = (Get-DiagNsgDecision $NsgRead.Data $Direction $_ $Sources $VnetRanges $SourcesInVnet) } })
    $details = @{ nsg = $NsgRead.Path; direction = $Direction; sources = $Sources
        decisions = @($evals | ForEach-Object { @{ target = $_.Target.Label; decision = $_.D.Decision; rule = $_.D.Rule; priority = $_.D.Priority } }) }
    $denied = @($evals | Where-Object { $_.D.Decision -eq 'Deny' })
    $unknown = @($evals | Where-Object { $_.D.Decision -eq 'Unknown' })
    $evidence = @(Get-EvRef $NsgRead) + @($Refs | Where-Object { $_ })
    if ($denied.Count) {
        $list = ($denied | ForEach-Object { "$($_.Target.Label) by $(Format-DiagNsgRule $_.D)" }) -join '; '
        return New-DiagResult @Common -Status Problem -Severity High -Seen "NSG '$nsgName' blocks $What to $list." `
            -Likely 'Consistent with evaluation traffic timing out at the network security group.' -Owner NetworkTeam `
            -Action "$Action Targets: $(($denied | ForEach-Object { $_.Target.Label }) -join ', ')." -Evidence $evidence -Details $details
    }
    if ($unknown.Count) {
        $list = ($unknown | ForEach-Object { "$($_.Target.Label) ($(Format-DiagNsgRule $_.D))" }) -join '; '
        return New-DiagResult @Common -Status CouldNotCheck -Gap KnownLimit `
            -Seen "NSG '$nsgName' has rules the diagnostic can't evaluate (application security groups or service tags) for $What to $list." `
            -Needs "Confirm in NSG '$nsgName' that these rules allow TCP 443 for this traffic." -Evidence $evidence -Details $details
    }
    if (!$evals.Count) {
        return New-DiagResult @Common -Status OK -Seen "No private endpoint addresses were found to check against NSG '$nsgName'." -Evidence $evidence -Details $details
    }
    $seen = "NSG '$nsgName' allows $What to $(($evals | ForEach-Object { $_.Target.Label }) -join ', ')."
    $tags = @(Get-DiagNsgSkippedTags $NsgRead.Data $Direction)
    if ($tags.Count -and @($evals | Where-Object { $_.Target.Ip }).Count) {
        $seen += " Rules using the $($tags -join ', ') service tag(s) were treated as not covering private addresses; service tag ranges aren't checked offline."
        $details.skippedServiceTags = $tags
    }
    New-DiagResult @Common -Status OK -Seen $seen -Evidence $evidence -Details $details
}

# Service tags (other than VirtualNetwork) in custom rule destinations; they are assumed not to cover private endpoint IPs.
function Get-DiagNsgSkippedTags {
    param($NsgData, [string]$Direction)
    @($NsgData.properties.securityRules | Where-Object { $_.properties.direction -eq $Direction } |
        ForEach-Object { Get-DiagNsgValues $_.properties 'destinationAddressPrefix' 'destinationAddressPrefixes' } |
        Where-Object { $_ -and $_ -notin @('*', 'Any', 'VirtualNetwork') -and !(ConvertTo-DiagIpRange $_) } | Sort-Object -Unique)
}

function Test-DiagNsg {
    param($Evidence)
    $out = [Collections.Generic.List[object]]::new()
    $agentSubnetId = $Evidence.discovery.agentSubnet
    if (!$agentSubnetId) { return , @() }
    $agentSubnet = Get-Ev $Evidence $agentSubnetId
    if (!$agentSubnet.Ok) { return , @() }   # subnet.resource reports it
    $agentVnet = Get-ArmParent $agentSubnetId
    $sources = @(Get-DiagSubnetPrefixes $agentSubnet.Data)
    $vnetSet = @(Get-DiagAgentVnetSet $Evidence $agentVnet)
    $agentNsgId = $agentSubnet.Data.properties.networkSecurityGroup.id
    $agentNsg = if ($agentNsgId) { Get-Ev $Evidence $agentNsgId } else { $null }
    $sourceText = $sources -join ', '

    foreach ($path in Get-DiagPathsUsed $Evidence) {
        $plan = Get-DiagNsgPathTargets $Evidence $path

        # nsg.agentOutbound
        $common = @{ Id = 'nsg.agentOutbound'; Area = 'Nsg'; Title = 'Agent subnet NSG outbound rules'; Layer = 'Nsg'; Path = $path }
        if (!$agentNsgId) {
            $out.Add((New-DiagResult @common -Resource $agentSubnetId -Status OK -Seen "The agent subnet '$(Get-ArmName $agentSubnetId)' has no NSG." -Evidence @(Get-EvRef $agentSubnet)))
        }
        else {
            $common.Resource = $agentNsgId
            $gap = New-ReadGap $agentNsg @common -What "NSG '$(Get-ArmName $agentNsgId)'"
            if ($gap) { $out.Add($gap) }
            elseif ($agentNsg.NotFound) {
                $out.Add((New-DiagResult @common -Status CouldNotCheck -Gap KnownLimit -Seen "NSG '$(Get-ArmName $agentNsgId)' on the agent subnet was not found." `
                    -Needs 'Check the NSG attached to the agent subnet in the portal.' -Evidence @(Get-EvRef $agentNsg)))
            }
            else {
                $out.Add((New-DiagNsgCoverageResult -Common $common -NsgRead $agentNsg -Direction Outbound -Targets $plan.Targets -Sources $sources `
                    -VnetRanges (Get-DiagVnetRanges $Evidence $vnetSet) -SourcesInVnet $true -What "outbound TCP 443 from the agent subnet ($sourceText)" `
                    -Action "Add an outbound rule to NSG '$(Get-ArmName $agentNsgId)' allowing TCP 443 from $sourceText, with a higher priority (lower number) than the blocking rule." `
                    -Refs (Get-EvRef $agentSubnet)))
            }
        }

        # nsg.peInbound — one result per private endpoint subnet on this path.
        $bySubnet = [ordered]@{}
        foreach ($t in @($plan.Targets | Where-Object { $_.Ip -and $_.Subnet })) {
            $k = $t.Subnet.ToLowerInvariant()
            if (!$bySubnet.Contains($k)) { $bySubnet[$k] = @{ Id = $t.Subnet; Targets = [Collections.Generic.List[object]]::new() } }
            $bySubnet[$k].Targets.Add($t)
        }
        foreach ($entry in $bySubnet.Values) {
            $subnetName = Get-ArmName $entry.Id
            $common = @{ Id = 'nsg.peInbound'; Area = 'Nsg'; Title = 'Private endpoint subnet NSG inbound rules'; Layer = 'Nsg'; Path = $path; Resource = $entry.Id }
            $subnet = Get-Ev $Evidence $entry.Id
            $gap = New-ReadGap $subnet @common -What "private endpoint subnet '$subnetName'"
            if ($gap) { $out.Add($gap); continue }
            if ($subnet.NotFound) { continue }
            $policies = $subnet.Data.properties.privateEndpointNetworkPolicies
            $nsgId = $subnet.Data.properties.networkSecurityGroup.id
            if (!$nsgId) {
                $out.Add((New-DiagResult @common -Status OK -Seen "Private endpoint subnet '$subnetName' has no NSG." -Evidence @(Get-EvRef $subnet)))
                continue
            }
            if ($policies -notin @('Enabled', 'NetworkSecurityGroupEnabled')) {
                $out.Add((New-DiagResult @common -Status OK -Seen "NSG '$(Get-ArmName $nsgId)' doesn't apply to private endpoints in subnet '$subnetName' (network policies are $(if ($policies) { $policies } else { 'off' }))." `
                    -Evidence @(Get-EvRef $subnet) -Details @{ privateEndpointNetworkPolicies = $policies }))
                continue
            }
            $nsg = Get-Ev $Evidence $nsgId
            $gap = New-ReadGap $nsg @common -What "NSG '$(Get-ArmName $nsgId)'"
            if ($gap) { $out.Add($gap); continue }
            if ($nsg.NotFound) { continue }
            $peVnet = Get-ArmParent $entry.Id
            $inVnet = @($vnetSet | Where-Object { Test-SameArmId $_ $peVnet }).Count -gt 0
            $out.Add((New-DiagNsgCoverageResult -Common $common -NsgRead $nsg -Direction Inbound -Targets $entry.Targets.ToArray() -Sources $sources `
                -VnetRanges (Get-DiagVnetRanges $Evidence @($vnetSet + $peVnet | Select-Object -Unique)) -SourcesInVnet $inVnet `
                -What "inbound TCP 443 from the agent subnet ($sourceText)" `
                -Action "Add an inbound rule to NSG '$(Get-ArmName $nsgId)' allowing TCP 443 from $sourceText to the private endpoints, with a higher priority (lower number) than the blocking rule." `
                -Refs (Get-EvRef $subnet)))
        }
    }

    $runner = Test-DiagNsgRunner $Evidence $agentNsgId $agentNsg
    if ($runner) { $out.Add($runner) }
    , $out.ToArray()
}

function Get-DiagNsgOutboundSignature {
    param($NsgData)
    $rules = @($NsgData.properties.securityRules | Where-Object { $_ -and $_.properties.direction -eq 'Outbound' } | Sort-Object { [int]$_.properties.priority } | ForEach-Object {
            $p = $_.properties
            ($p.priority, $p.access, $p.protocol, ((Get-DiagNsgValues $p 'sourceAddressPrefix' 'sourceAddressPrefixes') -join ','),
                ((Get-DiagNsgValues $p 'destinationAddressPrefix' 'destinationAddressPrefixes') -join ','),
                ((Get-DiagNsgValues $p 'destinationPortRange' 'destinationPortRanges') -join ',')) -join '|' })
    $rules -join ';'
}

# nsg.runner — probes from this machine only reflect agent traffic if the runner's NSGs match the agent subnet's.
function Test-DiagNsgRunner {
    param($Evidence, [string]$AgentNsgId, $AgentNsg)
    $r = $Evidence.discovery.runner
    if (!$r -or !$r.subnet) { return $null }   # runner.location reports an unknown runner
    $common = @{ Id = 'nsg.runner'; Area = 'Nsg'; Title = "This machine's NSG compared with the agent subnet"; Layer = 'Nsg'; Resource = $r.subnet }
    $subnet = Get-Ev $Evidence $r.subnet
    $gap = New-ReadGap $subnet @common -What "this machine's subnet '$(Get-ArmName $r.subnet)'"
    # A runner read gap never blocks a path; it only qualifies probe results.
    if ($gap) { $gap.gap = 'KnownLimit'; $gap.scope = 'ThisMachine'; return $gap }
    $common.Scope = 'ThisMachine'
    if (!$subnet.Ok) { return $null }
    $runnerNsgs = @($subnet.Data.properties.networkSecurityGroup.id)
    $refs = @(Get-EvRef $subnet)
    if ($r.nic) {
        $nic = Get-Ev $Evidence $r.nic
        if ($nic.Ok) { $runnerNsgs += $nic.Data.properties.networkSecurityGroup.id; $refs += Get-EvRef $nic }
    }
    $runnerNsgs = @($runnerNsgs | Where-Object { $_ })
    $agentName = if ($AgentNsgId) { "NSG '$(Get-ArmName $AgentNsgId)'" } else { 'no NSG' }
    $runnerName = if ($runnerNsgs.Count) { ($runnerNsgs | ForEach-Object { "NSG '$(Get-ArmName $_)'" }) -join ' and ' } else { 'no NSG' }
    $details = @{ agentNsg = $AgentNsgId; runnerNsgs = $runnerNsgs }
    $same = (!$AgentNsgId -and !$runnerNsgs.Count) -or ($runnerNsgs.Count -eq 1 -and (Test-SameArmId $runnerNsgs[0] $AgentNsgId))
    if (!$same -and $runnerNsgs.Count -eq 1 -and $AgentNsg -and $AgentNsg.Ok) {
        $other = Get-Ev $Evidence $runnerNsgs[0]
        if ($other.Ok -and (Get-DiagNsgOutboundSignature $other.Data) -eq (Get-DiagNsgOutboundSignature $AgentNsg.Data)) {
            $refs += Get-EvRef $other
            return New-DiagResult @common -Status OK -Seen "This machine uses $runnerName, which has the same outbound rules as the agent subnet's $agentName." -Evidence $refs -Details $details
        }
    }
    if ($same) {
        return New-DiagResult @common -Status OK -Seen "This machine and the agent subnet both use $agentName." -Evidence $refs -Details $details
    }
    New-DiagResult @common -Status CouldNotCheck -Gap KnownLimit -Seen "This machine uses $runnerName; the agent subnet uses $agentName. Probe results from this machine may not match what the agent sees." `
        -Needs 'Run the diagnostic from a VM whose subnet uses the same NSG as the agent subnet to test the agent path directly.' -Evidence $refs -Details $details
}
