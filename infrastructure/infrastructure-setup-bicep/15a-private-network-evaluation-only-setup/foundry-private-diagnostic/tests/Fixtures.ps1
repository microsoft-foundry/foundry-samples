# Builds evidence objects for tests. A healthy private-network project is the baseline;
# scenarios change it with the Set-/Remove- helpers.

$script:TS = '00000000-0000-0000-0000-00000000aaaa'

function Get-TestIds {
    $s = "/subscriptions/$script:TS"
    $f = "$s/resourceGroups/rg-foundry/providers"
    $n = "$s/resourceGroups/rg-network/providers/Microsoft.Network"
    $vnet = "$n/virtualNetworks/vnet-agents"
    @{
        Sub = $s
        Account = "$f/Microsoft.CognitiveServices/accounts/acct"
        Project = "$f/Microsoft.CognitiveServices/accounts/acct/projects/proj"
        Storage = "$f/Microsoft.Storage/storageAccounts/stacct"
        AppInsights = "$f/Microsoft.Insights/components/appi"
        Workspace = "$f/Microsoft.OperationalInsights/workspaces/law"
        Ampls = "$f/Microsoft.Insights/privateLinkScopes/ampls"
        Vnet = $vnet
        AgentSubnet = "$vnet/subnets/agents"
        PeSubnet = "$vnet/subnets/pe"
        JumpSubnet = "$vnet/subnets/jumpbox"
        Nsg = "$n/networkSecurityGroups/nsg-agents"
        PeAccount = "$n/privateEndpoints/pe-acct"
        PeStorage = "$n/privateEndpoints/pe-st-blob"
        PeAmpls = "$n/privateEndpoints/pe-ampls"
        Zones = "$s/resourceGroups/rg-network/providers/Microsoft.Network/privateDnsZones"
        Vm = "$s/resourceGroups/rg-network/providers/Microsoft.Compute/virtualMachines/vm-jump"
        Nic = "$n/networkInterfaces/nic-jump"
        ProjectPrincipal = '11111111-1111-1111-1111-111111111111'
        AccountPrincipal = '22222222-2222-2222-2222-222222222222'
        WorkspaceId = '33333333-3333-3333-3333-333333333333'
    }
}

function Get-ArmTypeFromId {
    param([string]$Id)
    if ($Id -notmatch '(?i)/providers/([^/]+)/(.+)$') { return $null }
    $ns = $Matches[1]; $parts = $Matches[2] -split '/'
    $types = for ($i = 0; $i -lt $parts.Count; $i += 2) { $parts[$i] }
    "$ns/$($types -join '/')"
}

function New-ArmObject {
    param([string]$Id, [hashtable]$Properties = @{}, [hashtable]$Extra = @{})
    $o = [ordered]@{ id = $Id; name = ($Id -split '/')[-1]; type = (Get-ArmTypeFromId $Id); location = 'swedencentral'; properties = $Properties }
    foreach ($k in $Extra.Keys) { $o[$k] = $Extra[$k] }
    $o
}

function Set-EvRequest {
    param($E, [string]$Path, $Data, [int]$Status = 200, [string]$ErrorKind, [string]$Method = 'GET', [string]$Api = 'ARM', [string]$Query)
    $key = "$Method $Path"
    $existing = @($E.requests | Where-Object { $_.key -ieq $key })
    $E.requests = @($E.requests | Where-Object { $_.key -ine $key })
    if (!$ErrorKind -and $Status -ne 200) {
        $ErrorKind = switch ($Status) { 404 { 'NotFound' } 403 { 'Forbidden' } 401 { 'Unauthorized' } 429 { 'Throttled' } default { 'Other' } }
    }
    $E.requests += , ([ordered]@{
        key = $key; method = $Method; api = $Api; path = $Path; apiVersion = 'test'; query = $(if ($Query) { $Query } else { $null })
        status = $Status; errorKind = $(if ($Status -eq 200) { $null } else { $ErrorKind }); collectedUtc = '2026-10-22T17:00:00Z'
        data = $(if ($Status -eq 200) { $Data } else { $null })
    })
    $E.Remove('_index')
}

function Set-EvStatus {
    param($E, [string]$Path, [int]$Status, [string]$ErrorKind)
    Set-EvRequest $E $Path $null -Status $Status -ErrorKind $ErrorKind
}

function Remove-EvRequest {
    param($E, [string]$Path, [string]$Method = 'GET')
    $E.requests = @($E.requests | Where-Object { $_.key -ine "$Method $Path" })
    $E.Remove('_index')
}

function Get-EvData {
    param($E, [string]$Path, [string]$Method = 'GET')
    $r = @($E.requests | Where-Object { $_.key -ieq "$Method $Path" })[0]
    if (!$r) { throw "Test evidence has no request '$Method $Path'." }
    $r.data
}

function Get-EvProbe {
    param($E, [string]$HostName)
    $p = @($E.probes | Where-Object { $_.host -ieq $HostName })[0]
    if (!$p) { throw "Test evidence has no probe for '$HostName'." }
    $p
}

