# Agent subnet checks: the subnet the account injects evaluation traffic into.

$script:AgentSubnetMinPrefix = 27        # smallest subnet the agent environment accepts
$script:AgentSubnetRecommendedPrefix = 24

function Get-SubnetPrefixLength {
    param($Properties)
    $prefixes = @(@($Properties.addressPrefix) + @($Properties.addressPrefixes) | Where-Object { $_ -match '/\d+$' })
    if (!$prefixes.Count) { return $null }
    ($prefixes | ForEach-Object { [int]($_ -split '/')[1] } | Measure-Object -Minimum).Minimum
}

function Test-DiagSubnet {
    param($Evidence)
    $id = $Evidence.discovery.agentSubnet
    if (!$id) { return , @() }   # project.injection already reports a missing subnet
    $out = [Collections.Generic.List[object]]::new()
    $name = Get-ArmName $id
    $ev = Get-Ev $Evidence $id

    $title = 'Agent subnet'
    $gap = New-ReadGap $ev -Id subnet.resource -Area Subnet -Title $title -Layer Config -Resource $id -What "agent subnet '$name'"
    if ($gap) { $out.Add($gap); return , $out.ToArray() }
    if ($ev.NotFound) {
        $out.Add((New-DiagResult -Id subnet.resource -Area Subnet -Title $title -Status Problem -Severity High -Layer Config -Resource $id `
            -Seen "Agent subnet '$name' doesn't exist." -Owner NetworkTeam `
            -Action 'Recreate the subnet or redeploy the account with an existing subnet.' -Evidence (Get-EvRef $ev)))
        return , $out.ToArray()
    }
    $p = $ev.Data.properties
    $out.Add((New-DiagResult -Id subnet.resource -Area Subnet -Title $title -Status OK -Layer Config -Resource $id `
        -Seen "Agent subnet '$name' ($(@(@($p.addressPrefix) + @($p.addressPrefixes) | Where-Object { $_ }) -join ', '))." -Evidence (Get-EvRef $ev)))

    # subnet.delegation
    $title = 'Agent subnet delegation'
    $delegations = @($p.delegations | ForEach-Object { $_.properties.serviceName } | Where-Object { $_ })
    if ('Microsoft.App/environments' -in $delegations) {
        $out.Add((New-DiagResult -Id subnet.delegation -Area Subnet -Title $title -Status OK -Layer Config -Resource $id -Seen 'Delegated to Microsoft.App/environments.' -Evidence (Get-EvRef $ev)))
    }
    else {
        $out.Add((New-DiagResult -Id subnet.delegation -Area Subnet -Title $title -Status Problem -Severity High -Layer Config -Resource $id `
            -Seen $(if ($delegations.Count) { "Delegated to $($delegations -join ', ') instead." } else { 'The subnet is not delegated.' }) -Owner NetworkTeam `
            -Action 'Delegate the agent subnet to Microsoft.App/environments (the subnet must be empty of other resources).' -Evidence (Get-EvRef $ev) `
            -Details @{ delegations = $delegations }))
    }

    # subnet.size
    $title = 'Agent subnet size'
    $length = Get-SubnetPrefixLength $p
    if ($null -eq $length) {
        $out.Add((New-DiagResult -Id subnet.size -Area Subnet -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Resource $id `
            -Seen 'The subnet has no address prefix in its metadata.' -Needs 'Check the subnet address range in the portal.' -Evidence (Get-EvRef $ev)))
    }
    elseif ($length -gt $script:AgentSubnetMinPrefix) {
        $out.Add((New-DiagResult -Id subnet.size -Area Subnet -Title $title -Status Problem -Severity High -Layer Config -Resource $id `
            -Seen "The subnet is /$length; the agent environment needs at least /$script:AgentSubnetMinPrefix." -Owner NetworkTeam `
            -Action "Use a subnet of /$script:AgentSubnetRecommendedPrefix (at least /$script:AgentSubnetMinPrefix)." -Evidence (Get-EvRef $ev)))
    }
    elseif ($length -gt $script:AgentSubnetRecommendedPrefix) {
        $out.Add((New-DiagResult -Id subnet.size -Area Subnet -Title $title -Status Problem -Severity Low -Layer Config -Resource $id `
            -Seen "The subnet is /$length; /$script:AgentSubnetRecommendedPrefix is recommended so the environment can scale." -Owner NetworkTeam `
            -Action "Consider a /$script:AgentSubnetRecommendedPrefix subnet for the agent environment." -Evidence (Get-EvRef $ev)))
    }
    else {
        $out.Add((New-DiagResult -Id subnet.size -Area Subnet -Title $title -Status OK -Layer Config -Resource $id -Seen "The subnet is /$length." -Evidence (Get-EvRef $ev)))
    }

    # subnet.attachments — something other than the agent environment is linked to the subnet.
    $title = 'Other services on the agent subnet'
    $others = @($p.serviceAssociationLinks | ForEach-Object { $_.properties.linkedResourceType } | Where-Object { $_ -and $_ -ne 'Microsoft.App/environments' })
    if ($others.Count) {
        $out.Add((New-DiagResult -Id subnet.attachments -Area Subnet -Title $title -Status Problem -Severity Medium -Layer Config -Resource $id `
            -Seen "The subnet is also linked to $($others -join ', ')." -Owner NetworkTeam `
            -Action 'Give the agent environment its own subnet.' -Evidence (Get-EvRef $ev) -Details @{ linkedResourceTypes = $others }))
    }
    else {
        $out.Add((New-DiagResult -Id subnet.attachments -Area Subnet -Title $title -Status OK -Layer Config -Resource $id -Seen 'No other services are linked to the subnet.' -Evidence (Get-EvRef $ev)))
    }

    # subnet.dnsServers — Azure-provided DNS vs custom resolvers (DNS checks use this).
    $vnetId = Get-ArmParent $id
    $vnet = Get-Ev $Evidence $vnetId
    $title = 'Virtual network DNS servers'
    $gap = New-ReadGap $vnet -Id subnet.dnsServers -Area Subnet -Title $title -Layer Name -Resource $vnetId -What "virtual network '$(Get-ArmName $vnetId)'"
    if ($gap) { $out.Add($gap) }
    elseif ($vnet.Ok) {
        $servers = @($vnet.Data.properties.dhcpOptions.dnsServers | Where-Object { $_ })
        $out.Add((New-DiagResult -Id subnet.dnsServers -Area Subnet -Title $title -Status OK -Layer Name -Resource $vnetId `
            -Seen $(if ($servers.Count) { "Custom DNS servers: $($servers -join ', ')." } else { 'Azure-provided DNS.' }) -Evidence (Get-EvRef $vnet) `
            -Details @{ dnsServers = $servers }))
    }

    , $out.ToArray()
}
