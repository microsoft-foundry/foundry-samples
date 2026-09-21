function New-TopologyFixture {
    param($Topology)
    $sub = '/subscriptions/11111111-1111-1111-1111-111111111111'
    $rg = "$sub/resourceGroups/fixture-rg"
    $account = "$rg/providers/Microsoft.CognitiveServices/accounts/fixtureaccount"
    $project = "$account/projects/fixtureproject"
    $storage = "$rg/providers/Microsoft.Storage/storageAccounts/fixturestorage"
    $vnet = "$rg/providers/Microsoft.Network/virtualNetworks/fixture-vnet"
    $principal = '22222222-2222-2222-2222-222222222222'
    $responses = @{}
    function Add-Resource([string]$Id, $Properties, $Identity = $null) {
        $responses[$Id] = @{ Code = 200; Data = @{ id = $Id; name = ($Id -split '/')[-1]; location = $Topology.location; properties = $Properties; identity = $Identity } }
    }
    function Add-Collection([string]$Id, $Values) {
        $responses[$Id] = @{ Code = 200; Data = @{ value = @($Values) } }
    }
    Add-Resource $account @{
        provisioningState = 'Succeeded'; publicNetworkAccess = 'Disabled'; disableLocalAuth = $false
        networkInjections = @(@{ scenario = 'agent'; subnetArmId = "$vnet/subnets/agents" })
        endpoint = 'https://fixtureaccount.cognitiveservices.azure.com/'
        endpoints = @{ openai = 'https://fixtureaccount.openai.azure.com/' }
    } @{ type = 'SystemAssigned'; principalId = '33333333-3333-3333-3333-333333333333' }
    Add-Resource $project @{ provisioningState = 'Succeeded'; endpoints = @{ project = 'https://fixtureaccount.services.ai.azure.com/api/projects/fixtureproject' } } @{ type = 'SystemAssigned'; principalId = $principal }
    Add-Resource $vnet @{ provisioningState = 'Succeeded'; dhcpOptions = @{ dnsServers = $(if ($Topology.customDns) { @('10.0.0.4') } else { @() }) } }
    Add-Resource "$vnet/subnets/agents" @{
        provisioningState = 'Succeeded'; delegations = @(@{ properties = @{ serviceName = 'Microsoft.App/environments' } })
        serviceAssociationLinks = @(@{ id = "$vnet/subnets/agents/serviceAssociationLinks/legionservicelink"; properties = @{ allowDelete = $false; linkedResourceType = 'Microsoft.App/environments' } })
        networkSecurityGroup = @{ id = "$rg/providers/Microsoft.Network/networkSecurityGroups/fixture-nsg" }
        routeTable = @{ id = "$rg/providers/Microsoft.Network/routeTables/fixture-routes" }
    }
    Add-Resource "$vnet/subnets/endpoints" @{ provisioningState = 'Succeeded'; delegations = @() }
    Add-Resource "$rg/providers/Microsoft.Network/networkSecurityGroups/fixture-nsg" @{ securityRules = @() }
    Add-Resource "$rg/providers/Microsoft.Network/routeTables/fixture-routes" @{ routes = @(@{ name = 'nva'; properties = @{ addressPrefix = '0.0.0.0/0'; nextHopType = 'VirtualAppliance'; nextHopIpAddress = '10.0.0.4' } }) }
    Add-Resource $storage @{
        provisioningState = 'Succeeded'; publicNetworkAccess = 'Disabled'; allowSharedKeyAccess = $false
        networkAcls = @{ defaultAction = 'Deny' }; primaryEndpoints = @{ blob = 'https://fixturestorage.blob.core.windows.net/' }
    }
    Add-Collection "$account/connections" @()
    $connections = @(
        @{ id = "$project/connections/data"; name = 'data'; properties = @{ category = 'AzureStorageAccount'; authType = 'AAD'; target = 'https://fixturestorage.blob.core.windows.net/'; metadata = @{ ResourceId = $storage } } },
        @{ id = "$project/connections/model-alias"; name = 'model-alias'; properties = @{ category = 'AzureOpenAI'; authType = 'ApiKey'; target = 'https://fixtureaccount.openai.azure.com/'; metadata = @{ ResourceId = $account } } }
    )
    $insights = "$rg/providers/Microsoft.Insights/components/actual-monitor-resource"
    $workspace = "$sub/resourceGroups/shared-monitoring/providers/Microsoft.OperationalInsights/workspaces/actual-logs"
    if ($Topology.monitoring) {
        $monitoringAuth = if ($Topology.location -eq 'koreacentral') { 'ProjectManagedIdentity' } else { 'ApiKey' }
        $connections += @{ id = "$project/connections/friendly-monitor-alias"; name = 'friendly-monitor-alias'; properties = @{
            category = 'AppInsights'; authType = $monitoringAuth; target = $insights
            metadata = @{ ResourceId = $insights; ApplicationInsightsConnectionString = 'fixture-sensitive-monitoring-sentinel' }
        } }
        $queryPolicy = if ($Topology.location -eq 'koreacentral') { 'Enabled' } else { 'Disabled' }
        $privateLinks = if ($queryPolicy -eq 'Disabled') { @(@{
            ResourceId = "$rg/providers/microsoft.insights/privatelinkscopes/fixture-ampls/scopedresources/fixture-insights"
            ScopeId = 'abababab-abab-abab-abab-abababababab'
        }) } else { @() }
        Add-Resource $insights @{ WorkspaceResourceId = $workspace; publicNetworkAccessForQuery = $queryPolicy; publicNetworkAccessForIngestion = $queryPolicy; PrivateLinkScopedResources = $privateLinks }
        Add-Resource $workspace @{ publicNetworkAccessForQuery = $queryPolicy; features = @{ enableLogAccessUsingOnlyResourcePermissions = $true } }
    }
    Add-Collection "$project/connections" $connections
    foreach ($scope in @($account, $project)) {
        $hosts = @()
        if ($scope -ne $project -or $Topology.projectHost) {
            $hosts = @(@{ id = "$scope/capabilityHosts/fixture-host"; name = 'fixture-host'; properties = @{ provisioningState = 'Succeeded'; capabilityHostKind = 'Agents' } })
        }
        Add-Collection "$scope/capabilityHosts" $hosts
    }
    Add-Collection "$account/deployments" @(@{ id = "$account/deployments/fixture-model"; name = 'fixture-model'; properties = @{ provisioningState = 'Succeeded'; model = @{ name = 'fixture-model'; format = 'OpenAI'; version = 'fixture' } } })
    $roleId = "$sub/providers/Microsoft.Authorization/roleDefinitions/44444444-4444-4444-4444-444444444444"
    Add-Resource $roleId @{
        roleName = 'Sanitized custom role, not a built-in role assumption'
        permissions = @(
            @{ actions = @('*/read'); notActions = @(); dataActions = @(); notDataActions = @() },
            @{ actions = @(); notActions = @(); dataActions = @('Microsoft.CognitiveServices/accounts/AIServices/assets/*','Microsoft.Storage/storageAccounts/blobServices/containers/blobs/*','Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action'); notDataActions = @('*/delete') }
        )
    }
    foreach ($resource in @($project, $storage, $account, $workspace, $insights)) {
        foreach ($scope in @(Get-AncestorScopes $resource)) {
            Add-Collection "$scope/providers/Microsoft.Authorization/roleAssignments" @()
            Add-Collection "$scope/providers/Microsoft.Authorization/denyAssignments" @()
        }
    }
    Add-Collection "$rg/providers/Microsoft.Authorization/roleAssignments" @(@{
        id = "$rg/providers/Microsoft.Authorization/roleAssignments/66666666-6666-6666-6666-666666666666"
        properties = @{ scope = $rg; principalId = $principal; principalType = 'ServicePrincipal'; roleDefinitionId = $roleId; createdOn = '2026-08-10T00:00:00Z' }
    })
    Add-Collection "$workspace/providers/Microsoft.Authorization/roleAssignments" @(@{
        id = "$workspace/providers/Microsoft.Authorization/roleAssignments/77777777-7777-7777-7777-777777777777"
        properties = @{ scope = $workspace; principalId = $principal; roleDefinitionId = $roleId; createdOn = '2026-08-10T00:00:00Z' }
    })
    foreach ($target in @(
        @{ Id = $account; Group = 'account'; Label = 'foundry'; Host = 'fixtureaccount.services.ai.azure.com'; Zone = 'privatelink.services.ai.azure.com'; Record = 'fixtureaccount'; Ip = '10.0.1.4' },
        @{ Id = $storage; Group = 'blob'; Label = 'storage'; Host = 'fixturestorage.blob.core.windows.net'; Zone = 'privatelink.blob.core.windows.net'; Record = 'fixturestorage'; Ip = '10.0.1.5' }
    )) {
        $pe = "$rg/providers/Microsoft.Network/privateEndpoints/$($target.Label)"
        $nic = "$rg/providers/Microsoft.Network/networkInterfaces/$($target.Label)"
        $zone = "$rg/providers/Microsoft.Network/privateDnsZones/$($target.Zone)"
        Add-Collection "$($target.Id)/privateEndpointConnections" @(@{ properties = @{ privateEndpoint = @{ id = $pe }; privateLinkServiceConnectionState = @{ status = 'Approved' } } })
        Add-Resource $pe @{
            subnet = @{ id = "$vnet/subnets/endpoints" }
            networkInterfaces = @(@{ id = $nic })
            customDnsConfigs = @(@{ fqdn = "$($target.Record).$($target.Zone)"; ipAddresses = @($target.Ip) })
            privateLinkServiceConnections = @(@{ properties = @{ privateLinkServiceId = $target.Id; groupIds = @($target.Group); privateLinkServiceConnectionState = @{ status = 'Approved' } } })
        }
        Add-Resource $nic @{ ipConfigurations = @(@{ properties = @{ privateIPAddress = $target.Ip } }) }
        Add-Resource $zone @{ provisioningState = 'Succeeded' }
        Add-Collection "$pe/privateDnsZoneGroups" @(@{ properties = @{ privateDnsZoneConfigs = @(@{ properties = @{ privateDnsZoneId = $zone; recordSets = @(@{ recordSetName = $target.Record; fqdn = "$($target.Record).$($target.Zone)"; ipAddresses = @($target.Ip) }) } }) } })
        Add-Collection "$zone/A" @(@{ name = $target.Record; properties = @{ aRecords = @(@{ ipv4Address = $target.Ip }) } })
        Add-Collection "$zone/virtualNetworkLinks" @(@{ properties = @{ virtualNetwork = @{ id = $vnet }; virtualNetworkLinkState = 'Completed' } })
    }
    $foundryPe = "$rg/providers/Microsoft.Network/privateEndpoints/foundry"
    $foundryNic = "$rg/providers/Microsoft.Network/networkInterfaces/foundry"
    foreach ($endpoint in @(
        @{ zone = 'privatelink.openai.azure.com'; ip = '10.0.1.6' },
        @{ zone = 'privatelink.cognitiveservices.azure.com'; ip = '10.0.1.7' }
    )) {
        $zone = "$rg/providers/Microsoft.Network/privateDnsZones/$($endpoint.zone)"
        $alias = "fixtureaccount.$($endpoint.zone)"
        $responses[$foundryPe].Data.properties.customDnsConfigs += @{ fqdn = $alias; ipAddresses = @($endpoint.ip) }
        $responses[$foundryNic].Data.properties.ipConfigurations += @{ properties = @{ privateIPAddress = $endpoint.ip } }
        $responses["$foundryPe/privateDnsZoneGroups"].Data.value[0].properties.privateDnsZoneConfigs += @{
            properties = @{ privateDnsZoneId = $zone; recordSets = @(@{ recordSetName = 'fixtureaccount'; fqdn = $alias; ipAddresses = @($endpoint.ip) }) }
        }
        Add-Resource $zone @{ provisioningState = 'Succeeded' }
        Add-Collection "$zone/A" @(@{ name = 'fixtureaccount'; properties = @{ aRecords = @(@{ ipv4Address = $endpoint.ip }) } })
        Add-Collection "$zone/virtualNetworkLinks" @(@{ properties = @{ virtualNetwork = @{ id = $vnet }; virtualNetworkLinkState = 'Completed' } })
    }
    return @{
        topology = $Topology.name; responses = $responses
        test = @{ project = $project; account = $account; storage = $storage; vnet = $vnet; rg = $rg; sub = $sub; principal = $principal; role = $roleId; insights = $insights; workspace = $workspace }
    }
}
