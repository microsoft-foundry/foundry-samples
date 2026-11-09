# Walks from the project to everything on its network path and builds evidence.discovery.
# Each resource is read once (Invoke-DiagArm caches); unreadable resources are recorded and the walk continues.

function Get-DiagData {
    param($Record)
    if ($Record -and $Record.status -eq 200) { return , $Record.data }
    $null
}

function Get-DiagUrlHost {
    param([string]$Url)
    if (!$Url) { return $null }
    $u = $null
    if ([uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$u) -and $u.Scheme -eq 'https') { return $u.Host.ToLowerInvariant() }
    $null
}

function Get-DiagConnectionPath {
    param([string]$Category)
    switch -Regex ($Category) {
        '^(AzureStorageAccount|AzureBlob)$' { 'Storage' }
        '^AppInsights$' { 'MonitorQuery' }
        '^(AzureOpenAI|AIServices|CognitiveServices)$' { 'Models' }
        default { $null }
    }
}

function Resolve-DiagConnectionResource {
    param($Connection)
    foreach ($candidate in @($Connection.properties.metadata.ResourceId, $Connection.properties.target)) {
        if ($candidate -and (Test-DiagArmPath "$candidate")) { return "$candidate".TrimEnd('/') }
    }
    $null
}

# Picks one connection per path: the one named by -ConnectionName for its kind, otherwise the first.
function Select-DiagConnections {
    param($Ctx, $Connections, [string]$ConnectionName)
    $chosen = [ordered]@{}
    if ($ConnectionName) {
        $named = @($Connections | Where-Object { $_.name -ieq $ConnectionName })[0]
        if (!$named) { Add-DiagCollectorError $Ctx 'discover' 'NotFound' "The project has no connection named '$ConnectionName'." }
        elseif (!(Get-DiagConnectionPath $named.properties.category)) {
            Add-DiagCollectorError $Ctx 'discover' 'Other' "Connection '$ConnectionName' ($($named.properties.category)) isn't used by evaluations; ignored."
        }
        else { $chosen[(Get-DiagConnectionPath $named.properties.category)] = $named }
    }
    foreach ($c in @($Connections)) {
        $path = Get-DiagConnectionPath $c.properties.category
        if ($path -and !$chosen.Contains($path)) { $chosen[$path] = $c }
    }
    $chosen
}

function Get-DiagPeIdsFromConnections {
    param($Ctx, [string]$ResourceId)
    $pecs = Get-DiagData (Invoke-DiagArm $Ctx "$ResourceId/privateEndpointConnections")
    @($pecs | ForEach-Object { $_.properties.privateEndpoint.id } | Where-Object { $_ } | Select-Object -Unique)
}

function Read-DiagPrivateEndpoint {
    param($Ctx, [string]$PeId)
    $pe = Get-DiagData (Invoke-DiagArm $Ctx $PeId)
    if ($pe.properties.subnet.id) {
        $peSubnet = Get-DiagData (Invoke-DiagArm $Ctx $pe.properties.subnet.id)
        if ($peSubnet.properties.networkSecurityGroup.id) { $null = Invoke-DiagArm $Ctx $peSubnet.properties.networkSecurityGroup.id }
    }
    $groups = Get-DiagData (Invoke-DiagArm $Ctx "$PeId/privateDnsZoneGroups")
    foreach ($group in @($groups)) {
        foreach ($cfg in @($group.properties.privateDnsZoneConfigs)) {
            $zone = $cfg.properties.privateDnsZoneId
            if (!$zone) { continue }
            $null = Invoke-DiagArm $Ctx "$zone/virtualNetworkLinks"
            $null = Invoke-DiagArm $Ctx "$zone/A"
        }
    }
    $pe
}

function New-DiagDependency {
    param([string]$Kind, [string]$Path, [string]$Resource, [string]$Connection, [string[]]$PrivateEndpoints = @(), [string[]]$Hosts = @())
    [ordered]@{
        kind = $Kind; path = $Path; resource = $(if ($Resource) { $Resource } else { $null }); connection = $(if ($Connection) { $Connection } else { $null })
        privateEndpoints = @($PrivateEndpoints | Where-Object { $_ } | Select-Object -Unique)
        hosts = @($Hosts | Where-Object { $_ } | ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)
    }
}

