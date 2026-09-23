# The CLI's JMESPath projection and this in-process projection feed the same
# allowlisted metadata shape. This second boundary also strips unexpected nested fields.
function Copy-MetadataFields {
    param($Source, [string[]]$Fields)
    $result = [hashtable]::new([StringComparer]::Ordinal)
    foreach ($field in $Fields) {
        $result[$field] = $(if ($Source -is [Collections.IDictionary] -and $field -cin @($Source.Keys)) { $Source[$field] } else { $null })
    }
    return $result
}

function Copy-ApprovedMetadataTree {
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [Collections.IDictionary]) {
        $allowed = @(
            'id','name','type','properties','principalId','clientId','tenantId',
            'actions','notActions','dataActions','notDataActions',
            'status','groupIds','privateLinkServiceId','privateLinkServiceConnectionState',
            'privateEndpoint','subnet','privateIPAddress','privateIPAllocationMethod',
            'privateLinkConnectionProperties','fqdns','groupId','requiredMemberName',
            'serviceName','linkedResourceType','allowDelete','link','provisioningState',
            'dnsServers','addressPrefixes','addressPrefix','fqdn','ipAddresses',
            'privateDnsZoneId','recordSets','recordType','recordSetName','ttl','ipv4Address',
            'priority','direction','access','protocol','sourceAddressPrefix','sourceAddressPrefixes',
            'destinationAddressPrefix','destinationAddressPrefixes','sourcePortRange','sourcePortRanges',
            'destinationPortRange','destinationPortRanges','nextHopType','nextHopIpAddress',
            'scenario','subnetArmId','useMicrosoftManagedNetwork'
        )
        $result = [hashtable]::new([StringComparer]::Ordinal)
        foreach ($key in $Value.Keys) {
            if ($key -cin $allowed) { $result[$key] = Copy-ApprovedMetadataTree $Value[$key] }
        }
        return $result
    }
    if ($Value -is [Collections.IList]) {
        $items = @($Value | ForEach-Object { Copy-ApprovedMetadataTree $_ })
        return ,$items
    }
    return $Value
}

function ConvertTo-ArmMetadataItem {
    param($Item, [string]$Kind)
    if ($Item -isnot [Collections.IDictionary]) { throw 'InvalidMetadataItem' }
    $output = Copy-MetadataFields $Item @('id','name','type','location')
    $output.identity = Copy-MetadataFields $Item.identity @('type','principalId','tenantId')
    $identities = $null
    if ($Item.identity.userAssignedIdentities -is [Collections.IDictionary]) {
        $identities = @{}
        foreach ($id in $Item.identity.userAssignedIdentities.Keys) {
            if ($id -match '^/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/Microsoft.ManagedIdentity/userAssignedIdentities/[^/?#]+$') {
                $identities[$id] = Copy-MetadataFields $Item.identity.userAssignedIdentities[$id] @('principalId','clientId')
            }
        }
    }
    $output.identity.userAssignedIdentities = $identities
    $p = $Item.properties
    if ($p -isnot [Collections.IDictionary]) { $output.properties = $null; return $output }
    $fields = switch ($Kind) {
        Connection { @('category','authType','target','isSharedToAll','provisioningState') }
        Authorization { @('principalId','principalType','roleDefinitionId','scope','createdOn','updatedOn','permissions','principals','excludePrincipals','doNotApplyToChildScopes') }
        Role { @('roleName','type','permissions','assignableScopes') }
        Deployment { @('provisioningState') }
        Capability { @('provisioningState','capabilityHostKind','storageConnections','vectorStoreConnections','threadStorageConnections') }
        PrivateConnection { @('privateEndpoint','privateLinkServiceConnectionState','groupIds','provisioningState') }
        Storage { @('provisioningState','publicNetworkAccess','allowSharedKeyAccess') }
        Monitoring { @('provisioningState','AppId','WorkspaceResourceId','publicNetworkAccessForIngestion','publicNetworkAccessForQuery') }
        Network { @('provisioningState','subnet','delegations','serviceAssociationLinks','networkSecurityGroup','routeTable','dhcpOptions','addressSpace','addressPrefix','addressPrefixes','networkInterfaces','ipConfigurations','customDnsConfigs','privateLinkServiceConnections','manualPrivateLinkServiceConnections','privateDnsZoneConfigs','aRecords','virtualNetwork','virtualNetworkLinkState','registrationEnabled','securityRules','routes') }
        default { @('provisioningState','endpoint','endpoints','networkInjections','publicNetworkAccess','disableLocalAuth','documentEndpoint') }
    }
    $properties = Copy-MetadataFields $p $fields
    foreach ($field in $fields) {
        if ($field -eq 'endpoints' -and $p[$field] -is [Collections.IDictionary]) {
            $properties[$field] = @{}
            foreach ($key in $p[$field].Keys) {
                # Endpoint names are service-defined map keys; values must be HTTPS
                # endpoint metadata, never a query-bearing credential or connection string.
                $endpoint = $null
                if ($p[$field][$key] -is [string] -and [uri]::TryCreate($p[$field][$key], [UriKind]::Absolute, [ref]$endpoint) -and
                    $endpoint.Scheme -eq 'https' -and !$endpoint.UserInfo -and !$endpoint.Query -and !$endpoint.Fragment) {
                    $properties[$field][$key] = $p[$field][$key]
                }
            }
        }
        else { $properties[$field] = Copy-ApprovedMetadataTree $p[$field] }
    }
    switch ($Kind) {
        Connection { $properties.metadata = Copy-MetadataFields $p.metadata @('ResourceId','resourceId') }
        Authorization {
            $properties.conditionPresent = if ($p.Contains('condition')) {
                $null -ne $p.condition -and $p.condition -cne ''
            } else { $p.conditionPresent -eq $true }
        }
        Deployment { $properties.model = Copy-MetadataFields $p.model @('name','format','version') }
        Storage {
            $properties.networkAcls = Copy-MetadataFields $p.networkAcls @('defaultAction','bypass')
            $properties.primaryEndpoints = Copy-MetadataFields $p.primaryEndpoints @('blob')
        }
        Monitoring {
            $properties.features = Copy-MetadataFields $p.features @('enableLogAccessUsingOnlyResourcePermissions')
            $links = if ($p['PrivateLinkScopedResources']) { $p['PrivateLinkScopedResources'] } else { $p['privateLinkScopedResources'] }
            $properties.privateLinkScopedResources = @($links | Where-Object { $_ } | ForEach-Object {
                @{ resourceId = $(if ($_['ResourceId']) { $_['ResourceId'] } else { $_['resourceId'] })
                    scopeId = $(if ($_['ScopeId']) { $_['ScopeId'] } else { $_['scopeId'] }) }
            })
        }
    }
    $output.properties = $properties
    return $output
}

function ConvertTo-ArmMetadata {
    param($Data, [string]$Kind, [bool]$Collection)
    if ($Data -isnot [Collections.IDictionary]) { throw 'InvalidMetadataShape' }
    if (!$Collection) { return (ConvertTo-ArmMetadataItem $Data $Kind) }
    if (!$Data.Contains('value') -or $Data.value -isnot [Collections.IList]) { throw 'InvalidCollectionShape' }
    $items = @($Data.value | ForEach-Object { ConvertTo-ArmMetadataItem $_ $Kind })
    return @{ value = $items; nextLink = $Data.nextLink }
}