function New-TestProbe {
    param([string]$HostName, [string]$Purpose, [string[]]$Ips, [string[]]$Cname = @(), [string]$Resolver = '168.63.129.16', [int]$HttpStatus = 401)
    [ordered]@{
        host = $HostName; port = 443; purpose = $Purpose; budgetHit = $false
        dns = [ordered]@{ resolver = $Resolver; cnameChain = @($HostName) + $Cname; answers = $Ips; ms = 5; error = $null }
        attempts = @($Ips | ForEach-Object {
            [ordered]@{
                ip = $_
                tcp = [ordered]@{ ok = $true; ms = 3; error = $null }
                tls = [ordered]@{ ok = $true; ms = 20; issuer = 'CN=Microsoft Azure RSA TLS Issuing CA 07, O=Microsoft Corporation, C=US'
                    rootIssuer = 'CN=DigiCert Global Root G2, OU=www.digicert.com, O=DigiCert Inc, C=US'; subject = "CN=$HostName"; error = $null }
                http = [ordered]@{ status = $HttpStatus; firstByteMs = 60; server = 'Microsoft-HTTPAPI/2.0'; msRequestId = $true; error = $null }
                outcome = 'Reachable'
            }
        })
        outcome = 'Reachable'
    }
}

function New-ZoneEvidence {
    param($E, [string]$Zone, [hashtable]$Records)
    $ids = Get-TestIds
    $zoneId = "$($ids.Zones)/$Zone"
    Set-EvRequest $E "$zoneId/virtualNetworkLinks" @(
        (New-ArmObject "$zoneId/virtualNetworkLinks/link-agents" @{ virtualNetwork = @{ id = $ids.Vnet }; virtualNetworkLinkState = 'Completed'; registrationEnabled = $false })
    )
    Set-EvRequest $E "$zoneId/A" @($Records.Keys | Sort-Object | ForEach-Object {
        (New-ArmObject "$zoneId/A/$_" @{ fqdn = "$_.$Zone."; aRecords = @(@{ ipv4Address = $Records[$_] }) })
    })
    $zoneId
}

function New-PeEvidence {
    param($E, [string]$PeId, [string]$Target, [string]$GroupId, [hashtable]$FqdnIps, [hashtable]$ZoneRecords)
    $ids = Get-TestIds
    $configs = @($FqdnIps.Keys | Sort-Object | ForEach-Object { [ordered]@{ fqdn = $_; ipAddresses = @($FqdnIps[$_]) } })
    Set-EvRequest $E $PeId (New-ArmObject $PeId @{
        subnet = @{ id = $ids.PeSubnet }
        customDnsConfigs = $configs
        networkInterfaces = @(@{ id = "$PeId.nic" })
        privateLinkServiceConnections = @(@{ name = 'conn'; properties = @{ privateLinkServiceId = $Target; groupIds = @($GroupId)
            privateLinkServiceConnectionState = @{ status = 'Approved' } } })
        manualPrivateLinkServiceConnections = @()
    })
    $zoneConfigs = foreach ($zone in ($ZoneRecords.Keys | Sort-Object)) {
        $zoneId = New-ZoneEvidence $E $zone $ZoneRecords[$zone]
        [ordered]@{ name = $zone; properties = [ordered]@{ privateDnsZoneId = $zoneId
            recordSets = @($ZoneRecords[$zone].Keys | Sort-Object | ForEach-Object {
                [ordered]@{ recordSetName = $_; fqdn = "$_.$zone"; ipAddresses = @($ZoneRecords[$zone][$_]) } }) } }
    }
    Set-EvRequest $E "$PeId/privateDnsZoneGroups" @((New-ArmObject "$PeId/privateDnsZoneGroups/default" @{ privateDnsZoneConfigs = @($zoneConfigs) }))
}

function New-RoleAssignment {
    param([string]$Scope, [string]$PrincipalId, [string]$RoleGuid, [string]$Name)
    New-ArmObject "$Scope/providers/Microsoft.Authorization/roleAssignments/$Name" @{
        principalId = $PrincipalId; principalType = 'ServicePrincipal'; scope = $Scope; conditionPresent = $false
        roleDefinitionId = "/subscriptions/$script:TS/providers/Microsoft.Authorization/roleDefinitions/$RoleGuid"
    }
}