function Read-DiagMonitoring {
    param($Ctx, $Connection, [string]$ComponentId, $Deps)
    $component = $(if ($ComponentId) { Get-DiagData (Invoke-DiagArm $Ctx $ComponentId) })
    $Deps.Add((New-DiagDependency AppInsights MonitorQuery $ComponentId $Connection.name -Hosts 'api.applicationinsights.io'))
    $workspaceId = "$($component.properties.WorkspaceResourceId)".TrimEnd('/')
    $workspace = $null
    if ($workspaceId) { $workspace = Get-DiagData (Invoke-DiagArm $Ctx $workspaceId) }
    $Deps.Add((New-DiagDependency Workspace MonitorQuery $workspaceId $null -Hosts 'api.loganalytics.io'))

    $scoped = @($component.properties.privateLinkScopedResources | ForEach-Object { $_.ResourceId }) +
    @($workspace.properties.privateLinkScopedResources | ForEach-Object { $_.resourceId })
    $amplsIds = @($scoped | Where-Object { $_ -match '(?i)^(.+/providers/Microsoft\.Insights/privateLinkScopes/[^/]+)' } |
            ForEach-Object { [regex]::Match($_, '(?i)^(.+/providers/Microsoft\.Insights/privateLinkScopes/[^/]+)').Groups[1].Value } |
            Sort-Object -Unique)
    foreach ($amplsId in $amplsIds) {
        $ampls = Get-DiagData (Invoke-DiagArm $Ctx $amplsId)
        $null = Invoke-DiagArm $Ctx "$amplsId/scopedResources"
        $pes = @($ampls.properties.privateEndpointConnections | ForEach-Object { $_.properties.privateEndpoint.id } | Where-Object { $_ })
        foreach ($pe in $pes) { $null = Read-DiagPrivateEndpoint $Ctx $pe }
        # Evaluations reach Log Analytics and Application Insights through the shared Monitor query host.
        $Deps.Add((New-DiagDependency Ampls MonitorQuery $amplsId $null -PrivateEndpoints $pes -Hosts @('api.monitor.azure.com')))
    }
}

# Finds the Virtual WAN hub the VNet is connected to. Hub VNets are named HV_<hub>_<guid>.
function Find-DiagVirtualHub {
    param($Ctx, [string]$VnetId, $Peerings)
    if (!@($Peerings | Where-Object { (Get-ArmName $_.properties.remoteVirtualNetwork.id) -match '^HV_' }).Count) { return $null }
    $hubs = Get-DiagData (Invoke-DiagResourceGraph $Ctx 'virtualHubs' (Get-DiagGraphQuery virtualHubs))
    foreach ($hub in @($hubs | Select-Object -First 10)) {
        $connections = Get-DiagData (Invoke-DiagArm $Ctx "$($hub.id)/hubVirtualNetworkConnections")
        if (@($connections | Where-Object { Test-SameArmId $_.properties.remoteVirtualNetwork.id $VnetId }).Count) { return $hub.id }
    }
    Add-DiagCollectorError $Ctx 'discover' 'NotFound' 'The VNet is peered with a Virtual WAN hub, but the hub could not be found or read.'
    $null
}

function Read-DiagNicAndVm {
    param($Ctx, [string]$NicId)
    $nic = Get-DiagData (Invoke-DiagArm $Ctx $NicId)
    if ($nic.properties.virtualMachine.id) { $null = Invoke-DiagArm $Ctx $nic.properties.virtualMachine.id }
    if ($nic.properties.networkSecurityGroup.id) { $null = Invoke-DiagArm $Ctx $nic.properties.networkSecurityGroup.id }
    $subnetId = @($nic.properties.ipConfigurations | ForEach-Object { $_.properties.subnet.id } | Where-Object { $_ })[0]
    if ($subnetId) {
        $subnet = Get-DiagData (Invoke-DiagArm $Ctx $subnetId)
        if ($subnet.properties.networkSecurityGroup.id) { $null = Invoke-DiagArm $Ctx $subnet.properties.networkSecurityGroup.id }
    }
    $nic
}

