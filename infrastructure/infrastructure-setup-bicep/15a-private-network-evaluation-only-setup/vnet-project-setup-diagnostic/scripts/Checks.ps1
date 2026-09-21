function Add-Check {
    param(
        $Context, [string]$Id, [string]$Domain, [string]$Resource,
        [ValidateSet('Passed','Failed','Warning','Unknown','NotApplicable','Observed','NotAssessed')][string]$Status,
        [string]$Expected, $Observed, [bool]$Required = $true, [string]$Principal = '',
        [string]$Scenario = 'Core', [string[]]$Limitations = @(),
        [string]$Remediation = 'Review the cited metadata with the resource owner; do not change Azure state as part of this diagnostic.',
        [ValidateSet('Configuration','ObservedNetwork')][string]$EvidenceKind = 'Configuration',
        [ValidateSet('Finding','Inventory','Coverage')][string]$Classification = 'Finding'
    )
    if ($Classification -eq 'Coverage') {
        if ($Status -notin @('NotAssessed','NotApplicable')) { throw 'Coverage records must not claim a prerequisite result.' }
        $Required = $false
    }
    if ($Classification -eq 'Inventory') {
        $Required = $false
        if ($Status -eq 'Passed') { $Status = 'Observed' }
        if (@($Context.Checks | Where-Object {
            $_.classification -eq 'Inventory' -and $_.id -eq $Id -and $_.resource -eq $Resource -and $_.principal -eq $Principal
        }).Count) { return }
    }
    $Context.Checks.Add([ordered]@{
        id = $Id; domain = $Domain; scenario = $Scenario; required = $Required; classification = $Classification
        status = $Status; severity = $(if ($Status -eq 'Failed') {'Error'} elseif ($Status -in @('Unknown','Warning')) {'Warning'} else {'Info'})
        principal = $Principal; resource = $Resource; scope = $Resource
        expected = $Expected; observed = $Observed; evidenceKind = $EvidenceKind
        collectedAt = [DateTimeOffset]::UtcNow.ToString('o'); hostContext = $Context.HostContext
        limitations = $Limitations; remediation = $Remediation
    })
}

function Get-ReadStatus {
    param($Read, [switch]$Collection)
    if ($Read.Code -eq 200) { return 'Passed' }
    if ($Read.Code -eq 404 -and !$Collection) { return 'Failed' }
    return 'Unknown'
}

