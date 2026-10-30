function Get-NetworkObservation($Config) {
    $ids = Get-SetupIds $Config
    Get-CurrentState @($ids.Vnet,$ids.AgentSubnet,$ids.PeSubnet)
}
function Get-DeploymentState($Config,$Request) {
    $ids = Get-SetupIds $Config
    $material = @{ resources = @{}; prerequisites = @{} }; $observed = @{}
    $asset = $Request.asset
    $rg = Get-SetupResource $Request.scope
    $material.prerequisites[$Request.scope] = @{ id = $rg.id }
    $target = switch ($asset) {
        'account' { $ids.Account }; 'project' { $ids.Project }; 'storage' { $ids.Storage }; 'network' { $ids.Vnet }
    }
    $writeIds = @($Request.observedIds)
    if ($target) { $writeIds += $target }
    foreach ($id in ($writeIds | Sort-Object -Unique)) {
        $resource = Get-SetupResource $id -Optional
        $material.resources[$id] = if ($resource) { ConvertTo-Semantic $resource } else { 'Absent' }
    }
    if ($asset -in @('workspace','monitoring')) {
        $cfg = $Config.applicationInsights
        $workspace = $cfg.logAnalyticsWorkspace
        $workspaceId = if ($workspace.mode -eq 'existing') { $workspace.resourceId } else { "$($ids.ResourceGroup)/providers/Microsoft.OperationalInsights/workspaces/$($workspace.name)" }
        $law = Get-SetupResource $workspaceId -Optional
        $material.prerequisites[$workspaceId] = if ($law) { ConvertTo-Semantic $law } else { 'Absent' }
        if ($asset -eq 'monitoring') {
            $component = Get-SetupResource $ids.Insights -Optional
            $material.resources[$ids.Insights] = if ($component) { ConvertTo-Semantic $component } else { 'Absent' }
        }
    }
    if ($asset -eq 'project') {
        $account = Get-SetupResource $ids.Account
        if ($account.properties.provisioningState -ne 'Succeeded' -or $account.kind -ne 'AIServices') { throw 'Project requires its Succeeded account.' }
        $material.prerequisites[$ids.Account] = ConvertTo-Semantic $account
        $material.projects = Get-CollectionMetadata "$($ids.Account)/projects"
    }
    if ($asset -eq 'connections') {
        $material.foundry = Get-FoundryState $Config
        if ((Get-SetupResource $ids.Storage).properties.provisioningState -ne 'Succeeded') { throw 'Await Storage Succeeded before consuming its endpoint.' }
        foreach ($id in @($ids.Storage,$ids.Insights) | Where-Object { $_ }) {
            $material.prerequisites[$id] = ConvertTo-Semantic (Get-SetupResource $id)
        }
    }
    if ($asset -in @('connectivity','monitor-connectivity')) {
        $network = Get-NetworkObservation $Config
        $vnet = $network.resources[$ids.Vnet]; $subnet = $network.resources[$ids.PeSubnet]
        if ($vnet -eq 'Absent' -or $subnet -eq 'Absent' -or $vnet.location -ine $Config.location) { throw 'Selected network/subnet unavailable or wrong region.' }
        if ($subnet.properties.Contains('delegations') -and @($subnet.properties.delegations).Count) { throw 'PE subnet is delegated; no repair.' }
        $range = Get-CidrRange $subnet.properties.addressPrefix; Assert-PrivateCidr $range
        if ($range.Prefix -gt 28) { throw 'PE subnet is too small.' }
        $material.prerequisites[$ids.Vnet] = @{ id = $vnet.id; location = $vnet.location }
        $material.prerequisites[$ids.PeSubnet] = @{ id = $subnet.id; addressPrefix = $subnet.properties.addressPrefix
            delegations = @($subnet.properties['delegations']); privateEndpointNetworkPolicies = $subnet.properties['privateEndpointNetworkPolicies'] }
        $observed.networkPolicies = $network
        $values = @{}; foreach ($key in $Request.parameters.Keys) { $values[$key] = $Request.parameters[$key].value }
        $targets = if ($asset -eq 'connectivity') { @($values.targetId) } else { @($values.insightsId,$values.workspaceId,$values.scopeId) }
        foreach ($id in $targets) {
            $resource = Get-SetupResource $id -Optional
            if (!$resource -and $id -ne $values['scopeId']) { throw 'Private endpoint target is missing.' }
            if ($resource -and $resource.properties.Contains('provisioningState') -and $resource.properties.provisioningState -ne 'Succeeded') { throw 'Private endpoint target is not yet Succeeded.' }
            $material.prerequisites[$id] = if (!$resource) { 'Absent' } elseif ($id -ieq $ids.Account) {
                @{ id = $resource.id; location = $resource.location; kind = $resource.kind; identity = $resource.identity
                    publicNetworkAccess = $resource.properties.publicNetworkAccess }
            } else { ConvertTo-Semantic $resource }
        }
    }
    @{ material = $material; observations = $observed }
}
function Assert-OperationCurrent($Plan,$Current,$Attempt) {
    $Attempt.receipt.observedChanges = @(Get-SemanticDiff $Plan.observed $Current.observations)
    $Attempt.receipt.observedChangesMeaning = 'Reported only; no policy change, exemption, resource adoption or global baseline update.'
    Write-Json $Attempt.path $Attempt.receipt
    Assert-NoDrift $Plan $Current.material $Attempt
}