function Read-DiagFirewall {
    param($Ctx, [string]$FirewallId)
    $fw = Get-DiagData (Invoke-DiagArm $Ctx $FirewallId)
    $policyId = $fw.properties.firewallPolicy.id
    $seen = @{}
    while ($policyId -and !$seen.ContainsKey($policyId.ToLowerInvariant()) -and $seen.Count -lt 3) {
        $seen[$policyId.ToLowerInvariant()] = $true
        $policy = Get-DiagData (Invoke-DiagArm $Ctx $policyId)
        $null = Invoke-DiagArm $Ctx "$policyId/ruleCollectionGroups"
        $policyId = $policy.properties.basePolicy.id
    }
    $null = Invoke-DiagArm $Ctx "$FirewallId/providers/Microsoft.Insights/diagnosticSettings"
    $null = Invoke-DiagArm $Ctx "$FirewallId/providers/Microsoft.Insights/metrics"
    $fw
}

function Resolve-DiagNextHop {
    param($Ctx, [string]$Ip, [string]$Source)
    $label = "nextHop:$Ip"
    $record = Invoke-DiagResourceGraph $Ctx $label (Get-DiagGraphQuery nextHop -Ip $Ip)
    $data = Get-DiagData $record
    $rows = @($data)
    $rank = @{ 'microsoft.network/azurefirewalls' = 0; 'microsoft.network/loadbalancers' = 1; 'microsoft.network/networkinterfaces' = 2 }
    $owner = @($rows | Where-Object { $_.type -and $rank.ContainsKey($_.type.ToLowerInvariant()) } | Sort-Object { $rank[$_.type.ToLowerInvariant()] })[0]
    $ownerType = $null
    if ($owner) {
        $ownerType = switch ($owner.type.ToLowerInvariant()) {
            'microsoft.network/azurefirewalls' { 'AzureFirewall' }
            'microsoft.network/loadbalancers' { 'LoadBalancer' }
            'microsoft.network/networkinterfaces' { 'NetworkInterface' }
        }
    }
    [ordered]@{ ip = $Ip; source = $Source; owner = $(if ($owner) { $owner.id } else { $null }); ownerType = $ownerType; request = "POST /providers/Microsoft.ResourceGraph/resources#$label" }
}

