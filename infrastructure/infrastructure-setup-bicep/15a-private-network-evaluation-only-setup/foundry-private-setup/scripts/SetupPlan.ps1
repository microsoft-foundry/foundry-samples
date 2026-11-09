. (Join-Path $PSScriptRoot 'Inspection.ps1')

function Read-SetupInput([string]$Path) {
    $split = Split-SetupInput (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable)
    $config = Assert-SetupConfig $split.config
    @{ config = $config; options = (Complete-IntegrationOptions $split.networking $config) }
}
function Complete-IntegrationOptions($Networking,$Config) {
    Assert-Fields $Networking @() @('dnsZones','privateEndpoints','monitorPrivateLink')
    $options = Copy-Data $Networking
    $monitoring = $Config.applicationInsights.mode -ne 'none'
    $zones = @('privatelink.services.ai.azure.com','privatelink.openai.azure.com','privatelink.cognitiveservices.azure.com','privatelink.blob.core.windows.net')
    $endpoints = @('pe-foundry','pe-storage')
    if ($monitoring) {
        $zones += @('privatelink.monitor.azure.com','privatelink.oms.opinsights.azure.com','privatelink.ods.opinsights.azure.com','privatelink.agentsvc.azure-automation.net')
        $endpoints += 'pe-monitor'
        if (!$options.Contains('monitorPrivateLink')) { $options.monitorPrivateLink = @{ mode = 'create'; name = "ampls-$((Get-Names $Config).account)" } }
    }
    foreach ($section in @(@('dnsZones',$zones),@('privateEndpoints',$endpoints))) {
        if (!$options.Contains($section[0])) { $options[$section[0]] = @{} }
        if ($options[$section[0]] -isnot [Collections.IDictionary]) { throw "privateNetworking.$($section[0]) must be an object." }
        foreach ($key in $section[1]) { if (!$options[$section[0]].Contains($key)) { $options[$section[0]][$key] = @{ mode = 'create' } } }
    }
    Assert-IntegrationOptions $options $Config
}
function Assert-IntegrationOptions($options,$Config) {
    Assert-Fields $options @('dnsZones','privateEndpoints') @('monitorPrivateLink')
    $zones = @('privatelink.services.ai.azure.com','privatelink.openai.azure.com','privatelink.cognitiveservices.azure.com','privatelink.blob.core.windows.net')
    $endpoints = @('pe-foundry','pe-storage')
    if ($Config.applicationInsights.mode -ne 'none') {
        $zones += @('privatelink.monitor.azure.com','privatelink.oms.opinsights.azure.com','privatelink.ods.opinsights.azure.com','privatelink.agentsvc.azure-automation.net')
        $endpoints += 'pe-monitor'
        if (!$options.Contains('monitorPrivateLink')) { throw 'Monitoring requires explicit AMPLS create/existing options.' }
    } elseif ($options.Contains('monitorPrivateLink')) { throw 'Monitoring-none must use matching no-monitoring options.' }
    Assert-Fields $options.dnsZones $zones
    Assert-Fields $options.privateEndpoints $endpoints
    foreach ($value in $options.dnsZones.Values) {
        if ($value.mode -eq 'create') { Assert-Fields $value @('mode') }
        elseif ($value.mode -eq 'existing') {
            Assert-Fields $value @('mode','resourceId') @('linkVnet')
            $null = Assert-ResourceId $value.resourceId 'Microsoft.Network/privateDnsZones'
            if ($value.Contains('linkVnet') -and $value.linkVnet -isnot [bool]) { throw 'linkVnet must be an explicit boolean.' }
        } else { throw 'Unsupported DNS mode.' }
    }
    foreach ($value in $options.privateEndpoints.Values) {
        if ($value.mode -eq 'create') { Assert-Fields $value @('mode') }
        elseif ($value.mode -eq 'existing') {
            Assert-Fields $value @('mode','resourceId') @('addDnsZoneGroup')
            $null = Assert-ResourceId $value.resourceId 'Microsoft.Network/privateEndpoints'
            if ($value.Contains('addDnsZoneGroup') -and $value.addDnsZoneGroup -isnot [bool]) { throw 'addDnsZoneGroup must be boolean.' }
        } else { throw 'Unsupported PE mode.' }
    }
    if ($options.Contains('monitorPrivateLink')) {
        if ($options.monitorPrivateLink.mode -eq 'create') { Assert-Fields $options.monitorPrivateLink @('mode','name'); Assert-Name $options.monitorPrivateLink.name '^[a-zA-Z0-9][a-zA-Z0-9_.-]+$' 2 80 }
        elseif ($options.monitorPrivateLink.mode -eq 'existing') { Assert-Fields $options.monitorPrivateLink @('mode','resourceId'); $null = Assert-ResourceId $options.monitorPrivateLink.resourceId 'Microsoft.Insights/privateLinkScopes' }
        else { throw 'Unsupported AMPLS mode.' }
    }
    return $options
}
function New-SetupPlan($Config,$Options) {
    $ids = Get-SetupIds $Config
    $nodes = [Collections.Generic.List[object]]::new()
    function Add-Node($Id,$Kind,$Depends,$Writes,$Values = @{},$Asset = '') {
        $nodes.Add(@{ id = $Id; kind = $Kind; dependsOn = @($Depends); writeScopes = @($Writes | Sort-Object -Unique)
            values = $Values; asset = $Asset; budgetSeconds = 1200 })
    }
    Add-Node 'ResourceGroup' 'ResourceGroup' @() @($ids.ResourceGroup)
    foreach ($pair in @(@('Network',$Config.network,$ids.Vnet,'network'),@('Storage',$Config.storageAccount,$ids.Storage,'storage'),
        @('Account',$Config.foundryAccount,$ids.Account,'account'))) {
        $kind = if ($pair[1].mode -eq 'create') { 'Deployment' } else { 'Reference' }
        Add-Node $pair[0] $kind @('ResourceGroup') $(if ($kind -eq 'Deployment') { @($pair[2]) } else { @() }) @{ location = $Config.location; config = $pair[1] } $pair[3]
    }
    $projectKind = if ($Config.foundryProject.mode -eq 'create') { 'Deployment' } else { 'Reference' }
    Add-Node 'Project' $projectKind @('Account') $(if ($projectKind -eq 'Deployment') { @($ids.Project) } else { @() }) @{
        location = $Config.location; accountName = (Get-Names $Config).account; config = $Config.foundryProject } 'project'
    $monitoring = $Config.applicationInsights.mode -ne 'none'
    if ($monitoring) {
        $kind = if ($Config.applicationInsights.mode -eq 'create') { 'Deployment' } else { 'Reference' }
        $writes = @($ids.Insights)
        if ($kind -eq 'Deployment' -and $Config.applicationInsights.logAnalyticsWorkspace.mode -eq 'create') {
            $writes += "$($ids.ResourceGroup)/providers/Microsoft.OperationalInsights/workspaces/$($Config.applicationInsights.logAnalyticsWorkspace.name)"
        }
        Add-Node 'Monitoring' $kind @('ResourceGroup') $(if ($kind -eq 'Deployment') { $writes } else { @() }) @{
            location = $Config.location; config = $Config.applicationInsights } 'monitoring'
    }
    foreach ($target in @('Foundry','Storage','Monitor')) {
        if ($target -eq 'Monitor' -and !$monitoring) { continue }
        $peKey = 'pe-' + $target.ToLowerInvariant(); $choice = $Options.privateEndpoints[$peKey]
        $zoneNames = switch ($target) {
            'Foundry' { @('privatelink.services.ai.azure.com','privatelink.openai.azure.com','privatelink.cognitiveservices.azure.com') }
            'Storage' { @('privatelink.blob.core.windows.net') }
            'Monitor' { @('privatelink.monitor.azure.com','privatelink.oms.opinsights.azure.com','privatelink.ods.opinsights.azure.com','privatelink.agentsvc.azure-automation.net') }
        }
        $zoneValues = @()
        foreach ($name in $zoneNames) {
            $zone = $Options.dnsZones[$name]
            $zoneId = if ($zone.mode -eq 'create') { "$($ids.ResourceGroup)/providers/Microsoft.Network/privateDnsZones/$name" } else { $zone.resourceId }
            $zoneValues += @{ name = $name; resourceId = $zoneId; deployZone = ($zone.mode -eq 'create')
                deployLink = ($zone.mode -eq 'create' -or ($zone.Contains('linkVnet') -and $zone.linkVnet)) }
        }
        $isNew = $choice.mode -eq 'create'
        $peId = if ($isNew) { "$($ids.ResourceGroup)/providers/Microsoft.Network/privateEndpoints/$peKey" } else { $choice.resourceId }
        $values = @{ location = $Config.location; vnetId = $ids.Vnet; subnetId = $ids.PeSubnet; peName = $peId.Split('/')[-1]
            zones = $zoneValues; deployEndpoint = $isNew; deployZoneGroup = ($isNew -or ($choice.Contains('addDnsZoneGroup') -and $choice.addDnsZoneGroup))
            existingEndpointResourceId = $(if ($isNew) { '' } else { $peId }) }
        $targetId = if ($target -eq 'Foundry') { $ids.Account } else { $ids.Storage }
        $dependency = if ($target -eq 'Foundry') { 'Account' } elseif ($target -eq 'Storage') { 'Storage' } else { 'Monitoring' }
        $asset = 'connectivity'
        $writes = @($ids.PeSubnet,$peId) + @($zoneValues | Where-Object { $_.deployZone -or $_.deployLink } | ForEach-Object resourceId)
        if ($target -eq 'Monitor') {
            $asset = 'monitor-connectivity'
            $scope = $Options.monitorPrivateLink
            $values.scopeId = if ($scope.mode -eq 'create') { "$($ids.ResourceGroup)/providers/Microsoft.Insights/privateLinkScopes/$($scope.name)" } else { $scope.resourceId }
            $values.deployScope = $scope.mode -eq 'create'; $values.insightsId = $ids.Insights
            $values.workspaceId = ''; $values.deployInsightsAssociation = $true; $values.deployWorkspaceAssociation = $true
            $writes += @($values.scopeId,$ids.Insights,"linked-workspace-of:$($ids.Insights)")
        } else {
            $values.targetId = $targetId; $values.groupId = $(if ($target -eq 'Foundry') { 'account' } else { 'blob' })
            $writes += $targetId
        }
        Add-Node "${target}Connectivity" 'Deployment' @('Network',$dependency) $writes $values $asset
    }
    $connectionDeps = @('Project','Storage')
    if ($monitoring) { $connectionDeps += 'Monitoring' }
    Add-Node 'Connections' 'Connections' $connectionDeps @($ids.Account,$ids.Project) @{
        accountName = (Get-Names $Config).account; projectName = (Get-Names $Config).project
        storageResourceId = $ids.Storage; applicationInsightsResourceId = $ids.Insights
        deployStorageConnection = $true; deployMonitoringConnection = $monitoring } 'connections'
    $grants = @('Account','Storage')
    if ($monitoring) { $grants += @('Insights','Workspace') }
    foreach ($grant in $grants) {
        $dependency = if ($grant -in @('Insights','Workspace')) { 'Monitoring' } else { $grant }
        $targetScope = switch ($grant) { 'Account' { $ids.Account }; 'Storage' { $ids.Storage }; 'Insights' { $ids.Insights }; 'Workspace' { "linked-workspace-of:$($ids.Insights)" } }
        Add-Node "Grant$grant" 'Grant' @('Project',$dependency) @($ids.Account,$ids.Project,$targetScope) @{ target = $grant }
    }
    $injectDeps = @('Project','Network','Connections','FoundryConnectivity','StorageConnectivity') + @($grants | ForEach-Object { "Grant$_" })
    if ($monitoring) { $injectDeps += 'MonitorConnectivity' }
    Add-Node 'Injection' 'Foundry' $injectDeps @($ids.Account,$ids.AgentSubnet) @{ operation = 'Injection' }
    Add-Node 'AccountHost' 'Foundry' @('Injection') @($ids.Account,$ids.AgentSubnet) @{ operation = 'AccountHost' }
    if ($Config.workload.projectHost -eq 'requested') { Add-Node 'ProjectHost' 'Foundry' @('AccountHost') @($ids.Account,$ids.Project) @{ operation = 'ProjectHost' } }
    $packageFiles = Get-PackageFileHashes
    $plan = @{ schemaVersion = '1.0'; config = $Config; options = $Options; packageHash = (Get-Digest $packageFiles); packageFiles = $packageFiles; nodes = @($nodes.ToArray()) }
    $plan.planHash = Get-Digest $plan
    return $plan
}
function Assert-SetupPlan($Plan) {
    $null = Assert-SetupConfig $Plan.config
    $null = Assert-IntegrationOptions $Plan.options $Plan.config
    $copy = Copy-Data $Plan; $copy.Remove('planHash')
    if ((Get-Digest $copy) -cne $Plan.planHash) { throw 'The plan file was edited after Plan generated it. Run Plan again; never edit plan.json by hand.' }
    if ($Plan.packageHash -cne (Get-PackageHash)) {
        $changes = if ($Plan.Contains('packageFiles')) { Get-PackageChangeSummary $Plan.packageFiles } else { '' }
        throw "Package files differ from when this plan was generated$(if ($changes) { " ($changes)" }). Keep plan.json and the state directory outside the extracted package folder, re-extract the package unchanged if needed, then run Plan again."
    }
    $expected = New-SetupPlan $Plan.config $Plan.options
    if ($expected.planHash -cne $Plan.planHash) { throw 'Only the deterministic generated setup DAG is supported.' }
}
function Resolve-NodeValues($Graph,$Node) {
    $values = Copy-Data $Node.values; $config = $Graph.config; $ids = Get-SetupIds $config
    if ($Node.asset -eq 'monitor-connectivity') {
        $component = Get-SetupResource $ids.Insights
        $values.workspaceId = Assert-ResourceId $component.properties.WorkspaceResourceId 'Microsoft.OperationalInsights/workspaces'
        $scope = Get-SetupResource $values.scopeId -Optional
        if ($scope) {
            $scoped = Get-SetupCollection "$($values.scopeId)/scopedResources"
            $values.deployInsightsAssociation = !@($scoped | Where-Object { $_.properties.linkedResourceId -ieq $ids.Insights }).Count
            $values.deployWorkspaceAssociation = !@($scoped | Where-Object { $_.properties.linkedResourceId -ieq $values.workspaceId }).Count
        }
    }
    if ($Node.kind -eq 'Connections') {
        foreach ($kind in @('storage','monitoring')) {
            if ($kind -eq 'monitoring' -and !$ids.Insights) { continue }
            $existing = Get-CompatibleConnection $config $kind
            if ($existing) {
                if ($kind -eq 'storage') { $values.deployStorageConnection = $false } else { $values.deployMonitoringConnection = $false }
            }
        }
    }
    return $values
}
