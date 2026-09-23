function Test-CapabilityHosts {
    param($Context, [string]$Scope, [string]$Label)
    $hosts = Read-Arm $Context "$Scope/capabilityHosts" -Collection
    $states = @($hosts.Data | ForEach-Object { @{ id = $_.id; kind = $_.properties.capabilityHostKind; state = $_.properties.provisioningState
        storageConnections = $_.properties.storageConnections; vectorStoreConnections = $_.properties.vectorStoreConnections; threadStorageConnections = $_.properties.threadStorageConnections } })
    $status = if ($hosts.Code -ne 200 -or !$states.Count) {'Unknown'}
        elseif (@($states | Where-Object { $_.state -in @('Failed','Canceled') }).Count) {'Failed'}
        elseif (@($states | Where-Object { $_.state -ne 'Succeeded' }).Count) {'Unknown'} else {'Passed'}
    Add-Check $Context "caphost.$Label" 'CapabilityHost' $Scope $status 'Customer-visible capability host metadata and provisioning state' @{
        readStatus = $hosts.Code; hosts = $states
    } -Limitations @('Account and project hosts are distinct. Empty lists can be unsupported topology; no MT route or ephemeral ST container state is inferred. Project hosts may have been added independently of the original template.')
    return @($hosts.Data)
}