function Invoke-DiagDiscover {
    param([Parameter(Mandatory)]$Ctx, [Parameter(Mandatory)][string]$ProjectId, [string]$ConnectionName)
    $accountId = Get-ArmParent $ProjectId
    $deps = [Collections.Generic.List[object]]::new()

    # 1. Project, account, connections, deployments.
    $null = Invoke-DiagArm $Ctx $ProjectId
    $account = Get-DiagData (Invoke-DiagArm $Ctx $accountId)
    $connections = Get-DiagData (Invoke-DiagArm $Ctx "$ProjectId/connections")
    $null = Invoke-DiagArm $Ctx "$accountId/deployments"
    $chosen = Select-DiagConnections $Ctx $connections $ConnectionName

    # 2. Targets, their private endpoints and DNS zones.
    # Only the hosts the agent calls; speech and translator endpoints aren't on the evaluation path.
    $accountHosts = @($account.properties.endpoints.Values | ForEach-Object { Get-DiagUrlHost $_ } |
            Where-Object { $_ -match '(?i)\.(services\.ai|openai|cognitiveservices)\.azure\.(com|us|cn)$' })
    $accountPes = Get-DiagPeIdsFromConnections $Ctx $accountId
    $deps.Add((New-DiagDependency Account Foundry $accountId $null -PrivateEndpoints $accountPes -Hosts $accountHosts))

    if ($chosen.Contains('Storage')) {
        $c = $chosen.Storage; $id = Resolve-DiagConnectionResource $c
        $storage = $(if ($id) { Get-DiagData (Invoke-DiagArm $Ctx $id) })
        $blobHost = Get-DiagUrlHost $storage.properties.primaryEndpoints.blob
        if (!$blobHost) { $blobHost = Get-DiagUrlHost $c.properties.target }
        $pes = $(if ($id) { Get-DiagPeIdsFromConnections $Ctx $id } else { @() })
        $deps.Add((New-DiagDependency Storage Storage $id $c.name -PrivateEndpoints $pes -Hosts $blobHost))
    }
    if ($chosen.Contains('MonitorQuery')) {
        $c = $chosen.MonitorQuery
        Read-DiagMonitoring $Ctx $c (Resolve-DiagConnectionResource $c) $deps
    }
    if ($chosen.Contains('Models')) {
        $c = $chosen.Models; $id = Resolve-DiagConnectionResource $c
        if ($id) { $null = Invoke-DiagArm $Ctx $id }
        $pes = $(if ($id -and $id -ine $accountId) { Get-DiagPeIdsFromConnections $Ctx $id } else { @() })
        $deps.Add((New-DiagDependency Model Models $id $c.name -PrivateEndpoints $pes -Hosts (Get-DiagUrlHost $c.properties.target)))
    }
    foreach ($dep in $deps) { if ($dep.kind -ne 'Ampls') { foreach ($pe in $dep.privateEndpoints) { $null = Read-DiagPrivateEndpoint $Ctx $pe } } }

    # 3. Agent subnet, VNet, NSG, route table, peerings, Virtual WAN hub.
    $agentSubnet = @($account.properties.networkInjections | Where-Object { $_.scenario -eq 'agent' } | ForEach-Object { $_.subnetArmId } | Where-Object { $_ })[0]
    $nextHops = [Collections.Generic.List[object]]::new()
    $firewalls = [Collections.Generic.List[string]]::new()
    $virtualHub = $null
    if ($agentSubnet) {
        $subnet = Get-DiagData (Invoke-DiagArm $Ctx $agentSubnet)
        $vnetId = Get-ArmParent $agentSubnet
        $null = Invoke-DiagArm $Ctx $vnetId
        $peerings = Get-DiagData (Invoke-DiagArm $Ctx "$vnetId/virtualNetworkPeerings")
        if ($subnet.properties.networkSecurityGroup.id) { $null = Invoke-DiagArm $Ctx $subnet.properties.networkSecurityGroup.id }
        if ($subnet.properties.routeTable.id) {
            $routes = Get-DiagData (Invoke-DiagArm $Ctx $subnet.properties.routeTable.id)
            $ips = @($routes.properties.routes | Where-Object { $_.properties.nextHopType -eq 'VirtualAppliance' -and $_.properties.nextHopIpAddress } |
                    ForEach-Object { $_.properties.nextHopIpAddress } | Select-Object -Unique)
            foreach ($ip in $ips) {
                try { $nextHops.Add((Resolve-DiagNextHop $Ctx $ip 'routeTable')) }
                catch { Add-DiagCollectorError $Ctx 'discover' 'Other' "Skipped next hop '$ip': not an IPv4 address." }
            }
        }
        $virtualHub = Find-DiagVirtualHub $Ctx $vnetId $peerings
        if ($virtualHub) {
            $hub = Get-DiagData (Invoke-DiagArm $Ctx $virtualHub)
            $intent = Get-DiagData (Invoke-DiagArm $Ctx "$virtualHub/routingIntent")
            $hubFirewalls = @($hub.properties.azureFirewall.id) + @($intent.properties.routingPolicies | ForEach-Object { $_.nextHop }) |
                Where-Object { $_ -match '(?i)/providers/Microsoft\.Network/azureFirewalls/' }
            foreach ($fw in $hubFirewalls) { if (!($firewalls | Where-Object { $_ -ieq $fw })) { $firewalls.Add($fw) } }
        }
    }

    # 4. Next-hop owners: firewalls, load balancers (with their backend NICs) and NVA NICs.
    foreach ($hop in $nextHops) {
        switch ($hop.ownerType) {
            'AzureFirewall' { if (!($firewalls | Where-Object { $_ -ieq $hop.owner })) { $firewalls.Add($hop.owner) } }
            'NetworkInterface' { $null = Read-DiagNicAndVm $Ctx $hop.owner }
            'LoadBalancer' {
                $lb = Get-DiagData (Invoke-DiagArm $Ctx $hop.owner)
                $nics = @($lb.properties.backendAddressPools | ForEach-Object { $_.properties.backendIPConfigurations } | ForEach-Object { $_.id } |
                        Where-Object { $_ -match '(?i)/networkInterfaces/[^/]+/ipConfigurations/' } | ForEach-Object { $_ -replace '(?i)/ipConfigurations/[^/]+$', '' } |
                        Sort-Object -Unique | Select-Object -First 4)
                foreach ($nic in $nics) { $null = Read-DiagNicAndVm $Ctx $nic }
            }
        }
    }
    foreach ($fwId in $firewalls) {
        $fw = Read-DiagFirewall $Ctx $fwId
        $hubIp = $fw.properties.hubIPAddresses.privateIPAddress
        if ($virtualHub -and !(@($nextHops | Where-Object { Test-SameArmId $_.owner $fwId }).Count)) {
            $nextHops.Add([ordered]@{ ip = $(if ($hubIp) { $hubIp } else { $null }); source = 'virtualHub'; owner = $fwId; ownerType = 'AzureFirewall'; request = $null })
        }
    }

    # 5. Role assignments on the resources the project identity uses.
    foreach ($dep in $deps) {
        if ($dep.kind -in 'Account', 'Storage', 'AppInsights', 'Workspace', 'Model' -and $dep.resource) {
            $null = Invoke-DiagArm $Ctx "$($dep.resource)/providers/Microsoft.Authorization/roleAssignments"
        }
    }

    # 6. The machine running this diagnostic, when it is an Azure VM.
    $runner = [ordered]@{ vm = $null; nic = $null; subnet = $null }
    if ($Ctx.RunnerVmId) {
        $runner.vm = $Ctx.RunnerVmId
        $vm = Get-DiagData (Invoke-DiagArm $Ctx $Ctx.RunnerVmId)
        $nicId = @($vm.properties.networkProfile.networkInterfaces | ForEach-Object { $_.id })[0]
        if ($nicId) {
            $runner.nic = $nicId
            $nic = Get-DiagData (Invoke-DiagArm $Ctx $nicId)
            if ($nic.properties.networkSecurityGroup.id) { $null = Invoke-DiagArm $Ctx $nic.properties.networkSecurityGroup.id }
            $subnetId = @($nic.properties.ipConfigurations | ForEach-Object { $_.properties.subnet.id })[0]
            if ($subnetId) {
                $runner.subnet = $subnetId
                $sn = Get-DiagData (Invoke-DiagArm $Ctx $subnetId)
                if ($sn.properties.networkSecurityGroup.id) { $null = Invoke-DiagArm $Ctx $sn.properties.networkSecurityGroup.id }
                if ($sn.properties.routeTable.id) { $null = Invoke-DiagArm $Ctx $sn.properties.routeTable.id }
            }
        }
    }

    $reason = @{ Storage = 'storage'; MonitorQuery = 'Application Insights'; Models = 'model' }
    $paths = [ordered]@{ Foundry = [ordered]@{ used = $true; reason = 'project' } }
    foreach ($p in 'Storage', 'MonitorQuery', 'Models') {
        $paths[$p] = $(if ($chosen.Contains($p)) { [ordered]@{ used = $true; reason = "connection $($chosen[$p].name)" } }
            else { [ordered]@{ used = $false; reason = "no $($reason[$p]) connection" } })
    }

    [ordered]@{
        project      = $ProjectId
        account      = $accountId
        agentSubnet  = $(if ($agentSubnet) { $agentSubnet } else { $null })
        connections  = @(foreach ($p in $chosen.Keys) {
                [ordered]@{ name = $chosen[$p].name; category = $chosen[$p].properties.category; resource = (Resolve-DiagConnectionResource $chosen[$p]); path = $p }
            })
        dependencies = $deps.ToArray()
        paths        = $paths
        nextHops     = $nextHops.ToArray()
        virtualHub   = $virtualHub
        firewalls    = $firewalls.ToArray()
        runner       = $runner
    }
}
