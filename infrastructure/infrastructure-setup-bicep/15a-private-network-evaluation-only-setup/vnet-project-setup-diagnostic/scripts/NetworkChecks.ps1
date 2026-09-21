function Test-SubnetConfiguration {
    param($Context, $Account, [string]$AccountId)
    $injections = @($Account.Data.properties.networkInjections | Where-Object { $_.scenario -eq 'agent' })
    $id = if ($injections.Count -eq 1) { $injections[0].subnetArmId } else { '' }
    $status = if ($id) { 'Passed' } else { 'Unknown' }
    Add-Check $Context 'network.injection' 'Network' $AccountId $status 'Account-owned agent network injection references a subnet' @{
        agentInjectionCount = $injections.Count; subnetId = $id
    } -Limitations @('Project-level networkInjection is not required. Unknown topology is not assumed to be template15a.')
    if (!$id) { return @{ VnetId = ''; CustomDns = $null } }
    try { $null = Assert-ArmId $id } catch { return @{ VnetId = ''; CustomDns = $null } }
    $subnet = Test-Provisioning $Context $id 'network.subnet'
    if ($subnet.Code -ne 200) { return @{ VnetId = ''; CustomDns = $null } }
    $delegations = @($subnet.Data.properties.delegations | ForEach-Object { $_.properties.serviceName })
    $status = if ('Microsoft.App/environments' -in $delegations) { 'Passed' }
        elseif (!$subnet.Data.properties -or !$subnet.Data.properties.ContainsKey('delegations') -or $null -eq $subnet.Data.properties.delegations) { 'Unknown' } else { 'Failed' }
    Add-Check $Context 'network.delegation' 'Network' $id $status 'Agent subnet delegated to Microsoft.App/environments' @{
        delegations = $delegations
        serviceAssociationLinks = @($subnet.Data.properties.serviceAssociationLinks | ForEach-Object { @{ id = $_.id; linkedResourceType = $_.properties.linkedResourceType; allowDelete = $_.properties.allowDelete } })
    } -Limitations @('Existing platform SALs are expected; their presence is not a defect and they must not be deleted.') `
        -Remediation 'Have the network owner compare the recorded agent subnet delegation with Microsoft.App/environments. Do not delete SALs, capability hosts, or modify delegation during diagnosis.'
    $vnetId = $id -replace '/subnets/[^/]+$', ''
    $vnet = Read-Arm $Context $vnetId
    $dnsReadable = $vnet.Code -eq 200 -and $vnet.Data.properties -is [Collections.IDictionary]
    $servers = @($vnet.Data.properties.dhcpOptions.dnsServers | Where-Object { ![string]::IsNullOrWhiteSpace($_) })
    Add-Check $Context 'network.resolvers' 'Network' $vnetId $(if ($dnsReadable) {'Passed'} elseif ($vnet.Code -eq 200) {'Unknown'} else {Get-ReadStatus $vnet}) 'Inspect VNet DNS configuration' @{
        readStatus = $vnet.Code; dnsServers = $servers
        resolverType = $(if (!$dnsReadable) {'Unknown'} elseif ($servers.Count) {'Custom'} else {'AzureProvided'})
    } -Limitations @('Empty dnsServers uses Azure-provided DNS. Custom/central forwarding rules and NVA behavior are not simulated.')
    Test-NetworkAttachments $Context $subnet.Data.properties
    return @{ VnetId = $vnetId; CustomDns = $(if ($dnsReadable) { $servers.Count -gt 0 } else { $null }) }
}

function Test-NetworkAttachments {
    param($Context, $SubnetProperties)
    foreach ($attachment in @('networkSecurityGroup', 'routeTable')) {
        $attachmentId = $SubnetProperties[$attachment].id
        if (!$attachmentId) { continue }
        $read = Read-Arm $Context $attachmentId
        $rules = if ($attachment -eq 'routeTable') {
            @($read.Data.properties.routes | ForEach-Object { @{ name = $_.name; addressPrefix = $_.properties.addressPrefix; nextHopType = $_.properties.nextHopType; nextHopIpAddress = $_.properties.nextHopIpAddress } })
        } else {
            @($read.Data.properties.securityRules | ForEach-Object { @{
                name = $_.name; priority = $_.properties.priority; direction = $_.properties.direction; access = $_.properties.access
                protocol = $_.properties.protocol; sourceAddressPrefix = $_.properties.sourceAddressPrefix
                destinationAddressPrefix = $_.properties.destinationAddressPrefix; destinationPortRange = $_.properties.destinationPortRange
            } })
        }
        Add-Check $Context 'network.attachments' 'Network' $attachmentId (Get-ReadStatus $read) 'Read attached NSG/UDR metadata' @{
            kind = $attachment; readStatus = $read.Code; rules = $rules
        } -Classification Inventory -Limitations @('Observation only. Rule combinations, effective routes, service tags, peering, firewalls and NVA paths are not evaluated.')
    }
}

function Get-RecordExpectedIps {
    param($Record, [string]$Fqdn, $PeProperties, [string[]]$NicIps)
    $declared = @($Record.ipAddresses | Where-Object { ![string]::IsNullOrWhiteSpace($_) })
    if ($declared.Count) { return $declared }
    $canonical = Get-KnownPrivateLinkMapping $Fqdn
    $hostName = if ($canonical) { $canonical.canonicalHost } else { $Fqdn }
    $matchedDns = @($PeProperties.customDnsConfigs | Where-Object {
        $mapping = Get-KnownPrivateLinkMapping $_.fqdn
        $candidate = if ($mapping) { $mapping.canonicalHost } else { $_.fqdn }
        $candidate -and $candidate -eq $hostName
    })
    $mapped = @($matchedDns | ForEach-Object { $_.ipAddresses } | Where-Object { $_ -and $_ -in $NicIps } | Sort-Object -Unique)
    if ($mapped.Count) { return $mapped }
    # A single-address PE can map a declared PE record to that sole address.
    # Never spread a multi-address NIC across all of its hostnames.
    $uniqueIps = @($NicIps | Where-Object { $_ } | Sort-Object -Unique)
    if ($Fqdn -and $uniqueIps.Count -eq 1) { return $uniqueIps }
    return @()
}

function Get-DnsRecordAssessment {
    param([int]$ReadCode, [string[]]$Expected, [string[]]$Addresses)
    $Expected = @($Expected | Where-Object { $_ })
    $Addresses = @($Addresses | Where-Object { $_ })
    if ($ReadCode -ne 200 -or !$Expected.Count) { return 'Unknown' }
    if (@($Expected | Where-Object { $_ -notin $Addresses }).Count) { return 'Failed' }
    # Additional addresses can belong to another approved PE for the same host.
    # Without complete host-to-PE evidence, do not call those addresses broken.
    if (@($Addresses | Where-Object { $_ -notin $Expected }).Count) { return 'Unknown' }
    return 'Passed'
}

function Test-PrivateEndpointConfiguration {
    param($Context, [string]$ResourceId, [string]$Group, $Topology)
    $connections = Read-Arm $Context "$ResourceId/privateEndpointConnections" -Collection
    if ($connections.Code -ne 200) {
        Add-Check $Context 'pe.discovery' 'PrivateEndpoint' $ResourceId 'Unknown' "Read approved $Group private endpoint connections" @{
            readStatus = $connections.Code; reason = $connections.Reason
        }
        return
    }
    if (@($connections.Data).Count -eq 0) {
        Add-Check $Context 'pe.approval' 'PrivateEndpoint' $ResourceId 'Failed' "At least one approved $Group private endpoint" @{ count = 0 }
        return
    }
    $approvedGroup = $false
    $unresolved = $false
    foreach ($connection in $connections.Data) {
        $peId = $connection.properties.privateEndpoint.id
        $approval = $connection.properties.privateLinkServiceConnectionState.status
        if (!$peId) { $unresolved = $true; continue }
        $pe = Read-Arm $Context $peId
        if ($pe.Code -ne 200) {
            $unresolved = $true
            Add-Check $Context 'pe.resource' 'PrivateEndpoint' $peId (Get-ReadStatus $pe) 'Read referenced private endpoint' @{ readStatus = $pe.Code }
            continue
        }
        $links = @(@($pe.Data.properties.privateLinkServiceConnections) + @($pe.Data.properties.manualPrivateLinkServiceConnections) |
            Where-Object { $_.properties.privateLinkServiceId -eq $ResourceId -and $Group -in $_.properties.groupIds })
        if (!$links.Count) {
            if (!$pe.Data.properties.privateLinkServiceConnections -and !$pe.Data.properties.manualPrivateLinkServiceConnections) { $unresolved = $true }
            continue
        }
        if (!$approval -or @($links | Where-Object { !$_.properties.privateLinkServiceConnectionState.status }).Count) { $unresolved = $true; continue }
        if ($approval -ne 'Approved' -or !@($links | Where-Object { $_.properties.privateLinkServiceConnectionState.status -eq 'Approved' }).Count) {
            continue
        }
        $approvedGroup = $true
        $peSubnetId = $pe.Data.properties.subnet.id
        if ($peSubnetId) {
            $peSubnet = Read-Arm $Context $peSubnetId
            $peVnetId = $peSubnetId -replace '/subnets/[^/]+$', ''
            Add-Check $Context 'pe.placement' 'PrivateEndpoint' $peId $(if ($peSubnet.Code -ne 200) { Get-ReadStatus $peSubnet } elseif ($peVnetId -eq $Topology.VnetId) {'Passed'} else {'Unknown'}) `
                'Resolve endpoint subnet and compare with account agent VNet' @{
                    subnetId = $peSubnetId; subnetReadStatus = $peSubnet.Code; endpointVnetId = $peVnetId; agentVnetId = $Topology.VnetId
                } -Limitations @('Different VNets may be valid with peering/central DNS. This check does not infer reachability across VNets.')
            if ($peSubnet.Code -eq 200) { Test-NetworkAttachments $Context $peSubnet.Data.properties }
        }
        else {
            Add-Check $Context 'pe.placement' 'PrivateEndpoint' $peId 'Unknown' 'Resolve endpoint subnet placement' @{ reason = 'SubnetReferenceUnavailable' }
        }
        $ips = [Collections.Generic.List[string]]::new()
        $nicEvidence = [Collections.Generic.List[object]]::new()
        foreach ($nicRef in @($pe.Data.properties.networkInterfaces | Where-Object { $_ })) {
            $nic = Read-Arm $Context $nicRef.id
            $nicIps = @($nic.Data.properties.ipConfigurations | ForEach-Object { $_.properties.privateIPAddress } | Where-Object { $_ })
            foreach ($ip in $nicIps) { $ips.Add($ip) }
            $nicEvidence.Add(@{ id = $nicRef.id; readStatus = $nic.Code; addresses = $nicIps })
        }
        Add-Check $Context 'pe.addresses' 'PrivateEndpoint' $peId $(if ($ips.Count) {'Passed'} else {'Unknown'}) 'Resolve PE NIC private addresses' @{
            subnetId = $pe.Data.properties.subnet.id; nics = @($nicEvidence.ToArray()); group = $Group
        }
        foreach ($dns in @($pe.Data.properties.customDnsConfigs | Where-Object { $_ })) {
            $mappedIps = @($dns.ipAddresses | Where-Object { $_ -in $ips })
            if ($dns.fqdn) { Add-Endpoint $Context "https://$($dns.fqdn)" $ResourceId $Group $mappedIps -PrivateEndpointId $peId }
        }
        # Keep private-link aliases as DNS evidence bound to discovered service hosts.
        $groups = Read-Arm $Context "$peId/privateDnsZoneGroups" -Collection
        $configs = @($groups.Data | ForEach-Object { $_.properties.privateDnsZoneConfigs } | Where-Object { $_ })
        Add-Check $Context 'dns.zoneGroups' 'DNS' $peId $(if ($groups.Code -eq 200 -and $configs.Count) {'Passed'} else {'Unknown'}) 'Inspect PE DNS zone groups or explicit custom DNS evidence' @{
            readStatus = $groups.Code; zoneIds = @($configs | ForEach-Object { $_.properties.privateDnsZoneId }); customDns = $Topology.CustomDns
        } -Limitations @('Missing zone groups can be legitimate with centralized/custom DNS; no DNS zone is invented.')
        foreach ($config in $configs) {
            $zoneId = $config.properties.privateDnsZoneId
            if (!$zoneId) { continue }
            $zone = Read-Arm $Context $zoneId
            $records = Read-Arm $Context "$zoneId/A" -Collection
            $vnetLinks = Read-Arm $Context "$zoneId/virtualNetworkLinks" -Collection
            $linked = @($vnetLinks.Data | Where-Object {
                $_.properties.virtualNetwork.id -eq $Topology.VnetId -and $_.properties.virtualNetworkLinkState -eq 'Completed'
            })
            Add-Check $Context 'dns.vnetLinks' 'DNS' $zoneId $(if ($linked.Count) {'Passed'} else {'Unknown'}) 'Inspect DNS zone links to the recorded agent VNet or centralized resolver path' @{
                zoneReadStatus = $zone.Code; linkReadStatus = $vnetLinks.Code; expectedVnetId = $Topology.VnetId
                links = @($vnetLinks.Data | Where-Object { $_ } | ForEach-Object { @{ vnetId = $_.properties.virtualNetwork.id; state = $_.properties.virtualNetworkLinkState } })
            } -Limitations @('No direct link can be valid with centralized DNS. Forwarding rules and resolver VNet membership require owner evidence.')
            $recordEvidence = [Collections.Generic.List[object]]::new()
            $recordStatuses = [Collections.Generic.List[string]]::new()
            $seenRecordNames = @{}
            foreach ($expectedRecord in @($config.properties.recordSets | Where-Object { $_ })) {
                $recordName = $expectedRecord.recordSetName
                if (!$recordName) { continue }
                $actual = @($records.Data | Where-Object { $_.name -eq $recordName -or $_.name -eq "$($zone.Data.name)/$recordName" })
                $addresses = @($actual | ForEach-Object { $_.properties.aRecords } | ForEach-Object { $_.ipv4Address } | Where-Object { $_ })
                $recordFqdn = if ($expectedRecord.fqdn) { $expectedRecord.fqdn } elseif ($zone.Data.name) { "$recordName.$($zone.Data.name)" } else { '' }
                $expected = @(Get-RecordExpectedIps $expectedRecord $recordFqdn $pe.Data.properties @($ips.ToArray()))
                $recordStatus = Get-DnsRecordAssessment $records.Code $expected $addresses
                $recordStatuses.Add($recordStatus)
                $seenRecordNames[$recordName] = $true
                $recordEvidence.Add(@{ name = $recordName; expectedIps = $expected; addresses = $addresses; status = $recordStatus })
                if ($expectedRecord.fqdn) {
                    Add-Endpoint $Context "https://$($expectedRecord.fqdn)" $ResourceId $Group @($expected | Where-Object { $_ -in $ips }) -PrivateEndpointId $peId
                }
            }
            # Some ARM versions omit generated recordSets; match PE FQDNs against
            # zone suffixes instead of guessing storage/account record names.
            foreach ($dns in @($pe.Data.properties.customDnsConfigs)) {
                $zoneName = [string]$zone.Data.name
                if (!$zoneName -or !$dns.fqdn) { continue }
                $publicSuffix = $zoneName -replace '^privatelink\.', ''
                $fqdn = [string]$dns.fqdn
                $label = ''
                foreach ($suffix in @($zoneName, $publicSuffix)) {
                    if ($fqdn.EndsWith(".$suffix", [StringComparison]::OrdinalIgnoreCase)) {
                        $label = $fqdn.Substring(0, $fqdn.Length - $suffix.Length - 1); break
                    }
                }
                if (!$label) { continue }
                if ($seenRecordNames.ContainsKey($label)) { continue }
                $actual = @($records.Data | Where-Object { $_.name -eq $label -or $_.name -eq "$zoneName/$label" })
                $addresses = @($actual | ForEach-Object { $_.properties.aRecords } | ForEach-Object { $_.ipv4Address } | Where-Object { $_ })
                $expected = @(Get-RecordExpectedIps @{} $fqdn $pe.Data.properties @($ips.ToArray()))
                $recordStatus = Get-DnsRecordAssessment $records.Code $expected $addresses
                $recordStatuses.Add($recordStatus)
                $recordEvidence.Add(@{ name = $label; expectedIps = $expected; addresses = $addresses; status = $recordStatus })
            }
            $status = if ('Failed' -in $recordStatuses) { 'Failed' } elseif (!$recordStatuses.Count -or 'Unknown' -in $recordStatuses) { 'Unknown' } else { 'Passed' }
            Add-Check $Context 'dns.records' 'DNS' $zoneId $status 'Generated PE records agree with the referenced endpoint IP mapping' @{
                recordReadStatus = $records.Code; records = @($recordEvidence.ToArray())
            } -Limitations @('Only records tied to the selected PE are checked. Additional addresses may belong to other approved PEs and remain inconclusive without full mapping evidence. Missing host-specific expected IPs are Unknown, not a mismatch. Custom DNS authority/forwarding is not certified.') `
                -Remediation 'Have the DNS owner reconcile the listed PE NIC addresses, zone-group record sets, and authoritative A records. For centralized DNS, confirm forwarding and VNet linkage separately; do not edit local hosts files.'
        }
    }
    $status = if ($approvedGroup) {'Passed'} elseif ($unresolved) {'Unknown'} else {'Failed'}
    Add-Check $Context 'pe.approval' 'PrivateEndpoint' $ResourceId $status "At least one approved private endpoint for subresource $Group" @{
        matchingApprovedEndpoint = $approvedGroup; inaccessibleEndpointEvidence = $unresolved
    } -Remediation 'Have the resource/network owner review approval and the recorded PE target/subresource. Investigate unresolved reads before treating a connection as missing; do not enable public access or mutate endpoint approval during diagnosis.'
}

function Get-HostsOverrides {
    param([string[]]$Names, [string]$Path)
    $matches = @()
    foreach ($line in Get-Content -LiteralPath $Path -ErrorAction Stop) {
        $parts = (($line -split '#', 2)[0].Trim() -split '\s+')
        if ($parts.Count -lt 2) { continue }
        foreach ($name in $parts[1..($parts.Count - 1)]) {
            if ($name.ToLowerInvariant() -in $Names) { $matches += @{ hostName = $name.ToLowerInvariant(); address = $parts[0] } }
        }
    }
    return $matches
}

function Get-EndpointMappingStatus {
    param([string[]]$Addresses, [string[]]$Expected)
    if ($Addresses.Count -and $Expected.Count -and !@($Addresses | Where-Object { $_ -notin $Expected }).Count) { return 'Passed' }
    return 'Unknown'
}

function Wait-NetworkOperation {
    param([Threading.Tasks.Task]$Task, [int]$TimeoutSeconds)
    $null = $Task.WaitAsync([TimeSpan]::FromSeconds($TimeoutSeconds)).GetAwaiter().GetResult()
}

function Test-AdvancedNetworkEvidence {
    param($Context, [string]$Name, [string[]]$Addresses, [int]$TimeoutSeconds = 5)
    $limits = @('Optional execution-host detail; not evidence of service-path or whole-VNet health.')
    $dnsOnly = @()
    $dnsOnlyStatus = 'NotAssessed'
    if (Get-Command Resolve-DnsName -ErrorAction SilentlyContinue) {
        $dnsOnlyStatus = 'Unknown'
        # Resolve-DnsName has no caller timeout; isolate it in a bounded local job.
        $job = Start-Job -ScriptBlock {
            param($hostName)
            Resolve-DnsName -Name $hostName -DnsOnly -NoHostsFile -QuickTimeout -ErrorAction Stop |
                Select-Object Name, Type, NameHost, IPAddress
        } -ArgumentList $name
        try {
            $finished = Wait-Job $job -Timeout $TimeoutSeconds
            if ($finished -and $job.State -eq 'Completed') {
                $dnsOnly = @(Receive-Job $job -ErrorAction SilentlyContinue | ForEach-Object { @{ name = $_.Name; type = [string]$_.Type; cname = $_.NameHost; address = $_.IPAddress } })
                $dnsOnlyStatus = 'Passed'
            }
        }
        finally { Stop-Job $job; Remove-Job $job -Force }
    }
    $classification = if ($dnsOnlyStatus -eq 'NotAssessed') {'Coverage'} else {'Inventory'}
    Add-Check $Context 'endpoint.dnsOnly' 'Network' $name $dnsOnlyStatus 'Optional DNS-only CNAME/address evidence' @{
        records = $dnsOnly; reason = $(if ($dnsOnlyStatus -eq 'NotAssessed') {'ResolveDnsNameNotSupported'} elseif ($dnsOnlyStatus -eq 'Unknown') {'DnsOnlyProbeFailedOrTimedOut'} else {'Collected'})
    } -Classification $classification -EvidenceKind ObservedNetwork -Limitations $limits
    $routes = @()
    $routeStatus = 'NotAssessed'
    if (Get-Command Find-NetRoute -ErrorAction SilentlyContinue) {
        $routeStatus = 'Unknown'
        if ($addresses.Count) {
        $job = Start-Job -ScriptBlock {
            param($addresses)
            foreach ($address in $addresses) {
                Find-NetRoute -RemoteIPAddress $address -ErrorAction Stop |
                    Select-Object IPAddress, InterfaceIndex, DestinationPrefix, NextHop, RouteMetric
            }
        } -ArgumentList (,$addresses)
        try {
            $finished = Wait-Job $job -Timeout $TimeoutSeconds
            if ($finished -and $job.State -eq 'Completed') {
                $routes = @(Receive-Job $job -ErrorAction SilentlyContinue | ForEach-Object {
                    @{ sourceAddress = $_.IPAddress; interfaceIndex = $_.InterfaceIndex; prefix = $_.DestinationPrefix; nextHop = $_.NextHop; metric = $_.RouteMetric }
                })
                if ($routes.Count) { $routeStatus = 'Passed' }
            }
        }
        finally { Stop-Job $job; Remove-Job $job -Force }
        }
    }
    $classification = if ($routeStatus -eq 'NotAssessed') {'Coverage'} else {'Inventory'}
    Add-Check $Context 'endpoint.route' 'Network' $name $routeStatus 'Optional selected local route/source evidence' @{
        routes = $routes; reason = $(if ($routeStatus -eq 'NotAssessed') {'FindNetRouteNotSupported'} elseif ($routeStatus -eq 'Unknown') {'RouteUnavailableOrTimedOut'} else {'Collected'})
    } -Classification $classification -EvidenceKind ObservedNetwork -Limitations $limits
}

function Test-LocalEndpoint {
    param($Context, $Endpoint, [int]$TimeoutSeconds = 5, [switch]$AdvancedNetworkDetails)
    $name = $Endpoint.hostName
    $limits = @('Evidence is from this execution host/path only. Private IPs, VPN presence and regional public responders do not prove the complete customer or service-owned private path.')
    $addresses = @()
    try {
        $task = [Net.Dns]::GetHostAddressesAsync($name)
        $addresses = @($task.WaitAsync([TimeSpan]::FromSeconds($TimeoutSeconds)).GetAwaiter().GetResult() | ForEach-Object { $_.IPAddressToString })
        $dnsStatus = if ($addresses.Count) {'Passed'} else {'Unknown'}
    }
    catch { $dnsStatus = 'Unknown' }
    Add-Check $Context 'endpoint.dns' 'Network' $name $dnsStatus 'Local OS resolution returns addresses' @{ addresses = $addresses } -EvidenceKind ObservedNetwork -Limitations $limits
    $expected = @($Endpoint.expectedIps | Where-Object { $_ })
    $mapping = Get-EndpointMappingStatus $addresses $expected
    Add-Check $Context 'endpoint.mapping' 'Network' $name $mapping 'Local addresses match this endpoint PE NIC mapping' @{
        addresses = $addresses; expectedIps = $expected; matches = @($addresses | Where-Object { $_ -in $expected })
        privateLinkAliases = @($Endpoint.privateLinkAliases)
    } -EvidenceKind ObservedNetwork -Limitations $limits
    if ($AdvancedNetworkDetails) { Test-AdvancedNetworkEvidence $Context $name $addresses $TimeoutSeconds }
    $tcp = [Net.Sockets.TcpClient]::new()
    $stream = $null
    $tcpStatus = 'Unknown'
    $tlsStatus = 'Unknown'
    $source = ''
    try {
        Wait-NetworkOperation ($tcp.ConnectAsync($name, 443)) $TimeoutSeconds
        $source = [string]$tcp.Client.LocalEndPoint
        $tcpStatus = 'Passed'
        # Default SslStream validation checks chain and the real hostname. No HTTP.
        $stream = [Net.Security.SslStream]::new($tcp.GetStream(), $false)
        Wait-NetworkOperation ($stream.AuthenticateAsClientAsync($name)) $TimeoutSeconds
        $tlsStatus = 'Passed'
    }
    catch {
        # Failures remain local-path uncertainty, not proof of an Azure defect.
    }
    finally { if ($stream) { $stream.Dispose() }; $tcp.Dispose() }
    Add-Check $Context 'endpoint.tcp443' 'Network' $name $tcpStatus 'Local TCP 443 connection' @{ sourceEndpoint = $source; connected = ($tcpStatus -eq 'Passed') } -EvidenceKind ObservedNetwork -Limitations $limits
    Add-Check $Context 'endpoint.tls' 'Network' $name $tlsStatus 'TLS handshake with normal hostname/certificate validation' @{ validated = ($tlsStatus -eq 'Passed'); serverName = $name } -EvidenceKind ObservedNetwork -Limitations $limits
}

function Test-LocalNetwork {
    param($Context, [switch]$AdvancedNetworkDetails)
    if ($Context.Offline) { throw 'Network mode is disabled for offline fixtures.' }
    $names = @($Context.Endpoints.Keys)
    $unbound = @($Context.EndpointAliases.Values | Where-Object {
        !$Context.Endpoints.ContainsKey($_.canonicalHost) -or $Context.Endpoints[$_.canonicalHost].resource -ine $_.resource
    })
    if ($unbound.Count) {
        Add-Check $Context 'endpoint.aliasMapping' 'Network' '' 'Unknown' 'Bind PE DNS aliases to independently discovered canonical service hosts' @{
            unboundAliases = $unbound
        } -Limitations @('No TLS probe uses a private-link alias. A canonical service hostname is not invented from DNS-only evidence.')
    }
    if (!$names.Count) {
        Add-Check $Context 'endpoint.discovery' 'Network' '' 'Unknown' 'Discover actual endpoint FQDNs before local probes' @{ endpointCount = 0 } -EvidenceKind ObservedNetwork
        return
    }
    $hostsPath = if ($IsWindows) { Join-Path $env:SystemRoot 'System32\drivers\etc\hosts' } else { '/etc/hosts' }
    try {
        $overrides = @(Get-HostsOverrides @($names + @($Context.EndpointAliases.Values | ForEach-Object { $_.alias })) $hostsPath)
        Add-Check $Context 'endpoint.hostsOverride' 'Network' '' $(if ($overrides.Count) {'Warning'} else {'Observed'}) 'Identify target-only local hosts overrides' @{ overrides = $overrides } -Classification $(if ($overrides.Count) {'Finding'} else {'Inventory'}) -Required $false -EvidenceKind ObservedNetwork `
            -Limitations @('A hosts override is local evidence, not shared DNS validation.')
    }
    catch { Add-Check $Context 'endpoint.hostsOverride' 'Network' '' 'Unknown' 'Read target-only hosts entries' @{ reason = 'HostsFileUnreadable' } -Required $false -EvidenceKind ObservedNetwork }
    Add-LocalHostContext $Context
    if (!$AdvancedNetworkDetails) {
        Add-Check $Context 'endpoint.advancedDetails' 'Network' '' 'NotAssessed' 'Optional DNS-only/CNAME and selected-route details are not selected' @{
            reason = 'AdvancedNetworkDetailsNotSelected'
        } -Classification Coverage -EvidenceKind ObservedNetwork -Remediation 'Use AdvancedNetworkDetails only when DNS-only or route details are useful. Basic DNS, mapping, TCP and TLS remain assessed.'
    }
    foreach ($endpoint in $Context.Endpoints.Values) { Test-LocalEndpoint $Context $endpoint -AdvancedNetworkDetails:$AdvancedNetworkDetails }
}