function Get-DefaultNsgRules {
    @(
        @{ name = 'AllowVnetInBound'; properties = @{ priority = 65000; direction = 'Inbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = 'VirtualNetwork'; destinationAddressPrefix = 'VirtualNetwork'; destinationPortRange = '*' } }
        @{ name = 'AllowAzureLoadBalancerInBound'; properties = @{ priority = 65001; direction = 'Inbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = 'AzureLoadBalancer'; destinationAddressPrefix = '*'; destinationPortRange = '*' } }
        @{ name = 'DenyAllInBound'; properties = @{ priority = 65500; direction = 'Inbound'; access = 'Deny'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = '*'; destinationPortRange = '*' } }
        @{ name = 'AllowVnetOutBound'; properties = @{ priority = 65000; direction = 'Outbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = 'VirtualNetwork'; destinationAddressPrefix = 'VirtualNetwork'; destinationPortRange = '*' } }
        @{ name = 'AllowInternetOutBound'; properties = @{ priority = 65001; direction = 'Outbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = 'Internet'; destinationPortRange = '*' } }
        @{ name = 'DenyAllOutBound'; properties = @{ priority = 65500; direction = 'Outbound'; access = 'Deny'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = '*'; destinationPortRange = '*' } }
    )
}

# Healthy private project: account, storage and Azure Monitor (via AMPLS) all private, Azure-provided DNS,
# no route table, runner VM in a sibling subnet with the same NSG.
function New-HealthyEvidence {
    $ids = Get-TestIds
    $E = [ordered]@{
        schema = 1
        tool = @{ commit = 'test' }
        run = [ordered]@{ startedUtc = '2026-10-22T17:00:00Z'; durationMs = 1000; masked = $false; project = $ids.Project
            runner = [ordered]@{ os = 'Windows'; tokenSource = 'ManagedIdentity'; azureVmResourceId = $ids.Vm
                dnsServers = @('168.63.129.16'); proxy = @{ system = 'none'; env = @() } } }
        discovery = $null
        requests = @()
        probes = @()
        collectorErrors = @()
    }

    Set-EvRequest $E $ids.Project (New-ArmObject $ids.Project @{ provisioningState = 'Succeeded' } @{ identity = @{ type = 'SystemAssigned'; principalId = $ids.ProjectPrincipal } })
    Set-EvRequest $E $ids.Account (New-ArmObject $ids.Account @{
        provisioningState = 'Succeeded'; publicNetworkAccess = 'Disabled'; disableLocalAuth = $true
        networkAcls = @{ defaultAction = 'Deny' }
        networkInjections = @(@{ scenario = 'agent'; subnetArmId = $ids.AgentSubnet; useMicrosoftManagedNetwork = $false })
        endpoints = [ordered]@{ 'AI Foundry API' = 'https://acct.services.ai.azure.com/'; 'OpenAI Language Model Instance API' = 'https://acct.openai.azure.com/'; 'Cognitive Services' = 'https://acct.cognitiveservices.azure.com/' }
    } @{ identity = @{ type = 'SystemAssigned'; principalId = $ids.AccountPrincipal }; kind = 'AIServices' })
    Set-EvRequest $E "$($ids.Project)/connections" @(
        (New-ArmObject "$($ids.Project)/connections/storage-conn" @{ category = 'AzureStorageAccount'; target = 'https://stacct.blob.core.windows.net/'; authType = 'AAD'; metadata = @{ ResourceId = $ids.Storage } })
        (New-ArmObject "$($ids.Project)/connections/appinsights-conn" @{ category = 'AppInsights'; target = $ids.AppInsights; authType = 'ApiKey'; metadata = @{ ResourceId = $ids.AppInsights } })
    )
    Set-EvRequest $E "$($ids.Account)/deployments" @((New-ArmObject "$($ids.Account)/deployments/gpt-4o" @{ provisioningState = 'Succeeded'; model = @{ name = 'gpt-4o'; format = 'OpenAI'; version = '2024-11-20' } }))

    # Network
    Set-EvRequest $E $ids.Vnet (New-ArmObject $ids.Vnet @{
        addressSpace = @{ addressPrefixes = @('10.1.0.0/16') }; dhcpOptions = @{ dnsServers = @() }
        subnets = @(@{ name = 'agents'; id = $ids.AgentSubnet }, @{ name = 'pe'; id = $ids.PeSubnet }, @{ name = 'jumpbox'; id = $ids.JumpSubnet })
    })
    Set-EvRequest $E "$($ids.Vnet)/virtualNetworkPeerings" @()
    Set-EvRequest $E $ids.AgentSubnet (New-ArmObject $ids.AgentSubnet @{
        addressPrefix = '10.1.2.0/24'; networkSecurityGroup = @{ id = $ids.Nsg }; privateEndpointNetworkPolicies = 'Disabled'
        delegations = @(@{ name = 'aca'; properties = @{ serviceName = 'Microsoft.App/environments' } })
        serviceAssociationLinks = @(@{ name = 'legionservicelink'; properties = @{ linkedResourceType = 'Microsoft.App/environments' } })
    })
    Set-EvRequest $E $ids.PeSubnet (New-ArmObject $ids.PeSubnet @{ addressPrefix = '10.1.5.0/24'; privateEndpointNetworkPolicies = 'Disabled'; delegations = @() })
    Set-EvRequest $E $ids.JumpSubnet (New-ArmObject $ids.JumpSubnet @{ addressPrefix = '10.1.9.0/24'; networkSecurityGroup = @{ id = $ids.Nsg }; delegations = @() })
    Set-EvRequest $E $ids.Nsg (New-ArmObject $ids.Nsg @{ securityRules = @(); defaultSecurityRules = @(Get-DefaultNsgRules) })

    # Private endpoints + DNS
    Set-EvRequest $E "$($ids.Account)/privateEndpointConnections" @((New-ArmObject "$($ids.Account)/privateEndpointConnections/pec-acct" @{ privateEndpoint = @{ id = $ids.PeAccount }; privateLinkServiceConnectionState = @{ status = 'Approved' }; groupIds = @('account') }))
    New-PeEvidence $E $ids.PeAccount $ids.Account 'account' @{ 'acct.services.ai.azure.com' = '10.1.5.4'; 'acct.openai.azure.com' = '10.1.5.5'; 'acct.cognitiveservices.azure.com' = '10.1.5.6' } @{
        'privatelink.services.ai.azure.com' = @{ acct = '10.1.5.4' }; 'privatelink.openai.azure.com' = @{ acct = '10.1.5.5' }; 'privatelink.cognitiveservices.azure.com' = @{ acct = '10.1.5.6' } }
    Set-EvRequest $E "$($ids.Storage)/privateEndpointConnections" @((New-ArmObject "$($ids.Storage)/privateEndpointConnections/pec-st" @{ privateEndpoint = @{ id = $ids.PeStorage }; privateLinkServiceConnectionState = @{ status = 'Approved' }; groupIds = @('blob') }))
    New-PeEvidence $E $ids.PeStorage $ids.Storage 'blob' @{ 'stacct.blob.core.windows.net' = '10.1.5.7' } @{ 'privatelink.blob.core.windows.net' = @{ stacct = '10.1.5.7' } }
    $w = $ids.WorkspaceId
    New-PeEvidence $E $ids.PeAmpls $ids.Ampls 'azuremonitor' ([ordered]@{
        'api.monitor.azure.com' = '10.1.5.13'; 'global.in.ai.monitor.azure.com' = '10.1.5.14'; "$w.oms.opinsights.azure.com" = '10.1.5.15'
        "$w.ods.opinsights.azure.com" = '10.1.5.16'; "$w.agentsvc.azure-automation.net" = '10.1.5.17' }) @{
        'privatelink.monitor.azure.com' = @{ api = '10.1.5.13'; 'global.in.ai' = '10.1.5.14' }
        'privatelink.oms.opinsights.azure.com' = @{ $w = '10.1.5.15' }; 'privatelink.ods.opinsights.azure.com' = @{ $w = '10.1.5.16' }
        'privatelink.agentsvc.azure-automation.net' = @{ $w = '10.1.5.17' } }

    # Dependencies
    Set-EvRequest $E $ids.Storage (New-ArmObject $ids.Storage @{ provisioningState = 'Succeeded'; publicNetworkAccess = 'Disabled'; allowSharedKeyAccess = $false
        networkAcls = @{ defaultAction = 'Deny'; bypass = 'AzureServices' }; primaryEndpoints = @{ blob = 'https://stacct.blob.core.windows.net/' } } @{ kind = 'StorageV2' })
    Set-EvRequest $E $ids.AppInsights (New-ArmObject $ids.AppInsights @{ provisioningState = 'Succeeded'; WorkspaceResourceId = $ids.Workspace
        publicNetworkAccessForIngestion = 'Disabled'; publicNetworkAccessForQuery = 'Disabled'
        privateLinkScopedResources = @(@{ ResourceId = "$($ids.Ampls)/scopedResources/appi"; ScopeId = 'scope' }) })
    Set-EvRequest $E $ids.Workspace (New-ArmObject $ids.Workspace @{ provisioningState = 'Succeeded'; publicNetworkAccessForIngestion = 'Disabled'; publicNetworkAccessForQuery = 'Disabled'
        features = @{ enableLogAccessUsingOnlyResourcePermissions = $true }
        privateLinkScopedResources = @(@{ resourceId = "$($ids.Ampls)/scopedResources/law"; scopeId = 'scope' }) })
    Set-EvRequest $E $ids.Ampls (New-ArmObject $ids.Ampls @{ accessModeSettings = @{ ingestionAccessMode = 'PrivateOnly'; queryAccessMode = 'PrivateOnly'; exclusions = @() }
        privateEndpointConnections = @(@{ properties = @{ privateEndpoint = @{ id = $ids.PeAmpls }; privateLinkServiceConnectionState = @{ status = 'Approved' } } }) } @{ location = 'global' })
    Set-EvRequest $E "$($ids.Ampls)/scopedResources" @(
        (New-ArmObject "$($ids.Ampls)/scopedResources/appi" @{ linkedResourceId = $ids.AppInsights; provisioningState = 'Succeeded' })
        (New-ArmObject "$($ids.Ampls)/scopedResources/law" @{ linkedResourceId = $ids.Workspace; provisioningState = 'Succeeded' })
    )

    # Access
    $ra = '/providers/Microsoft.Authorization/roleAssignments'
    Set-EvRequest $E "$($ids.Storage)$ra" @((New-RoleAssignment $ids.Storage $ids.ProjectPrincipal 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' 'ra-st'))
    Set-EvRequest $E "$($ids.AppInsights)$ra" @((New-RoleAssignment $ids.AppInsights $ids.ProjectPrincipal '73c42c96-874c-492b-b04d-ab87d138a893' 'ra-appi'))
    Set-EvRequest $E "$($ids.Workspace)$ra" @()
    Set-EvRequest $E "$($ids.Account)$ra" @()

    # Runner
    Set-EvRequest $E $ids.Vm (New-ArmObject $ids.Vm @{ networkProfile = @{ networkInterfaces = @(@{ id = $ids.Nic }) }; storageProfile = @{ imageReference = @{ publisher = 'MicrosoftWindowsServer'; offer = 'WindowsServer'; sku = '2022-datacenter' } } })
    Set-EvRequest $E $ids.Nic (New-ArmObject $ids.Nic @{ enableIPForwarding = $false; virtualMachine = @{ id = $ids.Vm }
        ipConfigurations = @(@{ properties = @{ privateIPAddress = '10.1.9.4'; subnet = @{ id = $ids.JumpSubnet } } }) })

    # Probes from the runner
    $E.probes = @(
        (New-TestProbe 'acct.services.ai.azure.com' 'Foundry' @('10.1.5.4') @('acct.privatelink.services.ai.azure.com'))
        (New-TestProbe 'stacct.blob.core.windows.net' 'Storage' @('10.1.5.7') @('stacct.privatelink.blob.core.windows.net') -HttpStatus 400)
        (New-TestProbe 'api.loganalytics.io' 'MonitorQuery' @('10.1.5.13') @('api.privatelink.monitor.azure.com') -HttpStatus 404)
        (New-TestProbe 'api.applicationinsights.io' 'MonitorQuery' @('10.1.5.13') @('api.privatelink.monitor.azure.com') -HttpStatus 404)
        (New-TestProbe 'management.azure.com' 'Comparison' @('4.150.240.10') -HttpStatus 400)
    )

    $E.discovery = [ordered]@{
        project = $ids.Project
        account = $ids.Account
        agentSubnet = $ids.AgentSubnet
        connections = @(
            [ordered]@{ name = 'storage-conn'; category = 'AzureStorageAccount'; resource = $ids.Storage; path = 'Storage' }
            [ordered]@{ name = 'appinsights-conn'; category = 'AppInsights'; resource = $ids.AppInsights; path = 'MonitorQuery' }
        )
        dependencies = @(
            [ordered]@{ kind = 'Account'; path = 'Foundry'; resource = $ids.Account; connection = $null; privateEndpoints = @($ids.PeAccount)
                hosts = @('acct.services.ai.azure.com', 'acct.openai.azure.com', 'acct.cognitiveservices.azure.com') }
            [ordered]@{ kind = 'Storage'; path = 'Storage'; resource = $ids.Storage; connection = 'storage-conn'; privateEndpoints = @($ids.PeStorage); hosts = @('stacct.blob.core.windows.net') }
            [ordered]@{ kind = 'AppInsights'; path = 'MonitorQuery'; resource = $ids.AppInsights; connection = 'appinsights-conn'; privateEndpoints = @(); hosts = @('api.applicationinsights.io') }
            [ordered]@{ kind = 'Workspace'; path = 'MonitorQuery'; resource = $ids.Workspace; connection = $null; privateEndpoints = @(); hosts = @('api.loganalytics.io') }
            [ordered]@{ kind = 'Ampls'; path = 'MonitorQuery'; resource = $ids.Ampls; connection = $null; privateEndpoints = @($ids.PeAmpls)
                hosts = @('api.monitor.azure.com') }
        )
        paths = [ordered]@{
            Foundry = @{ used = $true; reason = 'project' }
            Storage = @{ used = $true; reason = 'connection storage-conn' }
            MonitorQuery = @{ used = $true; reason = 'connection appinsights-conn' }
            Models = @{ used = $false; reason = 'no model connection' }
        }
        nextHops = @()
        virtualHub = $null
        firewalls = @()
        runner = [ordered]@{ vm = $ids.Vm; nic = $ids.Nic; subnet = $ids.JumpSubnet }
    }
    $E
}

# --- Network builders: route tables, peerings, next hops, firewalls, hubs and appliances. ---------------------------
# Used by the Egress, Firewall and Nva scenarios.

function Get-DiagTestNetIds {
    $ids = Get-TestIds
    $hub = "$($ids.Sub)/resourceGroups/rg-hub/providers/Microsoft.Network"
    @{
        RouteTable = "$($ids.Sub)/resourceGroups/rg-network/providers/Microsoft.Network/routeTables/rt-agents"
        HubVnet = "$hub/virtualNetworks/vnet-hub"
        Firewall = "$hub/azureFirewalls/fw-hub"
        Policy = "$hub/firewallPolicies/fwp-agents"
        ParentPolicy = "$hub/firewallPolicies/fwp-base"
        Hub = "$hub/virtualHubs/vhub"
        NvaNic = "$hub/networkInterfaces/nic-nva"
        NvaVm = "$($ids.Sub)/resourceGroups/rg-hub/providers/Microsoft.Compute/virtualMachines/vm-nva"
        NvaSubnet = "$hub/virtualNetworks/vnet-hub/subnets/nva"
        NvaNsg = "$hub/networkSecurityGroups/nsg-nva"
        NvaSubnetNsg = "$hub/networkSecurityGroups/nsg-nva-subnet"
        Lb = "$hub/loadBalancers/lb-nva"
        FwIp = '10.0.1.4'; HubFwIp = '10.0.64.4'; NvaIp = '10.0.2.4'; LbIp = '10.0.2.10'
    }
}

function New-DiagTestRoute {
    param([string]$Name, [string]$Prefix, [string]$Type, [string]$Ip)
    $p = @{ addressPrefix = $Prefix; nextHopType = $Type }
    if ($Ip) { $p.nextHopIpAddress = $Ip }
    @{ name = $Name; properties = $p }
}

# Route table on the agent subnet. BGP propagation is off unless -BgpOn.
function Add-DiagTestRouteTable {
    param($E, [object[]]$Routes, [switch]$BgpOn)
    $ids = Get-TestIds; $n = Get-DiagTestNetIds
    Set-EvRequest $E $n.RouteTable (New-ArmObject $n.RouteTable @{ disableBgpRoutePropagation = !$BgpOn; routes = @($Routes) })
    (Get-EvData $E $ids.AgentSubnet).properties.routeTable = @{ id = $n.RouteTable }
}

function Add-DiagTestPeering {
    param($E, [string]$State = 'Connected', [bool]$Forwarded = $true, [switch]$UseRemoteGateways, [string]$Name = 'to-hub')
    $ids = Get-TestIds; $n = Get-DiagTestNetIds
    $peer = New-ArmObject "$($ids.Vnet)/virtualNetworkPeerings/$Name" @{ peeringState = $State; remoteVirtualNetwork = @{ id = $n.HubVnet }
        allowForwardedTraffic = $Forwarded; allowGatewayTransit = $false; useRemoteGateways = [bool]$UseRemoteGateways }
    Set-EvRequest $E "$($ids.Vnet)/virtualNetworkPeerings" @(@(Get-EvData $E "$($ids.Vnet)/virtualNetworkPeerings" | Where-Object { $_ -and $_.name -ne $Name }) + @($peer))
}

# discovery.nextHops entry plus the Resource Graph request that resolved it.
function Add-DiagTestNextHop {
    param($E, [string]$Ip, [string]$Owner, [string]$OwnerType, [string]$Source = 'routeTable', [int]$Status = 200)
    $path = "/providers/Microsoft.ResourceGraph/resources#nextHop:$Ip"
    # Resource Graph returns ARM types; discovery maps them to the owner kind.
    $armType = @{ AzureFirewall = 'microsoft.network/azurefirewalls'; LoadBalancer = 'microsoft.network/loadbalancers'; NetworkInterface = 'microsoft.network/networkinterfaces' }[$OwnerType]
    $data = @(if ($Owner) { @{ id = $Owner; type = $(if ($armType) { $armType } else { $OwnerType }) } })
    Set-EvRequest $E $path $data -Status $Status -Method POST -Api ResourceGraph -Query "Resources | where properties has '$Ip'"
    $E.discovery.nextHops = @(@($E.discovery.nextHops | Where-Object { $_ -and $_.ip -ne $Ip }) + @([ordered]@{
        ip = $Ip; source = $Source; owner = $(if ($Owner) { $Owner } else { $null }); ownerType = $(if ($OwnerType) { $OwnerType } else { $null }); request = "POST $path" }))
}

# Azure Monitor query without AMPLS private endpoints, so api.loganalytics.io goes to the internet route.
function Set-DiagTestMonitorPublic {
    param($E)
    foreach ($dep in @($E.discovery.dependencies | Where-Object { $_.kind -eq 'Ampls' })) {
        $dep.privateEndpoints = @(); $dep.hosts = @()
        $ampls = Get-EvData $E $dep.resource
        $ampls.properties.privateEndpointConnections = @()
        $ampls.properties.accessModeSettings.queryAccessMode = 'Open'
    }
    foreach ($dep in @($E.discovery.dependencies | Where-Object { $_.kind -in 'AppInsights', 'Workspace' })) {
        (Get-EvData $E $dep.resource).properties.publicNetworkAccessForQuery = 'Enabled'
    }
}

function New-DiagTestAppRule {
    param([string]$Name, [string[]]$Fqdns, [string[]]$Sources = @('10.1.2.0/24'), [switch]$Tls, [string[]]$IpGroups = @(), [string[]]$WebCategories = @(), [string]$Protocol = 'Https', [int]$Port = 443)
    @{ ruleType = 'ApplicationRule'; name = $Name; sourceAddresses = @($Sources); sourceIpGroups = @($IpGroups); targetFqdns = @($Fqdns); fqdnTags = @()
       webCategories = @($WebCategories); targetUrls = @(); protocols = @(@{ protocolType = $Protocol; port = $Port }); terminateTLS = [bool]$Tls }
}

function New-DiagTestNetRule {
    param([string]$Name, [string[]]$Destinations = @(), [string[]]$Fqdns = @(), [string[]]$Ports = @('443'), [string[]]$Sources = @('10.1.2.0/24'), [string[]]$Protocols = @('TCP'))
    @{ ruleType = 'NetworkRule'; name = $Name; sourceAddresses = @($Sources); sourceIpGroups = @(); destinationAddresses = @($Destinations)
       destinationFqdns = @($Fqdns); destinationPorts = @($Ports); ipProtocols = @($Protocols) }
}

function New-DiagTestRc {
    param([string]$Name, [int]$Priority, [string]$Action = 'Allow', [object[]]$Rules)
    @{ ruleCollectionType = 'FirewallPolicyFilterRuleCollection'; name = $Name; priority = $Priority; action = @{ type = $Action }; rules = @($Rules) }
}

function New-DiagTestRcg {
    param([string]$Name, [int]$Priority, [object[]]$Collections)
    @{ Name = $Name; Priority = $Priority; Collections = @($Collections) }
}

# The recommended rules: private endpoints by network rule, Monitor query FQDNs by application rule.
function Get-DiagTestAllowGroups {
    @(New-DiagTestRcg 'rcg-agents' 200 @(
        (New-DiagTestRc 'net-private-endpoints' 100 Allow @(New-DiagTestNetRule 'to-private-endpoints' -Destinations @('10.1.5.0/24')))
        (New-DiagTestRc 'app-evaluation' 200 Allow @(New-DiagTestAppRule 'monitor-query' @('api.loganalytics.io', 'api.applicationinsights.io')))
    ))
}

function Set-DiagTestPolicy {
    param($E, [string]$PolicyId, [object[]]$Groups, [hashtable]$Props = @{}, [string]$BasePolicy)
    $p = @{ sku = @{ tier = 'Premium' }; threatIntelMode = 'Alert'; intrusionDetection = @{ mode = 'Off' }; dnsSettings = @{ enableProxy = $false; servers = @() } }
    foreach ($k in $Props.Keys) { $p[$k] = $Props[$k] }
    if ($BasePolicy) { $p.basePolicy = @{ id = $BasePolicy } }
    Set-EvRequest $E $PolicyId (New-ArmObject $PolicyId $p)
    Set-EvRequest $E "$PolicyId/ruleCollectionGroups" @(@($Groups) | Where-Object { $_ } | ForEach-Object {
        New-ArmObject "$PolicyId/ruleCollectionGroups/$($_.Name)" @{ priority = $_.Priority; ruleCollections = @($_.Collections) } })
}

# Azure Firewall with a policy (or classic rules), logs to the workspace, and SNAT metrics.
function Add-DiagTestFirewall {
    param($E, [string]$FirewallId, [object[]]$Groups, [hashtable]$PolicyProps = @{}, [object[]]$ParentGroups, [hashtable]$ParentProps,
        [switch]$Classic, [object[]]$ClassicApp = @(), [object[]]$ClassicNet = @(), [hashtable]$ClassicProps = @{}, [switch]$InHub, $SnatMax = 20)
    $ids = Get-TestIds; $n = Get-DiagTestNetIds
    $fw = $(if ($FirewallId) { $FirewallId } else { $n.Firewall })
    if ($null -eq $Groups) { $Groups = Get-DiagTestAllowGroups }
    $p = @{ provisioningState = 'Succeeded'; sku = @{ name = $(if ($InHub) { 'AZFW_Hub' } else { 'AZFW_VNet' }); tier = 'Premium' }; threatIntelMode = 'Alert'; additionalProperties = @{} }
    if ($InHub) { $p.hubIPAddresses = @{ privateIPAddress = $n.HubFwIp }; $p.virtualHub = @{ id = $n.Hub } }
    else { $p.ipConfigurations = @(@{ properties = @{ privateIPAddress = $n.FwIp } }) }
    if ($Classic) {
        $p.applicationRuleCollections = @($ClassicApp); $p.networkRuleCollections = @($ClassicNet)
        foreach ($k in $ClassicProps.Keys) { $p[$k] = $ClassicProps[$k] }
    }
    else {
        $p.firewallPolicy = @{ id = $n.Policy }
        if ($null -ne $ParentGroups -or $ParentProps) {
            Set-DiagTestPolicy $E $n.ParentPolicy $ParentGroups $(if ($ParentProps) { $ParentProps } else { @{} })
            Set-DiagTestPolicy $E $n.Policy $Groups $PolicyProps -BasePolicy $n.ParentPolicy
        }
        else { Set-DiagTestPolicy $E $n.Policy $Groups $PolicyProps }
    }
    Set-EvRequest $E $fw (New-ArmObject $fw $p)
    Set-EvRequest $E "$fw/providers/Microsoft.Insights/diagnosticSettings" @(New-ArmObject "$fw/providers/Microsoft.Insights/diagnosticSettings/fw-logs" @{
        workspaceId = $ids.Workspace; logs = @(@{ category = $null; categoryGroup = 'allLogs'; enabled = $true }) })
    Set-EvRequest $E "$fw/providers/Microsoft.Insights/metrics" @{ metric = 'SNATPortUtilization'; timespan = 'PT24H'; maximum = $SnatMax; average = $(if ($null -ne $SnatMax) { 5 } else { $null }) }
    $E.discovery.firewalls = @(@($E.discovery.firewalls | Where-Object { $_ }) + @($fw))
    $fw
}

# Forced tunneling: Monitor query goes public, 0.0.0.0/0 goes to the hub firewall over a peering.
function Add-DiagTestForcedTunnel {
    param($E, [string]$Ip, [string]$Owner, [string]$OwnerType = 'AzureFirewall', [string]$Type = 'VirtualAppliance', [switch]$NoPeering, [object[]]$ExtraRoutes = @())
    $n = Get-DiagTestNetIds
    if (!$Ip -and $Type -eq 'VirtualAppliance') { $Ip = $n.FwIp }
    Set-DiagTestMonitorPublic $E
    Add-DiagTestRouteTable $E (@(New-DiagTestRoute 'default' '0.0.0.0/0' $Type $Ip) + @($ExtraRoutes))
    if (!$NoPeering) { Add-DiagTestPeering $E }
    if ($Ip -and ($Owner -or $PSBoundParameters.ContainsKey('Owner'))) { Add-DiagTestNextHop $E $Ip $Owner $OwnerType }
}

# The common case: forced tunneling to a hub Azure Firewall.
function Add-DiagTestFirewallEgress {
    param($E, [hashtable]$Firewall = @{})
    $fw = Add-DiagTestFirewall $E @Firewall
    Add-DiagTestForcedTunnel $E -Owner $fw
    $fw
}

# Virtual WAN hub with routing intent sending internet (and optionally private) traffic to the hub firewall.
function Add-DiagTestHub {
    param($E, [string[]]$Destinations = @('Internet'), [hashtable]$Firewall = @{}, [string]$RoutingState = 'Provisioned')
    $n = Get-DiagTestNetIds
    $Firewall.InHub = $true
    $fw = Add-DiagTestFirewall $E @Firewall
    Set-EvRequest $E $n.Hub (New-ArmObject $n.Hub @{ provisioningState = 'Succeeded'; routingState = $RoutingState; azureFirewall = @{ id = $fw } })
    Set-EvRequest $E "$($n.Hub)/routingIntent" @(New-ArmObject "$($n.Hub)/routingIntent/ri-hub" @{
        routingPolicies = @($Destinations | ForEach-Object { @{ name = "${_}Traffic"; destinations = @($_); nextHop = $fw } }) })
    # Discovery finds the hub from a peering to its HV_* VNet, Resource Graph, and the hub's VNet connection.
    $ids = Get-TestIds
    $hubVnet = "$($ids.Sub)/resourceGroups/RG_vhub_internal/providers/Microsoft.Network/virtualNetworks/HV_vhub_00000000-0000-0000-0000-0000000000bb"
    $peer = New-ArmObject "$($ids.Vnet)/virtualNetworkPeerings/to-vhub" @{ peeringState = 'Connected'; remoteVirtualNetwork = @{ id = $hubVnet }
        allowForwardedTraffic = $true; allowGatewayTransit = $false; useRemoteGateways = $false }
    Set-EvRequest $E "$($ids.Vnet)/virtualNetworkPeerings" @(@(Get-EvData $E "$($ids.Vnet)/virtualNetworkPeerings" | Where-Object { $_ -and $_.name -ne 'to-vhub' }) + @($peer))
    Set-EvRequest $E '/providers/Microsoft.ResourceGraph/resources#virtualHubs' @(@{ id = $n.Hub; type = 'microsoft.network/virtualhubs' }) -Method POST -Api ResourceGraph
    Set-EvRequest $E "$($n.Hub)/hubVirtualNetworkConnections" @(New-ArmObject "$($n.Hub)/hubVirtualNetworkConnections/agents" @{ remoteVirtualNetwork = @{ id = $ids.Vnet } })
    $E.discovery.virtualHub = $n.Hub
    Set-DiagTestMonitorPublic $E
    $E.discovery.nextHops = @(@($E.discovery.nextHops | Where-Object { $_ }) + @([ordered]@{ ip = $n.HubFwIp; source = 'virtualHub'; owner = $fw; ownerType = 'AzureFirewall'; request = $null }))
    $fw
}

# Third-party appliance VM (or a load balancer in front of it) in the hub, with NSGs on its NIC and subnet.
function Add-DiagTestNva {
    param($E, [bool]$IpForwarding = $true, [object[]]$NicRules = @(), [object[]]$SubnetRules = @(), [switch]$ViaLb, [switch]$NoBackends, [switch]$NoRoute)
    $n = Get-DiagTestNetIds
    $nicProps = @{ enableIPForwarding = $IpForwarding; networkSecurityGroup = @{ id = $n.NvaNsg }; virtualMachine = @{ id = $n.NvaVm }
        ipConfigurations = @(@{ properties = @{ privateIPAddress = $n.NvaIp; subnet = @{ id = $n.NvaSubnet }
            loadBalancerBackendAddressPools = @(if ($ViaLb -and !$NoBackends) { @{ id = "$($n.Lb)/backendAddressPools/nva" } }) } }) }
    Set-EvRequest $E $n.NvaNic (New-ArmObject $n.NvaNic $nicProps)
    Set-EvRequest $E $n.NvaVm (New-ArmObject $n.NvaVm @{ networkProfile = @{ networkInterfaces = @(@{ id = $n.NvaNic }) }
        storageProfile = @{ imageReference = @{ publisher = 'paloaltonetworks'; offer = 'vmseries-flex'; sku = 'byol' } } } @{ plan = @{ publisher = 'paloaltonetworks'; product = 'vmseries-flex' } })
    Set-EvRequest $E $n.NvaSubnet (New-ArmObject $n.NvaSubnet @{ addressPrefix = '10.0.2.0/24'; networkSecurityGroup = @{ id = $n.NvaSubnetNsg } })
    Set-EvRequest $E $n.NvaNsg (New-ArmObject $n.NvaNsg @{ securityRules = @($NicRules); defaultSecurityRules = @(Get-DefaultNsgRules) })
    Set-EvRequest $E $n.NvaSubnetNsg (New-ArmObject $n.NvaSubnetNsg @{ securityRules = @($SubnetRules); defaultSecurityRules = @(Get-DefaultNsgRules) })
    if ($ViaLb) {
        Set-EvRequest $E $n.Lb (New-ArmObject $n.Lb @{ frontendIPConfigurations = @(@{ properties = @{ privateIPAddress = $n.LbIp; subnet = @{ id = $n.NvaSubnet } } })
            backendAddressPools = @(@{ id = "$($n.Lb)/backendAddressPools/nva"; properties = @{ backendIPConfigurations = @(if (!$NoBackends) { @{ id = "$($n.NvaNic)/ipConfigurations/ipconfig1" } }) } }) } @{ sku = @{ name = 'Standard' } })
    }
    if (!$NoRoute) {
        if ($ViaLb) { Add-DiagTestForcedTunnel $E -Ip $n.LbIp -Owner $n.Lb -OwnerType LoadBalancer }
        else { Add-DiagTestForcedTunnel $E -Ip $n.NvaIp -Owner $n.NvaNic -OwnerType NetworkInterface }
    }
}

function New-DiagTestNsgRule {
    param([string]$Name, [int]$Priority, [string]$Access = 'Deny', [string]$Source = '*', [string]$Destination = '*', [string]$Port = '443', [string]$Protocol = 'Tcp')
    @{ name = $Name; properties = @{ priority = $Priority; direction = 'Inbound'; access = $Access; protocol = $Protocol; sourceAddressPrefix = $Source
        destinationAddressPrefix = $Destination; destinationPortRange = $Port } }
}
