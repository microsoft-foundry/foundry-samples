. (Join-Path $PSScriptRoot 'Common.ps1')

function Get-Names($Config) {
    $ids = Get-SetupIds $Config
    @{ account = $ids.Account.Split('/')[-1]; project = $ids.Project.Split('/')[-1] }
}
function Get-CollectionMetadata([string]$Id) {
    $items = Get-SetupCollection $Id
    return ,@($items | ForEach-Object { ConvertTo-Semantic $_ } | Sort-Object id)
}
function Get-CurrentState {
    param([string[]]$ResourceIds, [string[]]$Collections = @())
    $state = @{ resources = @{}; collections = @{} }
    foreach ($id in ($ResourceIds | Sort-Object -Unique)) {
        $value = Get-SetupResource $id -Optional
        $state.resources[$id] = if ($value) { ConvertTo-Semantic $value } else { 'Absent' }
        if ($value -and $id -match '/Microsoft.Network/virtualNetworks/[^/]+$') {
            foreach ($subnet in $value.properties.subnets) {
                foreach ($key in @('networkSecurityGroup','routeTable')) {
                    if ($subnet.properties.Contains($key) -and $subnet.properties[$key]) {
                        $reference = $subnet.properties[$key].id
                        if (!$state.resources.Contains($reference)) { $state.resources[$reference] = ConvertTo-Semantic (Get-SetupResource $reference) }
                    }
                }
            }
        }
        if ($value -and $id -match '/subnets/[^/]+$') {
            foreach ($key in @('networkSecurityGroup','routeTable')) {
                if ($value.properties.Contains($key) -and $value.properties[$key]) {
                    $reference = $value.properties[$key].id
                    if (!$state.resources.Contains($reference)) { $state.resources[$reference] = ConvertTo-Semantic (Get-SetupResource $reference) }
                }
            }
        }
    }
    foreach ($id in $Collections) { $state.collections[$id] = Get-CollectionMetadata $id }
    return $state
}
function Get-FoundryState {
    param($Config)
    $ids = Get-SetupIds $Config
    $account = Get-SetupResource $ids.Account
    $project = Get-SetupResource $ids.Project
    if ($account.kind -ne 'AIServices' -or $account.location -ine $Config.location -or $project.location -ine $Config.location) {
        throw 'Unsupported Foundry kind/region.'
    }
    foreach ($item in @($account,$project)) {
        if ($item.properties.provisioningState -ne 'Succeeded' -or $item.identity.type -ne 'SystemAssigned' -or
            ![guid]::TryParse($item.identity.principalId,[ref]([guid]::Empty)) -or !$item.properties.internalId) {
            throw 'Succeeded resources with existing system identities/internal IDs are required; no identity conversion.'
        }
    }
    if ($account.properties.Contains('encryption') -and $account.properties.encryption -and
        $account.properties.encryption.keySource -ne 'Microsoft.CognitiveServices') { throw 'CMK migration is out of scope.' }
    $projects = Get-SetupCollection "$($ids.Account)/projects"
    if ($projects.Count -ne 1 -or $projects[0].id -ine $ids.Project) { throw 'Only the exact paired single-project account is supported.' }
    Get-CurrentState @($ids.Account,$ids.Project) @("$($ids.Account)/projects","$($ids.Account)/deployments",
        "$($ids.Account)/connections","$($ids.Project)/connections")
}
function Assert-ObservedDependencies($Config,$State) {
    $ids = Get-SetupIds $Config
    $storage = $State.resources[$ids.Storage]
    if ($storage -ne 'Absent' -and ($storage.kind -cne 'StorageV2' -or !$storage.properties.primaryEndpoints.blob)) { throw 'Azure GPv2 StorageV2 with a blob endpoint is required.' }
    if ($storage -ne 'Absent' -and (Get-SetupResource $ids.Storage).properties.provisioningState -ne 'Succeeded') { throw 'Await Storage Succeeded before consuming its blob endpoint.' }
    $vnet = $State.resources[$ids.Vnet]
    if ($vnet -ne 'Absent' -and $vnet.location -ine $Config.location) { throw 'VNet/account regions differ.' }
    $agent = $State.resources[$ids.AgentSubnet]
    $pe = $State.resources[$ids.PeSubnet]
    if ($agent -ne 'Absent') {
        $delegations = @($agent.properties.delegations | Where-Object { $_.properties.serviceName -eq 'Microsoft.App/environments' })
        if ($delegations.Count -ne 1 -or @($agent.properties.delegations).Count -ne 1) { throw 'Exact agent delegation required; no subnet repair.' }
        $range = Get-CidrRange $agent.properties.addressPrefix
        Assert-PrivateCidr $range
        if ($range.Prefix -gt 26) { throw 'Agent subnet is too small.' }
        if ($Config.network.mode -eq 'create' -and $agent.properties.addressPrefix -cne $Config.network.agentSubnetPrefix) { throw 'Created agent CIDR differs from intake.' }
    }
    if ($pe -ne 'Absent') {
        if ($pe.properties.Contains('delegations') -and @($pe.properties.delegations).Count) { throw 'Delegated PE subnet is unsupported.' }
        $range = Get-CidrRange $pe.properties.addressPrefix
        Assert-PrivateCidr $range
        if ($range.Prefix -gt 28) { throw 'PE subnet is too small.' }
        if ($Config.network.mode -eq 'create' -and $pe.properties.addressPrefix -cne $Config.network.privateEndpointSubnetPrefix) { throw 'Created PE CIDR differs from intake.' }
    }
}
function Get-CompatibleConnection($Config,[string]$Kind) {
    $ids = Get-SetupIds $Config
    if ($Kind -eq 'monitoring' -and !$ids.Insights) { return $null }
    $wanted = if ($Kind -eq 'storage') { $ids.Storage } else { $ids.Insights }
    $selected = if ($Config.Contains('connectionSelection') -and $Config.connectionSelection.Contains($Kind)) { $Config.connectionSelection[$Kind] } else { '' }
    # Exact GETs only: account-level listings can project the same project connection under another ID.
    $id = if ($selected) { $selected } elseif ($Kind -eq 'storage') { "$($ids.Project)/connections/dataset-storage" } else { "$($ids.Account)/connections/monitoring" }
    $connection = Get-SetupResource $id -Optional
    if (!$connection) {
        if ($selected) { throw 'Selected connection was not found.' }
        return $null
    }
    $p = $connection.properties
    $expectedTarget = if ($Kind -eq 'storage') { (Get-SetupResource $ids.Storage).properties.primaryEndpoints.blob } else { $ids.Insights }
    $expectedCategory = if ($Kind -eq 'storage') { 'AzureStorageAccount' } else { 'AppInsights' }
    $expectedAuth = if ($Kind -eq 'storage') { 'AAD' } else { 'ApiKey' }
    if ($p.category -cne $expectedCategory -or $p.authType -cne $expectedAuth -or
        $p.metadata.ResourceId -ine $wanted -or $p.target.TrimEnd('/') -ine $expectedTarget.TrimEnd('/') -or
        ($Kind -eq 'monitoring' -and (!$p.Contains('isSharedToAll') -or !$p.isSharedToAll))) { throw 'Existing connection is incompatible; do not overwrite it.' }
    return ConvertTo-Semantic $connection
}
function Get-Injection($Account, [string]$Subnet) {
    [array]$all = @()
    if ($Account.properties.Contains('networkInjections') -and $Account.properties.networkInjections) { $all = @($Account.properties.networkInjections) }
    $agent = @($all | Where-Object { $_.scenario -eq 'agent' })
    if ($agent.Count) {
        if ($agent.Count -ne 1 -or $agent[0].subnetArmId -ine $Subnet -or $agent[0].useMicrosoftManagedNetwork -ne $false) {
            throw 'Existing agent injection requires migration; it is not overwritten.'
        }
        return $null
    }
    return @{ properties = @{ networkInjections = @($all) + @(@{ scenario = 'agent'; subnetArmId = $Subnet; useMicrosoftManagedNetwork = $false }) } }
}
function Assert-MatchingHost($HostResource, [string]$Parent, [string]$Subnet = '') {
    if (($HostResource.id -replace '/capabilityHosts/[^/]+$','') -ine $Parent -or
        $HostResource.properties.capabilityHostKind -ne 'Agents') { throw 'Host parent/kind mismatch.' }
    foreach ($key in @('storageConnections','threadStorageConnections','vectorStoreConnections','aiServicesConnections')) {
        if ($HostResource.properties.Contains($key) -and $HostResource.properties[$key]) { throw 'BYO backend migration is out of scope.' }
    }
    if ($Subnet -and $HostResource.properties.customerSubnet -ine $Subnet) { throw 'Host subnet mismatch.' }
    if ($HostResource.properties.provisioningState -in @('Failed','Canceled','Deleting')) { throw 'Host is unsuccessful; no overwrite or delete.' }
}
function Get-Host([string]$Parent, [string]$Subnet = '') {
    $items = Get-SetupCollection "$Parent/capabilityHosts"
    if ($items.Count -gt 1) { throw 'Multiple hosts require review.' }
    if ($items.Count) { Assert-MatchingHost $items[0] $Parent $Subnet; return $items[0] }
    return $null
}