function Test-Provisioning {
    param($Context, [string]$Id, [string]$CheckId, [bool]$Required = $true)
    $read = Read-Arm $Context $Id
    $status = Get-ReadStatus $read
    $observed = @{ readStatus = $read.Code; reason = $read.Reason }
    if ($read.Code -eq 200) {
        $state = $read.Data.properties.provisioningState
        $observed.state = $state
        $observed.location = $read.Data.location
        $status = if ($state -eq 'Succeeded') { 'Passed' } elseif ($state -in @('Failed','Canceled','Deleted')) { 'Failed' } else { 'Unknown' }
    }
    Add-Check $Context $CheckId 'Resource' $Id $status 'Resource exists and provisioningState is Succeeded' $observed -Required $Required `
        -Remediation 'Confirm the explicit resource ID and read access. For a proven failed provisioning state, have the resource owner inspect that resource operation; do not redeploy or warm resources during diagnosis.'
    return $read
}

function Get-Principal {
    param($Context, $Read, [string]$Id, [string]$Label)
    $principal = $Read.Data.identity.principalId
    $userAssigned = @()
    if ($Read.Data.identity.userAssignedIdentities) {
        foreach ($key in $Read.Data.identity.userAssignedIdentities.Keys) {
            $userAssigned += @{ resourceId = $key; principalId = $Read.Data.identity.userAssignedIdentities[$key].principalId }
        }
    }
    $status = if ($principal) { 'Passed' } else { 'Unknown' }
    Add-Check $Context "identity.$Label" 'Identity' $Id $status 'Identify the configured account/project dependency principal' @{
        type = $Read.Data.identity.type; principalId = $principal; userAssigned = $userAssigned
    } -Limitations @('A user-assigned identity is not automatically selected for dependency access; missing selection remains Unknown.')
    return [string]$principal
}

function Test-RolePermission {
    param($Role, [string]$Action, [ValidateSet('actions','dataActions')][string]$Kind)
    $exclude = if ($Kind -eq 'actions') { 'notActions' } else { 'notDataActions' }
    foreach ($block in @($Role.properties.permissions)) {
        $included = @($block[$Kind] | Where-Object { $Action -like $_ }).Count -gt 0
        $excluded = @($block[$exclude] | Where-Object { $Action -like $_ }).Count -gt 0
        if ($included -and !$excluded) { return $true }
    }
    return $false
}

function Get-AncestorScopes {
    param([string]$Id)
    $parts = $Id.Trim('/').Split('/')
    $scopes = [Collections.Generic.List[string]]::new()
    $scopes.Add("/$($parts[0])/$($parts[1])")
    if ($parts.Count -ge 4) { $scopes.Add('/' + ($parts[0..3] -join '/')) }
    for ($i = 7; $i -lt $parts.Count; $i += 2) { $scopes.Add('/' + ($parts[0..$i] -join '/')) }
    return $scopes.ToArray()
}

function Get-DenyRelevance {
    param($Deny, [string]$Scope, [string]$Principal, $Requirement)
    $p = $Deny.properties
    $denyScope = [string]$p.scope
    if (!$denyScope -and $Deny.id -match '^(.*)/providers/Microsoft.Authorization/denyAssignments/[^/]+$') {
        $denyScope = $Matches[1]
    }
    $result = @{
        id = $Deny.id; scope = $denyScope; relevant = $true; reasons = @()
        permissionKind = $Requirement.kind; matchingActions = @()
        principals = @($p.principals | ForEach-Object { @{ id = $_.id; type = $_.type } })
        excludedPrincipals = @($p.excludePrincipals | ForEach-Object { @{ id = $_.id; type = $_.type } })
        doNotApplyToChildScopes = $p.doNotApplyToChildScopes
        conditional = ([bool]$p.conditionPresent -or ![string]::IsNullOrWhiteSpace($p.condition))
    }
    $isAncestor = $denyScope -and ($denyScope -eq '/' -or $Scope -ieq $denyScope -or
        $Scope.StartsWith($denyScope.TrimEnd('/') + '/', [StringComparison]::OrdinalIgnoreCase))
    if ($denyScope -match '^/subscriptions/[0-9a-f-]{36}(/|$)' -and !$isAncestor) {
        $result.relevant = $false; $result.reasons = @('DisjointOrDescendantScope'); return $result
    }
    if ($isAncestor -and $Scope -ine $denyScope -and $p.doNotApplyToChildScopes -eq $true) {
        $result.relevant = $false; $result.reasons = @('DoesNotApplyToChildScopes'); return $result
    }
    if (!$isAncestor) { $result.reasons += 'ScopeInheritanceUnknown' }
    if (@($p.permissions).Count -and $null -ne $p.permissions) {
        $result.matchingActions = @($Requirement.values | Where-Object { Test-RolePermission $Deny $_ $Requirement.kind })
        if (!$result.matchingActions.Count) {
            $result.relevant = $false; $result.reasons = @('NoMatchingPermissionInSelectedChannel'); return $result
        }
    }
    else { $result.reasons += 'DenyPermissionsUnavailable' }
    $allPrincipals = '00000000-0000-0000-0000-000000000000'
    if (@($p.excludePrincipals | Where-Object { $_.id -eq $Principal -or ($_.id -eq $allPrincipals -and $_.type -eq 'SystemDefined') }).Count) {
        $result.relevant = $false; $result.reasons = @('PrincipalExplicitlyExcluded'); return $result
    }
    $direct = @($p.principals | Where-Object { $_.id -eq $Principal -or ($_.id -eq $allPrincipals -and $_.type -eq 'SystemDefined') })
    $ambiguous = @($p.principals | Where-Object { !$_.id -or $_.type -notin @('User','ServicePrincipal') })
    if (!$direct.Count -and @($p.principals).Count -and $null -ne $p.principals -and !$ambiguous.Count) {
        $result.relevant = $false; $result.reasons = @('DifferentExplicitPrincipals'); return $result
    }
    if (!$direct.Count) { $result.reasons += 'PrincipalOrGroupMembershipUnknown' }
    if (@($p.excludePrincipals | Where-Object { $_.type -notin @('User','ServicePrincipal') }).Count) {
        $result.reasons += 'ExcludedGroupMembershipUnknown'
    }
    if ($result.conditional) { $result.reasons += 'DenyConditionNotEvaluated' }
    if (!$result.reasons.Count) { $result.reasons = @('MatchingDenyRequiresEffectiveAuthorizationReview') }
    return $result
}

function Test-ConfiguredGrant {
    param($Context, [string]$Scope, [string]$Principal, $Requirement, [string]$CheckId, [string]$Scenario = 'Core', [string]$PrincipalSource = '', [bool]$Required = $true)
    $limitations = @($Requirement.limitation,
        'Configured grants only, not effective access. Group/PIM and management-group inheritance may not be visible; no identity was impersonated.',
        'Assignment timestamps are observations, not a promise about propagation or authorization caches.')
    if (!$Principal) {
        Add-Check $Context $CheckId 'RBAC' $Scope 'Unknown' 'Known intended principal and configured permission coverage' @{ reason = 'PrincipalNotSpecifiedOrUnresolved'; principalSource = $PrincipalSource } -Required $Required -Scenario $Scenario -Limitations $limitations
        return
    }
    $assignments = @{}
    $visibility = [Collections.Generic.List[object]]::new()
    $denyUncertain = $false
    $denyEvidence = @{}
    $unreadableDenyScopes = [Collections.Generic.List[string]]::new()
    foreach ($ancestor in @(Get-AncestorScopes $Scope)) {
        $roles = Read-Arm $Context "$ancestor/providers/Microsoft.Authorization/roleAssignments" -Collection
        $denies = Read-Arm $Context "$ancestor/providers/Microsoft.Authorization/denyAssignments" -Collection
        $visibility.Add(@{ scope = $ancestor; assignments = $roles.Code; denies = $denies.Code })
        if ($denies.Code -ne 200) {
            $denyUncertain = $true
            $unreadableDenyScopes.Add($ancestor)
        }
        else {
            $index = 0
            foreach ($deny in $denies.Data) {
                $key = if ($deny.id) { $deny.id } else { "$ancestor/unknown-deny-$index" }
                $denyEvidence[$key] = Get-DenyRelevance $deny $Scope $Principal $Requirement
                $index++
            }
        }
        if ($roles.Code -ne 200) { continue }
        foreach ($assignment in $roles.Data) {
            $p = $assignment.properties
            if ($p.principalId -ne $Principal -or !$p.scope) { continue }
            if ($Scope -ine $p.scope -and !$Scope.StartsWith($p.scope.TrimEnd('/') + '/', [StringComparison]::OrdinalIgnoreCase)) { continue }
            $assignments[$assignment.id] = $assignment
        }
    }
    $coverage = @{}
    $hints = [Collections.Generic.List[object]]::new()
    $conditionalCoverage = @{}
    $unreadableAllowDefinition = $false
    foreach ($assignment in $assignments.Values) {
        $p = $assignment.properties
        $role = Read-Arm $Context $p.roleDefinitionId
        $condition = [bool]$p.conditionPresent -or ![string]::IsNullOrWhiteSpace($p.condition)
        $hints.Add(@{
            assignmentId = $assignment.id; scope = $p.scope; roleDefinitionId = $p.roleDefinitionId
            roleName = $role.Data.properties.roleName; conditional = $condition
            createdOn = $p.createdOn; updatedOn = $p.updatedOn; definitionReadStatus = $role.Code
        })
        if ($role.Code -ne 200) { $unreadableAllowDefinition = $true; continue }
        foreach ($action in $Requirement.values) {
            if (Test-RolePermission $role.Data $action $Requirement.kind) {
                if ($condition) { $conditionalCoverage[$action] = $true } else { $coverage[$action] = $true }
            }
        }
    }
    $missing = @($Requirement.values | Where-Object { !$coverage.ContainsKey($_) })
    # Additional allow assignments cannot revoke a sufficient unconditional grant.
    $uncertain = $missing.Count -gt 0 -and ($unreadableAllowDefinition -or
        @($missing | Where-Object { $conditionalCoverage.ContainsKey($_) }).Count -gt 0)
    $relevantDenies = @($denyEvidence.Values | Where-Object { $_.relevant })
    $denyUncertain = $denyUncertain -or $relevantDenies.Count -gt 0
    $status = if (!$missing.Count -and !$denyUncertain -and !$uncertain) { 'Passed' } else { 'Unknown' }
    Add-Check $Context $CheckId 'RBAC' $Scope $status "Visible unconditional $($Requirement.kind) covering selected operations" @{
        actions = $Requirement.values; uncoveredByVisibleUnconditionalGrants = $missing
        principalSource = $PrincipalSource
        assignments = @($hints.ToArray()); visibility = @($visibility.ToArray())
        denyEvidenceUncertain = $denyUncertain; conditionalOrDefinitionUncertainty = $uncertain
        denyEvidence = @{
            relevant = $relevantDenies; unreadableScopes = @($unreadableDenyScopes.ToArray())
            ignored = @($denyEvidence.Values | Where-Object { !$_.relevant } | ForEach-Object { @{ id = $_.id; scope = $_.scope; reasons = $_.reasons } })
        }
    } -Required $Required -Principal $Principal -Scenario $Scenario -Limitations $limitations `
      -Remediation 'Ask the dependency owner to review scoped grants, live definitions, exclusions, conditions, and deny assignments. Do not infer absence from limited Reader visibility or assign broad roles.'
}