function Test-StorageScenario {
    param($Context, $Options, $Catalog, $Connections, [string]$ProjectPrincipal, $Topology)
    $selected = Select-Connection $Context $Connections @('AzureStorageAccount','AzureBlob') $Options.StorageConnection 'storage.connection' $Options.ProjectId 'Core'
    if (!$selected.Id) { return }
    if ($selected.Id -notmatch '(?i)/providers/Microsoft.Storage/storageAccounts/[^/]+$') {
        Add-Check $Context 'storage.targetType' 'Storage' $selected.Id 'Failed' 'Storage connection resolves to a storage account' @{ reason = 'WrongResourceType' }
        return
    }
    $storage = Test-Provisioning $Context $selected.Id 'storage.resource'
    if ($storage.Code -eq 200) {
        $p = $storage.Data.properties
        Add-Check $Context 'storage.privatePolicy' 'Storage' $selected.Id $(if ($p.publicNetworkAccess -eq 'Disabled' -or $p.networkAcls.defaultAction -eq 'Deny') {'Passed'} elseif (!$p.publicNetworkAccess -and !$p.networkAcls.defaultAction) {'Unknown'} else {'Warning'}) `
            'Observe intended private storage policy' @{ publicNetworkAccess = $p.publicNetworkAccess; defaultAction = $p.networkAcls.defaultAction; bypass = $p.networkAcls.bypass; allowSharedKeyAccess = $p.allowSharedKeyAccess } `
            -Required $false -Limitations @('PNA Disabled is normal. Policy alone does not prove connectivity; do not enable public access to diagnose.')
        $actualHost = Get-EndpointHost $p.primaryEndpoints.blob
        $connectionHost = Get-EndpointHost $selected.Connection.properties.target
        $status = if (!$actualHost -or !$connectionHost) {'Unknown'} elseif ($actualHost -eq $connectionHost) {'Passed'} else {'Failed'}
        Add-Check $Context 'storage.target' 'Storage' $selected.Id $status 'Connection target matches storage primary Blob endpoint' @{ connectionHost = $connectionHost; resourceHost = $actualHost } `
            -Remediation 'Have the project owner compare the selected connection ResourceId and target with the existing storage Blob endpoint. No dataset, pending upload, SAS, or blob probe is needed for this metadata comparison.'
        Add-Endpoint $Context $p.primaryEndpoints.blob $selected.Id 'blob'
    }
    $auth = $selected.Connection.properties.authType
    Add-Check $Context 'storage.authentication' 'Storage' $selected.Id $(if ($auth -in @('AAD','ManagedIdentity')) {'Passed'} else {'Unknown'}) `
        'Identity-driven storage connection for selected project MI checks' @{ authType = $auth } -Limitations @('Unsupported authentication paths are not tested using secrets.')
    Test-ConfiguredGrant $Context $selected.Id $ProjectPrincipal $Catalog.actions.Blob 'rbac.blob.projectMI'
    Test-PrivateEndpointConfiguration $Context $selected.Id 'blob' $Topology
}

function Test-ModelScenario {
    param($Context, $Options, $Catalog, $Connections, [string]$AccountId, [string]$ProjectPrincipal, $Topology)
    $selected = Select-Connection $Context $Connections @('AzureOpenAI','AIServices','CognitiveService') $Options.ModelConnection 'model.connection' $Options.ProjectId 'Models' -AllowKnownModelAccount
    $id = $selected.Id
    if (!$id) { return }
    if ($id -notmatch '(?i)/providers/Microsoft.CognitiveServices/accounts/[^/]+$') {
        Add-Check $Context 'model.targetType' 'Models' $id 'Unknown' 'Supported Cognitive Services model account target' @{ reason = 'UnsupportedModelTopology' } -Scenario Models
        return
    }
    $account = Read-Arm $Context $id
    $deployments = Read-Arm $Context "$id/deployments" -Collection
    $matches = @($deployments.Data | Where-Object { !$Options.ModelDeployment -or $_.name -eq $Options.ModelDeployment })
    $status = if ($deployments.Code -ne 200 -or $matches.Count -ne 1) {'Unknown'}
        elseif ($matches[0].properties.provisioningState -eq 'Succeeded') {'Passed'}
        elseif ($matches[0].properties.provisioningState -in @('Failed','Canceled')) {'Failed'} else {'Unknown'}
    if ($deployments.Code -eq 200 -and $Options.ModelDeployment -and !$matches.Count) { $status = 'Failed' }
    Add-Check $Context 'model.deployment' 'Models' $id $status 'Selected deployment exists and is provisioned' @{
        readStatus = $deployments.Code; deployments = @($matches | ForEach-Object { @{ name = $_.name; state = $_.properties.provisioningState; model = $_.properties.model } })
    } -Scenario Models -Limitations @('Deployment metadata does not establish model capacity, protocol support, grader compatibility, or inference authorization.')
    $auth = $Options.ModelAuthentication
    $connectionAuth = switch ($selected.Connection.properties.authType) { 'ApiKey' {'ApiKey'} 'AAD' {'Entra'} 'ManagedIdentity' {'Entra'} default {'Unknown'} }
    if ($auth -eq 'Auto') {
        $auth = $connectionAuth
    }
    $status = if ($auth -eq 'ApiKey' -and $account.Code -eq 200 -and $account.Data.properties.disableLocalAuth -eq $true) {'Failed'}
        elseif ($auth -eq 'ApiKey' -and $account.Code -eq 200 -and $account.Data.properties.disableLocalAuth -eq $false) {'Passed'}
        elseif ($auth -eq 'Entra') {'Passed'} else {'Unknown'}
    if ($connectionAuth -ne 'Unknown' -and $Options.ModelAuthentication -ne 'Auto' -and $connectionAuth -ne $auth) { $status = 'Failed' }
    Add-Check $Context 'model.authentication' 'Models' $id $status 'Selected authentication agrees with model account local-auth policy' @{
        selectedAuthentication = $auth; connectionAuthType = $selected.Connection.properties.authType; disableLocalAuth = $account.Data.properties.disableLocalAuth
    } -Scenario Models -Limitations @('API-key validity is never checked. Project MI model grants are not required for an API-key path.') `
        -Remediation 'Confirm the intended authentication path with the model connection owner and compare it with disableLocalAuth. Do not fetch/test keys or change account authentication policy as a diagnostic step.'
    if ($auth -eq 'Entra') {
        $principal = if ('Scheduled' -in $Options.Profiles -or 'Continuous' -in $Options.Profiles) { $ProjectPrincipal } else { $Options.Caller }
        Test-ConfiguredGrant $Context $id $principal $Catalog.actions.Model 'rbac.model.intendedIdentity' 'Models'
    }
    $hosts = @((Get-EndpointHost $account.Data.properties.endpoint))
    if ($account.Data.properties.endpoints) {
        $hosts += @($account.Data.properties.endpoints.Values | ForEach-Object { Get-EndpointHost $_ })
    }
    $connectionHost = Get-EndpointHost $selected.Connection.properties.target
    Add-Check $Context 'model.target' 'Models' $id $(if ($connectionHost -and $connectionHost -in $hosts) {'Passed'} else {'Unknown'}) `
        'Connection host agrees with a discovered model account endpoint' @{
            connectionHost = $connectionHost; accountEndpointHosts = @($hosts | Where-Object { $_ })
        } -Scenario Models -Limitations @('ARM may omit protocol-specific endpoints. Missing host correspondence is inconclusive; endpoint names are not invented.')
    Add-Endpoint $Context $account.Data.properties.endpoint $id 'model'
    Add-Endpoint $Context $selected.Connection.properties.target $id 'model'
    if ($id -ne $AccountId) { Test-PrivateEndpointConfiguration $Context $id 'account' $Topology }
}

function Get-MonitoringPrivateLinks {
    param($Properties)
    $links = @{}
    if (!$Properties) { return @() }
    foreach ($item in @($Properties['PrivateLinkScopedResources']) + @($Properties['privateLinkScopedResources'])) {
        if (!$item) { continue }
        $resourceId = if ($item['ResourceId']) { [string]$item['ResourceId'] } else { [string]$item['resourceId'] }
        $scopeId = if ($item['ScopeId']) { [string]$item['ScopeId'] } else { [string]$item['scopeId'] }
        if (!$resourceId -and !$scopeId) { continue }
        $links["$resourceId|$scopeId"] = @{ resourceId = $resourceId; scopeId = $scopeId }
    }
    return @($links.Values)
}

function Test-MonitoringQueryPathCoverage {
    param($Context, [string]$ComponentId, $Component, $Workspace, $PrivateLinks)
    $componentQuery = $Component.Data.properties.publicNetworkAccessForQuery
    $workspaceQuery = $Workspace.Data.properties.publicNetworkAccessForQuery
    $privateRequired = $componentQuery -eq 'Disabled' -or $workspaceQuery -eq 'Disabled' -or @($PrivateLinks).Count -gt 0
    $policyKnown = $Component.Code -eq 200 -and $Workspace.Code -eq 200 -and
        $componentQuery -in @('Enabled','Disabled') -and $workspaceQuery -in @('Enabled','Disabled')
    $reason = if ($privateRequired) {'PrivateMonitoringQueryPathNotAssessed'}
        elseif (!$policyKnown) {'QueryNetworkPolicyUnavailable'} else {'NoPrivateQueryPolicyObserved'}
    if (!$policyKnown) {
        Add-Check $Context 'monitoring.queryPolicy' 'Monitoring' $ComponentId 'Unknown' 'Read component and workspace query-network policies' @{
            componentReadStatus = $Component.Code; workspaceReadStatus = $Workspace.Code
            componentQueryPolicy = $componentQuery; workspaceQueryPolicy = $workspaceQuery
        } -Scenario Traces
    }
    Add-Check $Context 'monitoring.queryPathCoverage' 'Monitoring' $ComponentId 'NotAssessed' `
        'Expose unassessed private monitoring query-path requirements separately from ARM discovery' @{
            reason = $reason; privateQueryPathRequired = $privateRequired
            componentQueryPolicy = $componentQuery; workspaceQueryPolicy = $workspaceQuery
            componentIngestionPolicy = $Component.Data.properties.publicNetworkAccessForIngestion
            privateLinkAssociations = @($PrivateLinks); runtimeReachabilityTested = $false; queryExecuted = $false
        } -Classification Coverage -Scenario Traces `
        -Limitations @('ARM GET success and private-link association presence do not prove AMPLS DNS or reachability. AMPLS/DCE/DCR traversal and service query-path probes are outside this version. This is a trace-read assessment, not an ingestion/API-key permission check.') `
        -Remediation 'This tool does not assess monitoring query reachability. Use separately authorized monitoring/network evidence if needed; do not enable public access, provision resources, or run a query/evaluation during this diagnostic.'
}

function Test-MonitoringScenario {
    param($Context, $Options, $Catalog, $Connections, [string]$ProjectPrincipal)
    $selected = Select-Connection $Context $Connections @('AppInsights','ApplicationInsights') $Options.MonitoringConnection 'monitoring.connection' $Options.ProjectId 'Traces'
    if (!$selected.Id) { return }
    if ($selected.Id -notmatch '(?i)/providers/Microsoft.Insights/components/[^/]+$') {
        Add-Check $Context 'monitoring.targetType' 'Monitoring' $selected.Id 'Failed' 'Application Insights resource ID, not connection alias' @{ reason = 'WrongResourceType' } -Scenario Traces
        return
    }
    $component = Read-Arm $Context $selected.Id
    $workspaceId = $component.Data.properties.WorkspaceResourceId
    $privateLinks = @(Get-MonitoringPrivateLinks $component.Data.properties)
    Add-Check $Context 'monitoring.component' 'Monitoring' $selected.Id (Get-ReadStatus $component) 'Discover Insights component and backing-workspace ARM metadata only, not reachability' @{
        alias = $selected.Connection.name; componentResourceId = $selected.Id; workspaceResourceId = $workspaceId
        readStatus = $component.Code; publicNetworkAccessForQuery = $component.Data.properties.publicNetworkAccessForQuery
        publicNetworkAccessForIngestion = $component.Data.properties.publicNetworkAccessForIngestion
        privateLinkScopes = @($privateLinks | ForEach-Object { $_.resourceId } | Where-Object { $_ })
        privateLinkAssociations = $privateLinks
    } -Classification $(if ($component.Code -eq 200) {'Inventory'} else {'Finding'}) -Scenario Traces -Limitations @('AppId/connection alias is not the Azure resource name. Monitoring private-link forwarding and ingestion are not exercised.')
    if (!$workspaceId) {
        Add-Check $Context 'monitoring.workspace' 'Monitoring' $selected.Id 'Unknown' 'Resolve backing Log Analytics workspace' @{ reason = 'WorkspaceIdUnavailable' } -Scenario Traces
        Test-MonitoringQueryPathCoverage $Context $selected.Id $component @{ Code = 0; Data = $null } $privateLinks
        return
    }
    $workspace = Read-Arm $Context $workspaceId
    Add-Check $Context 'monitoring.workspace' 'Monitoring' $workspaceId (Get-ReadStatus $workspace) 'Read backing-workspace ARM metadata only, not query reachability' @{
        readStatus = $workspace.Code; publicNetworkAccessForQuery = $workspace.Data.properties.publicNetworkAccessForQuery
        enableLogAccessUsingOnlyResourcePermissions = $workspace.Data.properties.features.enableLogAccessUsingOnlyResourcePermissions
    } -Classification $(if ($workspace.Code -eq 200) {'Inventory'} else {'Finding'}) -Scenario Traces
    Test-MonitoringQueryPathCoverage $Context $selected.Id $component $workspace $privateLinks
    $principalSource = 'Tool configuration: discovered project managed identity; caller and connection credentials are assessed separately. Actual service execution identity is not verified.'
    Test-ConfiguredGrant $Context $selected.Id $ProjectPrincipal $Catalog.actions.TraceResource 'rbac.trace.resourceCandidate' 'Traces' -PrincipalSource $principalSource -Required $false
    $resourceGrant = $Context.Checks[$Context.Checks.Count - 1]
    $resourcePermissionMode = $workspace.Data.properties.features.enableLogAccessUsingOnlyResourcePermissions
    $resourceScopeUsable = $workspace.Code -eq 200 -and $resourcePermissionMode -is [bool] -and $resourcePermissionMode
    $resourceGrantSufficient = $resourceScopeUsable -and $resourceGrant.status -eq 'Passed' -and !$resourceGrant.observed.denyEvidenceUncertain
    if ($resourceGrantSufficient) {
        Add-Check $Context 'rbac.trace.workspaceCandidate' 'RBAC' $workspaceId 'NotApplicable' `
            'Workspace RBAC alternative is unnecessary when the selected resource-context grant is sufficient' @{
                reason = 'ResourceContextGrantSufficient'; assessed = $false; selectedGrantScope = $selected.Id
                principalSource = $principalSource
            } -Classification Inventory -Principal $ProjectPrincipal -Scenario Traces `
            -Remediation 'No workspace-role assessment is needed for this selected resource-context path; no workspace grant is claimed.'
        $workspaceGrant = @{ status = 'NotApplicable' }
    }
    else {
        Test-ConfiguredGrant $Context $workspaceId $ProjectPrincipal $Catalog.actions.Trace 'rbac.trace.workspaceCandidate' 'Traces' -PrincipalSource $principalSource -Required $false
        $workspaceGrant = $Context.Checks[$Context.Checks.Count - 1]
    }
    $grantScope = if ($resourceGrantSufficient) { $selected.Id }
        elseif ($workspaceGrant.status -eq 'Passed' -and !$resourceGrant.observed.denyEvidenceUncertain) { $workspaceId } else { '' }
    Add-Check $Context 'rbac.trace.intendedIdentity' 'RBAC' $selected.Id $(if ($grantScope) {'Passed'} else {'Unknown'}) `
        'Configured project-MI read grants for QueryResourceAsync at the Insights component under the backing workspace access policy' @{
            principalSource = $principalSource; queryApi = 'QueryResourceAsync'; queryResourceId = $selected.Id
            workspaceResourceId = $workspaceId; enableLogAccessUsingOnlyResourcePermissions = $resourcePermissionMode
            resourcePermissionPolicyKnown = ($workspace.Code -eq 200 -and $resourcePermissionMode -is [bool])
            configuredGrantScope = $grantScope; resourceCandidateStatus = $resourceGrant.status; workspaceCandidateStatus = $workspaceGrant.status
            queryResourceDenyUncertainty = $resourceGrant.observed.denyEvidenceUncertain
        } -Principal $ProjectPrincipal -Scenario Traces `
        -Limitations @('Resource-context and workspace-permission grants are alternative configuration paths, not two mandatory roles. Unknown access policy cannot certify component-only grants. No caller substitution, token minting, query, table-protection check, or effective-access test is performed.') `
        -Remediation 'Review the project MI grant at the component and the workspace access-control mode before considering workspace grants. Do not require broad workspace access when legitimate resource-context grants suffice.'
    if ($Options.PrivilegedTraceContent) {
        Test-ConfiguredGrant $Context $selected.Id $ProjectPrincipal $Catalog.actions.PrivilegedTrace 'rbac.trace.privilegedCandidate' 'Traces' -PrincipalSource $principalSource -Required $false
        Add-Check $Context 'monitoring.privilegedCoverage' 'Monitoring' $workspaceId 'NotAssessed' 'Confirm table-specific privileged-content policy' @{ reason = 'PrivilegedContentNotCertifiedByGenericWorkspaceGrant' } -Classification Coverage -Scenario Traces `
            -Limitations @('No trace content is queried. Sensitive trace-content access needs scenario-specific owner evidence.')
    }
}

function Invoke-ConfigurationAssessment {
    param($Context, $Options, $Catalog)
    $projectId = $Options.ProjectId
    $accountId = $projectId -replace '/projects/[^/]+$', ''
    $account = Test-Provisioning $Context $accountId 'resource.account'
    $project = Test-Provisioning $Context $projectId 'resource.project'
    $accountPrincipal = Get-Principal $Context $account $accountId 'account'
    $projectPrincipal = Get-Principal $Context $project $projectId 'project'
    $topology = Test-SubnetConfiguration $Context $account $accountId
    $null = Test-CapabilityHosts $Context $accountId 'account'
    $projectHosts = Test-CapabilityHosts $Context $projectId 'project'
    $connections = @(Read-Connections $Context $accountId $projectId)
    Test-ConfiguredGrant $Context $projectId $projectPrincipal $Catalog.actions.ProjectAssets 'rbac.assets.projectMI'
    if ($Options.Caller) {
        Test-ConfiguredGrant $Context $projectId $Options.Caller $Catalog.actions.ProjectAssets 'rbac.assets.evaluationCaller'
    }
    else {
        Add-Check $Context 'rbac.assets.evaluationCaller' 'RBAC' $projectId 'NotAssessed' 'Assess optional evaluation-caller grants only when an intended caller is supplied' @{
            reason = 'OptionalCallerNotSpecified'; operatorSubstituted = $false
        } -Classification Coverage -Remediation 'Supply EvaluationCallerObjectId only if caller-specific configuration is in scope. Do not substitute the diagnostic operator or host identity.'
    }
    if ('Scheduled' -in $Options.Profiles -or 'Continuous' -in $Options.Profiles) {
        Add-Check $Context 'identity.scheduled' 'Identity' $projectId $(if ($projectPrincipal) {'Passed'} else {'Unknown'}) `
            'Scheduled/continuous dependency checks use project MI, not diagnostic operator' @{ principalId = $projectPrincipal } -Principal $projectPrincipal -Scenario Scheduled
    }
    Add-Endpoint $Context $account.Data.properties.endpoint $accountId 'account'
    if ($account.Data.properties.endpoints) {
        foreach ($endpoint in $account.Data.properties.endpoints.Values) { Add-Endpoint $Context $endpoint $accountId 'account' }
    }
    if ($project.Data.properties.endpoints) {
        foreach ($endpoint in $project.Data.properties.endpoints.Values) { Add-Endpoint $Context $endpoint $accountId 'project' }
    }
    Add-Endpoint $Context $project.Data.properties.endpoint $accountId 'project'
    Test-PrivateEndpointConfiguration $Context $accountId 'account' $topology
    Test-StorageScenario $Context $Options $Catalog $connections $projectPrincipal $topology
    if ('Models' -in $Options.Profiles -or 'Graders' -in $Options.Profiles) {
        Test-ModelScenario $Context $Options $Catalog $connections $accountId $projectPrincipal $topology
    }
    if ('Traces' -in $Options.Profiles) { Test-MonitoringScenario $Context $Options $Catalog $connections $projectPrincipal }
    if ('Agent' -in $Options.Profiles) {
        $references = @($projectHosts | ForEach-Object { @($_.properties.vectorStoreConnections) + @($_.properties.threadStorageConnections) } | Where-Object { $_ })
        foreach ($connection in @($connections | Where-Object { $_.properties.category -in @('CognitiveSearch','AzureAISearch','CosmosDb','AzureCosmosDB') })) {
            $id = Get-ConnectionTargetId $connection
            $read = if ($id) { Read-Arm $Context $id } else { @{ Code = 0; Data = $null } }
            Add-Check $Context 'agent.dependency' 'Agent' $id $(if ($id) { Get-ReadStatus $read } else {'Unknown'}) 'Read discovered optional agent dependency' @{
                alias = $connection.name; category = $connection.properties.category; readStatus = $read.Code
            } -Scenario Agent
        }
        Add-Check $Context 'agent.coverage' 'Agent' $projectId 'NotAssessed' 'Confirm intended agent target and dependency authorization topology' @{
            discoveredCapabilityHostReferences = $references
        } -Classification Coverage -Scenario Agent -Limitations @('No agent API is called. Search/Cosmos are not required for Core. Connection metadata alone cannot certify the intended agent topology.')
    }
    Add-Check $Context 'coverage.runtime' 'Coverage' $projectId 'NotAssessed' 'Customer ARM configuration coverage only' @{
        evaluationRun = $false; inferenceRun = $false; dataPlaneAuthorizationExercised = $false
    } -Classification Coverage -Limitations @('Service-side execution, service-managed resources, actual storage writes, keys, and evaluation success are outside coverage.')
}