function Get-Inspection {
    param($Config)
    $ids = Get-SetupIds $Config
    $resources = @($ids.ResourceGroup,$ids.Account,$ids.Project,$ids.Storage,$ids.Vnet,$ids.AgentSubnet,$ids.PeSubnet)
    if ($ids.Insights) { $resources += $ids.Insights }
    $state = Get-CurrentState $resources
    Assert-ObservedDependencies $Config $state
    $foundry = $null
    $endpoint = $null
    if ($state.resources[$ids.Account] -ne 'Absent' -and $state.resources[$ids.Project] -ne 'Absent') {
        $foundry = Get-FoundryState $Config
        $project = Get-SetupResource $ids.Project
        $endpoint = $project.properties.endpoints['AI Foundry API']
    } elseif ($Config.foundryAccount.mode -eq 'existing') { throw 'Supplied Foundry resources are missing; no new resources substituted.' }
    if ($ids.Insights -and $state.resources[$ids.Insights] -ne 'Absent') {
        $workspaceId = Assert-ResourceId (Get-SetupResource $ids.Insights).properties.WorkspaceResourceId 'Microsoft.OperationalInsights/workspaces'
        $state.resources[$workspaceId] = ConvertTo-Semantic (Get-SetupResource $workspaceId)
    }
    @{ configHash = (Get-Digest $Config); state = $state; foundry = $foundry; projectEndpoint = $endpoint
        coverage = @{ configuration = 'Partial'; effectiveAccess = 'NotAssessed'; actualServingRoute = 'NotVerified' } }
}