function Get-ConnectionTargetId {
    param($Connection)
    foreach ($candidate in @($Connection.properties.metadata.ResourceId, $Connection.properties.metadata.resourceId, $Connection.properties.target)) {
        if ($candidate -is [string] -and $candidate.StartsWith('/subscriptions/')) {
            try { return (Assert-ArmId $candidate) } catch { continue }
        }
    }
    return ''
}

function Get-EndpointHost {
    param([string]$Value)
    $uri = $null
    if (![uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https' -or
        !$uri.IsDefaultPort -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or
        $uri.HostNameType -ne [UriHostNameType]::Dns -or $uri.Host -notmatch '\.') { return '' }
    # This version supports public Azure DNS suffixes only, not arbitrary connection targets.
    if ($uri.Host -notmatch '(?i)\.(services\.ai\.azure\.com|openai\.azure\.com|cognitiveservices\.azure\.com|blob\.core\.windows\.net|api\.azureml\.ms|in\.applicationinsights\.azure\.com|search\.windows\.net|documents\.azure\.com)$') { return '' }
    return $uri.DnsSafeHost.ToLowerInvariant()
}

function Add-Endpoint {
    param($Context, [string]$Value, [string]$Resource, [string]$Kind, [string[]]$ExpectedIps = @(), [string]$PrivateEndpointId = '')
    $hostName = Get-EndpointHost $Value
    if (!$hostName) { return }
    if (!$Context.ContainsKey('EndpointAliases')) { $Context.EndpointAliases = @{} }
    $mapping = Get-KnownPrivateLinkMapping $hostName
    if ($mapping) {
        # An alias is DNS evidence, never a second TLS hostname. Bind it only to
        # an independently discovered canonical endpoint of the same ARM resource.
        if ($PrivateEndpointId -and $Kind -eq $mapping.group -and $Resource -match $mapping.resourcePattern) {
            $Context.EndpointAliases[$hostName] = @{
                alias = $hostName; canonicalHost = $mapping.canonicalHost; zone = $mapping.zone
                expectedIps = $ExpectedIps; resource = $Resource; privateEndpointId = $PrivateEndpointId
            }
        }
        Sync-EndpointAliases $Context
        return
    }
    if (!$Context.Endpoints.ContainsKey($hostName)) {
        $Context.Endpoints[$hostName] = @{ hostName = $hostName; resource = $Resource; kind = $Kind; expectedIps = @(); privateLinkAliases = @() }
    }
    $Context.Endpoints[$hostName].expectedIps = @(@($Context.Endpoints[$hostName].expectedIps) + $ExpectedIps | Sort-Object -Unique)
    Sync-EndpointAliases $Context
}

function Get-KnownPrivateLinkMapping {
    param([string]$HostName)
    $zones = @{
        'privatelink.services.ai.azure.com' = @{ suffix = 'services.ai.azure.com'; group = 'account'; resourcePattern = '(?i)/providers/Microsoft.CognitiveServices/accounts/[^/]+$' }
        'privatelink.openai.azure.com' = @{ suffix = 'openai.azure.com'; group = 'account'; resourcePattern = '(?i)/providers/Microsoft.CognitiveServices/accounts/[^/]+$' }
        'privatelink.cognitiveservices.azure.com' = @{ suffix = 'cognitiveservices.azure.com'; group = 'account'; resourcePattern = '(?i)/providers/Microsoft.CognitiveServices/accounts/[^/]+$' }
        'privatelink.blob.core.windows.net' = @{ suffix = 'blob.core.windows.net'; group = 'blob'; resourcePattern = '(?i)/providers/Microsoft.Storage/storageAccounts/[^/]+$' }
    }
    foreach ($zone in $zones.Keys) {
        if ($HostName -match ('^(?<label>[a-z0-9-]+)\.' + [regex]::Escape($zone) + '$')) {
            return @{ canonicalHost = "$($Matches.label).$($zones[$zone].suffix)"; zone = $zone
                group = $zones[$zone].group; resourcePattern = $zones[$zone].resourcePattern }
        }
    }
    return $null
}

function Sync-EndpointAliases {
    param($Context)
    foreach ($alias in $Context.EndpointAliases.Values) {
        $endpoint = $Context.Endpoints[$alias.canonicalHost]
        if (!$endpoint -or $endpoint.resource -ine $alias.resource) { continue }
        $endpoint.expectedIps = @(@($endpoint.expectedIps) + @($alias.expectedIps) | Sort-Object -Unique)
        $endpoint.privateLinkAliases = @(@($endpoint.privateLinkAliases | Where-Object { $_.alias -ne $alias.alias }) + @($alias))
    }
}

function Read-Connections {
    param($Context, [string]$AccountId, [string]$ProjectId)
    $connections = [Collections.Generic.List[object]]::new()
    foreach ($scope in @($AccountId, $ProjectId)) {
        $read = Read-Arm $Context "$scope/connections" -Collection
        Add-Check $Context 'connection.discovery' 'Connections' $scope (Get-ReadStatus $read -Collection) 'Read connection metadata without credentials' @{
            readStatus = $read.Code; count = @($read.Data).Count
        } -Classification $(if ($read.Code -eq 200) {'Inventory'} else {'Finding'}) -Required ($scope -eq $ProjectId) -Limitations @('Account connections are eligible only when shared to all; owner-scoped non-shared connections need manual confirmation.')
        if ($read.Code -ne 200) { continue }
        foreach ($connection in $read.Data) {
            if ($scope -eq $AccountId -and !$connection.properties.isSharedToAll) { continue }
            $connections.Add($connection)
        }
    }
    # A project-level connection shadows a shared account alias.
    $resolved = @{}
    foreach ($connection in $connections) { $resolved[$connection.name] = $connection }
    return @($resolved.Values)
}

function Select-Connection {
    param($Context, $Connections, [string[]]$Categories, [string]$Name, [string]$CheckId, [string]$ProjectId, [string]$Scenario,
        [switch]$AllowKnownModelAccount)
    $matches = @($Connections | Where-Object { $_.properties.category -in $Categories -and (!$Name -or $_.name -eq $Name) })
    $selected = if ($matches.Count -eq 1) { $matches[0] } else { $null }
    $id = if ($selected) { Get-ConnectionTargetId $selected } else { '' }
    $resolution = if ($id) { 'ExplicitResourceId' } else { 'Unresolved' }
    $knownAccountIds = @()
    if ($AllowKnownModelAccount -and $selected -and !$id -and
        !$selected.properties.metadata.ResourceId -and !$selected.properties.metadata.resourceId) {
        $knownAccountIds = @(Get-KnownModelAccountIds $Context (Get-EndpointHost $selected.properties.target))
        if ($knownAccountIds.Count -eq 1) {
            $id = $knownAccountIds[0]
            $resolution = 'ExactCanonicalHostOfReadAccount'
        }
        elseif ($knownAccountIds.Count -gt 1) { $resolution = 'AmbiguousReadAccountHost' }
    }
    $status = if ($selected -and $id) { 'Passed' } else { 'Unknown' }
    $expected = if ($AllowKnownModelAccount) { 'An unambiguous connection with an explicit ARM ID or exact unique canonical-host association to an already-read account' }
        else { 'An unambiguous connection with an explicit dependency ARM ID' }
    Add-Check $Context $CheckId 'Connections' $ProjectId $status $expected @{
        candidateAliases = @($matches | ForEach-Object { $_.name }); selectedAlias = $selected.name
        targetResourceId = $id; authType = $selected.properties.authType; category = $selected.properties.category
        targetHost = $(if ($selected) { Get-EndpointHost $selected.properties.target } else { '' })
        targetResolution = $resolution; knownAccountMatches = $knownAccountIds
    } -Scenario $Scenario -Limitations @('A connection alias is not a resource name. No ARM ID is invented from a hostname or AppId. Exact model-host association uses only already-read account endpoint metadata, never another connection authentication path or external discovery.')
    return @{ Connection = $selected; Id = $id }
}

function Get-KnownModelAccountIds {
    param($Context, [string]$HostName)
    if (!$HostName -or (Get-KnownPrivateLinkMapping $HostName)) { return @() }
    $ids = @{}
    foreach ($entry in $Context.Cache.GetEnumerator()) {
        if ($entry.Key -notmatch '^(?<id>/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.CognitiveServices/accounts/[^/]+)\|False$') { continue }
        $id = $Matches.id
        $read = $entry.Value
        if ($read.Code -ne 200 -or $read.Data.id -ine $id) { continue }
        $hosts = @((Get-EndpointHost $read.Data.properties.endpoint))
        if ($read.Data.properties.endpoints) {
            $hosts += @($read.Data.properties.endpoints.Values | ForEach-Object { Get-EndpointHost $_ })
        }
        if ($HostName -in $hosts) { $ids[$id] = $true }
    }
    return @($ids.Keys)
}

function Get-Outcome {
    param($Checks)
    $findings = @($Checks | Where-Object { !$_.classification -or $_.classification -eq 'Finding' })
    $coverage = @($Checks | Where-Object { $_.classification -eq 'Coverage' -and $_.status -eq 'NotAssessed' })
    $exitCode = 0
    $status = 'Passed for selected implemented checks'
    if (@($findings | Where-Object { $_.required -and $_.status -eq 'Failed' }).Count) {
        $exitCode = 1; $status = 'Failed'
    }
    elseif (@($findings | Where-Object { $_.required -and $_.status -ne 'Passed' }).Count) {
        $exitCode = 2; $status = 'Inconclusive'
    }
    $actionable = @($Checks | Where-Object { $_.classification -ne 'Coverage' -and $_.status -in @('Failed','Unknown','Warning') })
    $groups = @($actionable | Group-Object { "$($_.status)|$($_.id)" } | Sort-Object Name | ForEach-Object {
        @{ id = $_.Group[0].id; status = $_.Group[0].status; count = $_.Count
            required = @($_.Group | Where-Object { $_.required }).Count -gt 0
            resources = @($_.Group | ForEach-Object { $_.resource } | Sort-Object -Unique) }
    })
    return @{
        exitCode = $exitCode; status = $status; findingCount = $findings.Count
        passedFindingCount = @($findings | Where-Object { $_.status -eq 'Passed' }).Count
        inventoryCount = @($Checks | Where-Object { $_.classification -eq 'Inventory' }).Count
        coverageStatus = $(if ($coverage.Count) {'Incomplete'} else {'No declared gaps'})
        notAssessedCount = $coverage.Count; notAssessed = @($coverage | ForEach-Object { $_.id } | Sort-Object -Unique)
        actionableGroups = $groups
    }
}