function Add-LocalHostContext {
    param($Context)
    $interfaces = @()
    $available = $true
    try {
        $interfaces = @([Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object { $_.OperationalStatus -eq 'Up' } | ForEach-Object {
            $ip = $_.GetIPProperties()
            @{ name = $_.Name; type = [string]$_.NetworkInterfaceType
                addresses = @($ip.UnicastAddresses | ForEach-Object { $_.Address.IPAddressToString })
                dnsServers = @($ip.DnsAddresses | ForEach-Object { $_.IPAddressToString })
                gateways = @($ip.GatewayAddresses | ForEach-Object { $_.Address.IPAddressToString }) }
        })
    }
    catch { $available = $false }
    $available = $available -and $interfaces.Count -gt 0
    Add-Check $Context 'endpoint.hostContext' 'Network' '' $(if ($available) {'Observed'} else {'NotAssessed'}) 'Record local interface/resolver/source context' @{
        interfaces = $interfaces; reason = $(if ($available) {'Collected'} else {'InterfaceMetadataUnavailable'})
    } -Classification $(if ($available) {'Inventory'} else {'Coverage'}) -EvidenceKind ObservedNetwork `
        -Limitations @('Selected-route metadata is platform-dependent; endpoint.route records it where supported. TCP rows record the chosen local source. No host settings are changed or VNet membership inferred.')
}
