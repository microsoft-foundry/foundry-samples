#requires -Version 7.2
[CmdletBinding()]
param([string]$OutputDirectory = (Join-Path ([IO.Path]::GetTempPath()) ('vnet-diagnostic-tests-' + [guid]::NewGuid().ToString('N'))))
$ErrorActionPreference = 'Stop'
$scripts = Join-Path $PSScriptRoot '..\scripts'
. (Join-Path $scripts 'ArmReader.ps1')
. (Join-Path $scripts 'Checks.ps1')
. (Join-Path $scripts 'NetworkChecks.ps1')
. (Join-Path $scripts 'Scenarios.ps1')
. (Join-Path $PSScriptRoot 'New-Fixture.ps1')
$catalog = Get-Content (Join-Path $PSScriptRoot '..\references\requirements.json') -Raw | ConvertFrom-Json -AsHashtable
$topologies = Get-Content (Join-Path $PSScriptRoot 'fixtures\topologies.json') -Raw | ConvertFrom-Json -AsHashtable
$null = New-Item -ItemType Directory -Path $OutputDirectory -Force
$script:assertions = 0
function Assert-True([bool]$Condition, [string]$Message) {
    $script:assertions++
    if (!$Condition) { throw "Assertion failed: $Message" }
}
function Assert-Throws([scriptblock]$Action, [string]$Message) {
    $threw = $false
    try { & $Action | Out-Null } catch { $threw = $true }
    Assert-True $threw $Message
}
function New-TestContext($Fixture, [string]$Name = 'working') {
    $path = Join-Path $OutputDirectory "$Name.fixture.json"
    $Fixture | ConvertTo-Json -Depth 70 | Set-Content $path
    return (New-DiagnosticContext $path 'MUST-NOT-RUN-AZ' @())
}
function New-TestOptions($Fixture, [string[]]$Profiles = @('Core')) {
    return @{ ProjectId = $Fixture.test.project; Profiles = $Profiles; Caller = $Fixture.test.principal; ModelAuthentication = 'Auto'; PrivilegedTraceContent = $false }
}
function Find-Check($Context, [string]$Id) { return @($Context.Checks | Where-Object { $_.id -eq $Id } | ForEach-Object { [pscustomobject]$_ }) }

foreach ($file in Get-ChildItem $scripts -Filter '*.ps1') {
    $tokens = $null; $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    Assert-True (!$errors.Count) "PowerShell syntax: $($file.Name)"
}
$fixture = New-TopologyFixture $topologies[0]
$id = $fixture.test.project
$validUri = "https://management.azure.com${id}?api-version=2025-06-01"
$null = Assert-ArmRequest $validUri
foreach ($method in @('POST','PUT','PATCH','DELETE','HEAD','get')) {
    Assert-Throws { Assert-ArmRequest $validUri -Method $method } "Reject method $method"
}
foreach ($bad in @(
    $validUri.Replace('management.azure.com','evil.example'),
    $validUri.Replace('https:','http:'),
    "$validUri&sig=secret",
    "$validUri#fragment",
    "$validUri&api-version=2025-06-01",
    "https://management.azure.com${id}/listSecrets?api-version=2025-06-01",
    "https://management.azure.com${id}/validate?api-version=2025-06-01",
    "https://management.azure.com${id}/evaluations?api-version=2025-06-01",
    "https://management.azure.com${id}/../fixtureproject?api-version=2025-06-01",
    "https://management.azure.com${id}?api-version=2000-01-01"
)) { Assert-Throws { Assert-ArmRequest $bad } 'Reject unsafe request' }
Assert-Throws { Assert-ArmRequest $validUri -InitialPath $fixture.test.storage } 'Paging scope must match exactly'
Assert-Throws { Assert-ArmId "$id/../other" -Project } 'Reject traversal IDs'
Assert-Throws { Assert-ArmId "$id%2fconnections" -Project } 'Reject encoded IDs'
Assert-Throws { New-DiagnosticContext '' 'az' @('login') } 'Reject arbitrary CLI prefix'
$invalidFixture = Join-Path $OutputDirectory 'invalid.fixture.json'
'null' | Set-Content $invalidFixture
Assert-Throws { New-DiagnosticContext $invalidFixture 'MUST-NOT-RUN-AZ' @() } 'Null fixture must never fall back to Azure'
'{}' | Set-Content $invalidFixture
Assert-Throws { New-DiagnosticContext $invalidFixture 'MUST-NOT-RUN-AZ' @() } 'Missing fixture response map must never fall back to Azure'
Assert-True ((Get-ReadStatus @{Code=403}) -eq 'Unknown') '403 is Unknown'
Assert-True ((Get-ReadStatus @{Code=404}) -eq 'Failed') 'Explicit-resource 404 is missing'
Assert-True ((Get-ReadStatus @{Code=404} -Collection) -eq 'Unknown') 'Collection 404 may be unsupported'

foreach ($topology in $topologies) {
    $fixture = New-TopologyFixture $topology
    $ctx = New-TestContext $fixture $topology.name
    Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture) $catalog
    $outcome = Get-Outcome $ctx.Checks
    Assert-True ($outcome.exitCode -eq 0) "$($topology.name): complete selected Core fixture passes"
    Assert-True (!(Find-Check $ctx 'monitoring.connection').Count) 'Monitoring not required on Core'
    Assert-True (!(Find-Check $ctx 'agent.coverage').Count) 'Search/Cosmos not required on Core'
    Assert-True ((Find-Check $ctx 'network.injection')[0].status -eq 'Passed') 'Account injection, no project injection required'
    Assert-True ((Find-Check $ctx 'rbac.assets.projectMI')[0].status -eq 'Passed') 'Inherited custom-role assets grant'
    Assert-True ((Find-Check $ctx 'rbac.blob.projectMI')[0].status -eq 'Passed') 'Separate inherited Blob grant'
    Assert-True ((Find-Check $ctx 'dns.records' | Where-Object status -eq 'Failed').Count -eq 0) 'Expected DNS records match'
    Assert-True ($ctx.Endpoints.Count -eq 4) 'Canonical service hosts are deduplicated; aliases are not extra TLS targets'
    foreach ($mapping in @(
        @{ hostName = 'fixtureaccount.services.ai.azure.com'; ip = '10.0.1.4' },
        @{ hostName = 'fixtureaccount.openai.azure.com'; ip = '10.0.1.6' },
        @{ hostName = 'fixtureaccount.cognitiveservices.azure.com'; ip = '10.0.1.7' },
        @{ hostName = 'fixturestorage.blob.core.windows.net'; ip = '10.0.1.5' }
    )) {
        $endpoint = $ctx.Endpoints[$mapping.hostName]
        Assert-True ($endpoint.expectedIps.Count -eq 1 -and $endpoint.expectedIps[0] -eq $mapping.ip) 'PE IP maps to the right canonical endpoint, not all IPs on the NIC'
        Assert-True ($endpoint.privateLinkAliases.Count -eq 1) 'Alias metadata is preserved on canonical endpoint'
        Assert-True (!$ctx.Endpoints.ContainsKey($endpoint.privateLinkAliases[0].alias)) 'Private-link alias is not a probe target'
    }
    $fixturePath = Join-Path $OutputDirectory "$($topology.name).fixture.json"
    $reportPath = Join-Path $OutputDirectory $topology.name
    $output = & (Join-Path $PSHOME $(if ($IsWindows) {'pwsh.exe'} else {'pwsh'})) -NoProfile -File (Join-Path $scripts 'Invoke-VNetProjectDiagnostics.ps1') `
        -ProjectResourceId $fixture.test.project -EvaluationCallerObjectId $fixture.test.principal -FixturePath $fixturePath -OutputDirectory $reportPath
    Assert-True ($LASTEXITCODE -eq 0) "CLI fixture exit code: $($output -join ' ')"
    Assert-True (@($output).Count -eq 4 -and $output[1] -match '^Coverage:' -and ($output -join ' ') -notmatch 'VoidTaskResult') 'Console emits compact findings/coverage summary and two report paths'
    $report = Get-Content (Join-Path $reportPath 'diagnostics.json') -Raw | ConvertFrom-Json -AsHashtable
    Assert-True ($report.fixture -and $report.summary.exitCode -eq 0) 'CLI persisted JSON report'
    Assert-True (Test-Path (Join-Path $reportPath 'diagnostics.md')) 'CLI persisted readable report'
    foreach ($check in $report.checks) {
        foreach ($field in @('id','domain','scenario','required','classification','status','severity','principal','resource','scope','expected','observed','evidenceKind','collectedAt','hostContext','limitations','remediation')) {
            Assert-True $check.ContainsKey($field) "Report field $field"
        }
    }
}

$fixture = New-TopologyFixture $topologies[0]
$role = $fixture.responses[$fixture.test.role].Data
Assert-True (Test-RolePermission $role $catalog.actions.ProjectAssets.values[0] 'dataActions') 'Inspect second permission block'
Assert-True (!(Test-RolePermission $role 'Microsoft.CognitiveServices/accounts/AIServices/assets/delete' 'dataActions')) 'Subtract notDataActions'
Assert-True (!(Test-RolePermission @{properties=@{permissions=@(@{actions=@('*');dataActions=@()})}} $catalog.actions.ProjectAssets.values[0] 'dataActions')) 'Management wildcard does not grant dataActions'
$role.properties.permissions[0].notActions = @('Microsoft.OperationalInsights/*')
Assert-True (!(Test-RolePermission $role $catalog.actions.Trace.values[0] 'actions')) 'Subtract notActions'
$role.properties.permissions += @{ actions = @($catalog.actions.Trace.values[0]); notActions = @() }
Assert-True (Test-RolePermission $role $catalog.actions.Trace.values[0] 'actions') 'Exclusion is per permission block, not global deny'
$ctx = New-TestContext $fixture
$assignmentKey = "$($fixture.test.rg)/providers/Microsoft.Authorization/roleAssignments"
$fixture.responses[$assignmentKey].Data.value[0].properties.condition = 'fixture condition'
$ctx = New-TestContext $fixture
Test-ConfiguredGrant $ctx $fixture.test.project $fixture.test.principal $catalog.actions.ProjectAssets 'test'
Assert-True ($ctx.Checks[0].status -eq 'Unknown') 'Conditional grant cannot pass'
$fixture.responses[$assignmentKey].Data.value[0].properties.Remove('condition')
$fixture.responses["$($fixture.test.sub)/providers/Microsoft.Authorization/denyAssignments"] = @{ Code = 403 }
$ctx = New-TestContext $fixture
Test-ConfiguredGrant $ctx $fixture.test.project $fixture.test.principal $catalog.actions.ProjectAssets 'test'
Assert-True ($ctx.Checks[0].status -eq 'Unknown') 'Inaccessible ancestor deny evidence is Unknown'
$fixture.responses[$assignmentKey] = @{ Code = 403 }
$ctx = New-TestContext $fixture
Test-ConfiguredGrant $ctx $fixture.test.project $fixture.test.principal $catalog.actions.ProjectAssets 'test'
Assert-True ($ctx.Checks[0].status -eq 'Unknown') 'Limited Reader visibility is not absent grant'
$fixture = New-TopologyFixture $topologies[0]
$fixture.responses["$($fixture.test.project)/providers/Microsoft.Authorization/denyAssignments"].Data.value = @(@{ id = '/fixture-deny' })
$ctx = New-TestContext $fixture
Test-ConfiguredGrant $ctx $fixture.test.project $fixture.test.principal $catalog.actions.ProjectAssets 'test'
Assert-True ($ctx.Checks[0].status -eq 'Unknown') 'Visible deny is uncertainty without a deny evaluator'

$fixture = New-TopologyFixture $topologies[0]
$assignmentKey = "$($fixture.test.rg)/providers/Microsoft.Authorization/roleAssignments"
$conditional = ($fixture.responses[$assignmentKey].Data.value[0] | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable)
$conditional.id += '-conditional'
$conditional.properties.condition = 'fixture-only-condition'
$fixture.responses[$assignmentKey].Data.value += $conditional
$ctx = New-TestContext $fixture 'redundant-conditional'
Test-ConfiguredGrant $ctx $fixture.test.storage $fixture.test.principal $catalog.actions.Blob 'test'
Assert-True ($ctx.Checks[0].status -eq 'Passed' -and !$ctx.Checks[0].observed.conditionalOrDefinitionUncertainty) 'Additional conditional allow cannot revoke complete unconditional Blob grant'
Assert-True ($ctx.Checks[0].observed.assignments.Count -eq 2) 'Conditional assignment remains visible as metadata'
$denyList = "$($fixture.test.sub)/providers/Microsoft.Authorization/denyAssignments"
$deny = @{
    id = "$($fixture.test.rg)/providers/Microsoft.Authorization/denyAssignments/88888888-8888-8888-8888-888888888888"
    properties = @{
        scope = $fixture.test.rg; principals = @(@{ id = '00000000-0000-0000-0000-000000000000'; type = 'SystemDefined' })
        excludePrincipals = @(); doNotApplyToChildScopes = $false
        permissions = @(@{ actions = @('*/write','*/delete'); notActions = @(); dataActions = @(); notDataActions = @() })
    }
}
$fixture.responses[$denyList].Data.value = @($deny)
$ctx = New-TestContext $fixture 'management-only-deny'
Test-ConfiguredGrant $ctx $fixture.test.storage $fixture.test.principal $catalog.actions.Blob 'test'
Assert-True ($ctx.Checks[0].status -eq 'Passed') 'Management-only deny does not deny Blob dataActions'
Assert-True ($ctx.Checks[0].observed.denyEvidence.ignored[0].reasons[0] -eq 'NoMatchingPermissionInSelectedChannel') 'Report explains channel-irrelevant deny'
$deny.properties.permissions[0].dataActions = @('*')
$deny.properties.scope = "$($fixture.test.sub)/resourceGroups/unrelated-insights-managed"
$ctx = New-TestContext $fixture 'unrelated-deny'
Test-ConfiguredGrant $ctx $fixture.test.storage $fixture.test.principal $catalog.actions.Blob 'test'
Assert-True ($ctx.Checks[0].status -eq 'Passed') 'Subscription list descendant deny on unrelated RG is irrelevant'
Assert-True ($ctx.Checks[0].observed.denyEvidence.ignored[0].scope -eq $deny.properties.scope) 'Ignored deny ID and scope retained'
$deny.properties.scope = "$($fixture.test.project)/connections/unrelated-child"
Assert-True (!(Get-DenyRelevance $deny $fixture.test.project $fixture.test.principal $catalog.actions.ProjectAssets).relevant) 'Deny on descendant cannot deny its ancestor'
$deny.properties.scope = $fixture.test.rg
$deny.properties.doNotApplyToChildScopes = $true
Assert-True (!(Get-DenyRelevance $deny $fixture.test.storage $fixture.test.principal $catalog.actions.Blob).relevant) 'Child-scope opt-out is respected'
$deny.properties.doNotApplyToChildScopes = $false
$deny.properties.principals = @(@{id='99999999-9999-9999-9999-999999999999';type='ServicePrincipal'})
Assert-True (!(Get-DenyRelevance $deny $fixture.test.storage $fixture.test.principal $catalog.actions.Blob).relevant) 'Different explicit service principal does not apply'
$deny.properties.principals[0].type = 'Group'
$ctx = New-TestContext $fixture 'group-deny'
Test-ConfiguredGrant $ctx $fixture.test.storage $fixture.test.principal $catalog.actions.Blob 'test'
Assert-True ($ctx.Checks[0].status -eq 'Unknown') 'Potential group membership remains Unknown'
Assert-True ('PrincipalOrGroupMembershipUnknown' -in $ctx.Checks[0].observed.denyEvidence.relevant[0].reasons) 'Relevant deny explains membership uncertainty'
$deny.properties.principals = @(@{id=$fixture.test.principal;type='ServicePrincipal'})
$deny.properties.excludePrincipals = @(@{id=$fixture.test.principal;type='ServicePrincipal'})
Assert-True (!(Get-DenyRelevance $deny $fixture.test.storage $fixture.test.principal $catalog.actions.Blob).relevant) 'Explicit principal exclusion is respected'
$deny.properties.excludePrincipals = @()
$deny.properties.permissions[0].notDataActions = @('Microsoft.Storage/*')
Assert-True (!(Get-DenyRelevance $deny $fixture.test.storage $fixture.test.principal $catalog.actions.Blob).relevant) 'Deny notDataActions exclusion is respected'
$deny.properties.permissions += @{ dataActions = @($catalog.actions.Blob.values[0]); notDataActions = @() }
$ctx = New-TestContext $fixture 'relevant-deny'
Test-ConfiguredGrant $ctx $fixture.test.storage $fixture.test.principal $catalog.actions.Blob 'test'
Assert-True ($ctx.Checks[0].status -eq 'Unknown') 'Matching deny in second permission block remains Unknown'
Assert-True ($ctx.Checks[0].observed.denyEvidence.relevant[0].matchingActions[0] -eq $catalog.actions.Blob.values[0]) 'Relevant deny action is reported'
$deny.properties.conditionPresent = $true
Assert-True ('DenyConditionNotEvaluated' -in (Get-DenyRelevance $deny $fixture.test.storage $fixture.test.principal $catalog.actions.Blob).reasons) 'Deny conditions retain uncertainty'
$deny.properties.scope = '/providers/Microsoft.Management/managementGroups/fixture-group'
Assert-True ('ScopeInheritanceUnknown' -in (Get-DenyRelevance $deny $fixture.test.storage $fixture.test.principal $catalog.actions.Blob).reasons) 'Unknown management-group ancestry is not dismissed as disjoint'

$fixture = New-TopologyFixture $topologies[0]
$fixture.responses[$fixture.test.storage] = @{ Code = 403 }
$ctx = New-TestContext $fixture
$options = New-TestOptions $fixture @('Core','Models','Traces')
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'storage.resource')[0].status -eq 'Unknown') 'Dependency403 remains Unknown'
Assert-True ((Find-Check $ctx 'model.deployment')[0].status -eq 'Passed') 'Continue independent model checks after403'
Assert-True ((Find-Check $ctx 'monitoring.component')[0].resource -eq $fixture.test.insights) 'Resolve alias to actual Insights ARM ID'
Assert-True ((Find-Check $ctx 'monitoring.workspace')[0].resource -eq $fixture.test.workspace) 'Resolve cross-RG backing workspace'
$fixture.responses[$fixture.test.storage] = @{ Code = 404 }
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture) $catalog
Assert-True ((Get-Outcome $ctx.Checks).exitCode -eq 1) 'Proven missing resource yields exit1'

foreach ($topology in $topologies) {
    $fixture = New-TopologyFixture $topology
    $name = "$($topology.name)-traces"
    $ctx = New-TestContext $fixture $name
    Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture @('Core','Traces')) $catalog
    if ($topology.monitoring) {
        Assert-True ((Find-Check $ctx 'monitoring.connection')[0].status -eq 'Passed') 'Actual ARM AppInsights category is selected'
        Assert-True ((Find-Check $ctx 'monitoring.connection')[0].observed.category -eq 'AppInsights') 'Actual category is preserved in metadata'
        Assert-True ((Find-Check $ctx 'monitoring.component')[0].resource -eq $fixture.test.insights) 'AppInsights resolves actual component, not alias'
        Assert-True ((Find-Check $ctx 'monitoring.workspace')[0].status -eq 'Observed') 'AppInsights backing Log Analytics metadata is inventory'
        Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Passed') 'Resource-centric trace configured-grant assessment executes'
        $expectedAuth = if ($topology.location -eq 'koreacentral') {'ProjectManagedIdentity'} else {'ApiKey'}
        Assert-True ((Find-Check $ctx 'monitoring.connection')[0].observed.authType -eq $expectedAuth) 'Monitoring auth metadata remains unchanged'
    }
    else {
        Assert-True ((Find-Check $ctx 'monitoring.connection')[0].status -eq 'Unknown') 'Older15a has no invented monitoring dependency'
        Assert-True (!(Find-Check $ctx 'monitoring.workspace').Count) 'No backing workspace invented for a topology without monitoring'
    }
    $reportPath = Join-Path $OutputDirectory $name
    $output = & (Join-Path $PSHOME $(if ($IsWindows) {'pwsh.exe'} else {'pwsh'})) -NoProfile -File (Join-Path $scripts 'Invoke-VNetProjectDiagnostics.ps1') `
        -ProjectResourceId $fixture.test.project -EvaluationCallerObjectId $fixture.test.principal -Profiles Traces `
        -FixturePath (Join-Path $OutputDirectory "$name.fixture.json") -OutputDirectory $reportPath
    $expectedExit = if ($topology.monitoring) {0} else {2}
    Assert-True ($LASTEXITCODE -eq $expectedExit) "Traces CLI produces expected exit for $name"
    $json = Get-Content (Join-Path $reportPath 'diagnostics.json') -Raw
    $markdown = Get-Content (Join-Path $reportPath 'diagnostics.md') -Raw
    Assert-True (($json + $markdown + ($output -join ' ')) -notmatch 'ApplicationInsightsConnectionString|fixture-sensitive-monitoring-sentinel') 'Monitoring connection string is absent from both reports and stdout'
}
$fixture = New-TopologyFixture $topologies[0]
$ctx = New-TestContext $fixture 'interactive-trace-mi'
$options = New-TestOptions $fixture @('Core','Traces')
$options.Caller = ''
Invoke-ConfigurationAssessment $ctx $options $catalog
$traceGrant = (Find-Check $ctx 'rbac.trace.intendedIdentity')[0]
Assert-True ($traceGrant.status -eq 'Passed' -and $traceGrant.principal -eq $fixture.test.principal) 'Interactive Traces with no caller assesses known project MI'
Assert-True ($traceGrant.observed.queryApi -eq 'QueryResourceAsync' -and $traceGrant.resource -eq $fixture.test.insights) 'Resource-context assessment model and component scope are explicit'
Assert-True ($traceGrant.observed.principalSource -match '^Tool configuration: discovered project managed identity;') 'Trace identity describes the tool assessment choice'
Assert-True ((Find-Check $ctx 'rbac.assets.evaluationCaller')[0].status -eq 'NotAssessed') 'Known trace PMI does not substitute the omitted optional asset caller'
Assert-True ((Find-Check $ctx 'monitoring.component')[0].observed.privateLinkScopes.Count -eq 0) 'Missing monitoring associations produce empty array, not null placeholder'
Assert-True ((Find-Check $ctx 'monitoring.queryPathCoverage')[0].status -eq 'NotAssessed') 'Public-enabled query metadata does not claim a tested runtime path'
Assert-True (!(Find-Check $ctx 'monitoring.queryPathCoverage')[0].observed.runtimeReachabilityTested) 'Public metadata also retains untested runtime boundary'
$options.Caller = '99999999-9999-9999-9999-999999999999'
$ctx = New-TestContext $fixture 'trace-caller-separation'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].principal -eq $fixture.test.principal) 'Explicit different caller cannot replace the project identity selected for trace assessment'
$fixture.responses[$fixture.test.project].Data.identity.principalId = ''
$ctx = New-TestContext $fixture 'trace-missing-pmi'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Unknown' -and !(Find-Check $ctx 'rbac.trace.intendedIdentity')[0].principal) 'Missing project MI is not replaced by an explicit caller'
$fixture = New-TopologyFixture $topologies[1]
$ctx = New-TestContext $fixture 'private-monitoring'
$options = New-TestOptions $fixture @('Core','Traces')
$options.Caller = ''
Invoke-ConfigurationAssessment $ctx $options $catalog
$componentCheck = (Find-Check $ctx 'monitoring.component')[0]
Assert-True ($componentCheck.status -eq 'Observed' -and $componentCheck.expected -match 'metadata only') 'Component inventory is explicitly ARM discovery only'
Assert-True ($componentCheck.observed.privateLinkScopes.Count -eq 1 -and $componentCheck.observed.privateLinkScopes[0] -match '/privatelinkscopes/fixture-ampls/scopedresources/') 'Pascal-case PrivateLinkScopedResources ResourceId is preserved'
Assert-True ($componentCheck.observed.privateLinkAssociations[0].scopeId -eq 'abababab-abab-abab-abab-abababababab') 'ScopeId is safely preserved'
$pathCheck = (Find-Check $ctx 'monitoring.queryPathCoverage')[0]
Assert-True (!$pathCheck.required -and $pathCheck.status -eq 'NotAssessed' -and $pathCheck.classification -eq 'Coverage') 'Unimplemented private monitoring path is explicit coverage, not a health failure'
Assert-True ($pathCheck.observed.reason -eq 'PrivateMonitoringQueryPathNotAssessed') 'Private monitoring uncertainty is actionable evidence'
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].principal -eq $fixture.test.principal) 'ApiKey monitoring connection does not change trace-query PMI'
Assert-True (!(Find-Check $ctx 'rbac.model.intendedIdentity').Count) 'Trace query does not require model API-key authorization'
Assert-True (!@($ctx.Requests | Where-Object { $_ -match '/privatelinkscopes/|dataCollection|/query[?]' }).Count) 'No AMPLS/DCE/DCR traversal or query is introduced'
$lowercaseLinks = @(Get-MonitoringPrivateLinks @{ privateLinkScopedResources = @(@{ resourceId = '/fixture/ampls'; scopeId = 'fixture-scope' }) })
Assert-True ($lowercaseLinks.Count -eq 1 -and $lowercaseLinks[0].resourceId -eq '/fixture/ampls') 'Lowercase private-link metadata normalizes without duplication'
Assert-True (@(Get-MonitoringPrivateLinks @{ PrivateLinkScopedResources = @($null) }).Count -eq 0) 'Null private-link elements do not produce placeholders'

$fixture = New-TopologyFixture $topologies[0]
$componentScope = $fixture.test.insights
$workspaceScope = $fixture.test.workspace
$fixture.responses["$($fixture.test.rg)/providers/Microsoft.Authorization/roleAssignments"].Data.value = @()
$fixture.responses["$workspaceScope/providers/Microsoft.Authorization/roleAssignments"].Data.value = @()
$fixture.responses["$componentScope/providers/Microsoft.Authorization/roleAssignments"].Data.value = @(@{
    id = "$componentScope/providers/Microsoft.Authorization/roleAssignments/cccccccc-cccc-cccc-cccc-cccccccccccc"
    properties = @{ scope = $componentScope; principalId = $fixture.test.principal; roleDefinitionId = $fixture.test.role }
})
$fixture.responses[$fixture.test.role].Data.properties.permissions = @(@{ actions = @('Microsoft.Insights/logs/*/read'); notActions = @(); dataActions = @() })
$ctx = New-TestContext $fixture 'component-only-grant'
$options = New-TestOptions $fixture @('Core','Traces')
$options.Caller = ''
Invoke-ConfigurationAssessment $ctx $options $catalog
$traceGrant = (Find-Check $ctx 'rbac.trace.intendedIdentity')[0]
Assert-True ($traceGrant.status -eq 'Passed' -and $traceGrant.observed.configuredGrantScope -eq $componentScope) 'Legitimate component-only resource-context grants suffice without workspace grants'
Assert-True (!(Find-Check $ctx 'rbac.trace.workspaceCandidate')[0].required) 'Workspace candidate is not an unconditional prerequisite'
$unused = (Find-Check $ctx 'rbac.trace.workspaceCandidate')[0]
Assert-True ($unused.classification -eq 'Inventory' -and $unused.status -eq 'NotApplicable' -and $unused.severity -eq 'Info' -and !$unused.observed.assessed) 'Sufficient resource path records an unused alternative, never fake workspace Passed'
Assert-True (!@($ctx.Requests | Where-Object { $_ -like "*$workspaceScope/providers/Microsoft.Authorization/*" }).Count) 'Unused workspace role and deny endpoints are not requested'
Assert-True ('rbac.trace.workspaceCandidate' -notin (Get-Outcome $ctx.Checks).actionableGroups.id) 'Unused alternative cannot create actionable noise'
Assert-True ('rbac.trace.workspaceCandidate' -notin (Get-Outcome $ctx.Checks).notAssessed) 'Unused alternative is not incomplete coverage'
Assert-True ((Find-Check $ctx 'rbac.trace.resourceCandidate')[0].observed.actions[0] -eq 'Microsoft.Insights/logs/AppRequests/read') 'Resource-context read uses management actions, not workspace-query or model channel'
$fixture.responses[$workspaceScope].Data.properties.features.enableLogAccessUsingOnlyResourcePermissions = $false
$ctx = New-TestContext $fixture 'workspace-required-mode'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Unknown') 'Workspace-required mode does not certify component-only grants'
Assert-True (@($ctx.Requests | Where-Object { $_ -like "*$workspaceScope/providers/Microsoft.Authorization/roleAssignments?*" }).Count -eq 1) 'Workspace-required mode still requests alternative roles'
$fixture.responses[$workspaceScope].Data.properties.features.Remove('enableLogAccessUsingOnlyResourcePermissions')
$ctx = New-TestContext $fixture 'unknown-workspace-mode'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Unknown') 'Missing access-mode evidence keeps component-only grant inconclusive'
Assert-True ((Find-Check $ctx 'rbac.trace.workspaceCandidate')[0].status -eq 'Unknown') 'Unknown policy still assesses necessary workspace alternative'
$fixture.responses[$workspaceScope].Data.properties.features.enableLogAccessUsingOnlyResourcePermissions = $true
$fixture.responses[$fixture.test.role].Data.properties.permissions[0].notActions = @('Microsoft.Insights/logs/AppTraces/read')
$ctx = New-TestContext $fixture 'component-table-exclusion'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Unknown') 'Relevant resource-context table exclusion prevents complete configured-grant coverage'
$fixture = New-TopologyFixture $topologies[0]
$fixture.responses["$($fixture.test.insights)/providers/Microsoft.Authorization/denyAssignments"].Data.value = @(@{
    id = "$($fixture.test.insights)/providers/Microsoft.Authorization/denyAssignments/eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    properties = @{ scope = $fixture.test.insights; principals = @(@{id=$fixture.test.principal;type='ServicePrincipal'})
        permissions = @(@{ actions = @('Microsoft.Insights/logs/*/read'); notActions = @() }) }
})
$ctx = New-TestContext $fixture 'trace-deny-not-overridden'
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture @('Core','Traces')) $catalog
Assert-True ((Find-Check $ctx 'rbac.trace.workspaceCandidate')[0].status -eq 'Passed') 'Fixture has a sufficient workspace permission alternative'
Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Unknown') 'Workspace alternative cannot override a relevant query-resource deny'
foreach ($readCode in @(403,408)) {
    $fixture = New-TopologyFixture $topologies[0]
    $fixture.responses[$fixture.test.workspace].Data.properties.features.enableLogAccessUsingOnlyResourcePermissions = $false
    $fixture.responses["$($fixture.test.workspace)/providers/Microsoft.Authorization/roleAssignments"] = @{Code=$readCode;Data=$null}
    $ctx = New-TestContext $fixture "needed-workspace-$readCode"
    Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture @('Core','Traces')) $catalog
    Assert-True ((Find-Check $ctx 'rbac.trace.workspaceCandidate')[0].status -eq 'Unknown') 'Needed workspace access-denied/timeout evidence is not skipped'
    Assert-True ((Find-Check $ctx 'rbac.trace.intendedIdentity')[0].status -eq 'Unknown' -and (Get-Outcome $ctx.Checks).exitCode -eq 2) 'Necessary fallback gap still makes required trace finding inconclusive'
}

$fixture = New-TopologyFixture $topologies[0]
$monitoringConnection = @($fixture.responses["$($fixture.test.project)/connections"].Data.value | Where-Object { $_.properties.category -eq 'AppInsights' })[0]
$monitoringConnection.properties.category = 'ApplicationInsights'
$monitoringConnection.properties.target = '55555555-5555-5555-5555-555555555555'
$ctx = New-TestContext $fixture 'legacy-monitoring-category'
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture @('Core','Traces')) $catalog
Assert-True ((Find-Check $ctx 'monitoring.component')[0].resource -eq $fixture.test.insights) 'Legacy template ApplicationInsights/AppId target remains supported via metadata ResourceId'

$fixture = New-TopologyFixture $topologies[0]
$modelConnection = @($fixture.responses["$($fixture.test.project)/connections"].Data.value | Where-Object name -eq 'model-alias')[0]
$modelConnection.properties.metadata = @{ ApiType = 'Azure'; ApiVersion = 'fixture'; DeploymentApiVersion = 'fixture' }
$fixture.responses["$($fixture.test.project)/connections"].Data.value += @{
    name = 'model-aad'; properties = @{ category = 'AzureOpenAI'; authType = 'AAD'; target = $modelConnection.properties.target; metadata = @{ ResourceId = $fixture.test.account } }
}
$options = New-TestOptions $fixture @('Core','Models','Graders')
$options.ModelConnection = 'model-alias'
$options.ModelDeployment = 'fixture-model'
$ctx = New-TestContext $fixture 'model-known-account'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'model.connection')[0].status -eq 'Passed') 'Selected APIKey connection without ResourceId resolves exact known account host'
Assert-True ((Find-Check $ctx 'model.connection')[0].observed.targetResolution -eq 'ExactCanonicalHostOfReadAccount') 'Host association source is reported'
Assert-True ((Find-Check $ctx 'model.connection')[0].observed.targetResourceId -eq $fixture.test.account) 'Use existing account ID, never synthesize an ID'
Assert-True ((Find-Check $ctx 'model.deployment')[0].status -eq 'Passed') 'Known-account deployment check executes'
Assert-True ((Find-Check $ctx 'model.authentication')[0].observed.selectedAuthentication -eq 'ApiKey') 'Do not substitute sibling AAD connection authentication'
Assert-True (!(Find-Check $ctx 'rbac.model.intendedIdentity').Count) 'Selected APIKey path does not acquire sibling Entra grant requirements'
$modelConnection.properties.target = 'https://foreignaccount.openai.azure.com/'
$ctx = New-TestContext $fixture 'model-foreign'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'model.connection')[0].status -eq 'Unknown') 'Foreign missing-ID model stays Unknown'
Assert-True (!(Find-Check $ctx 'model.deployment').Count) 'Do not inspect parent deployment as a foreign target fallback'
Assert-True (!@($ctx.Requests | Where-Object { $_ -match 'foreignaccount|/deployments[?]' }).Count) 'No broad discovery or unrelated deployment calls'
$options.ModelConnection = ''
$fixture.responses["$($fixture.test.project)/connections"].Data.value = @($modelConnection)
$ctx = New-TestContext $fixture 'model-foreign-auto'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True (!(Find-Check $ctx 'model.deployment').Count) 'Automatic selection also cannot default a foreign target to parent account'
$modelConnection.properties.target = 'https://fixtureaccount.openai.azure.com/'
$ctx = New-TestContext $fixture 'model-ambiguous'
$otherId = "$($fixture.test.account)-other"
$otherAccount = ($fixture.responses[$fixture.test.account].Data | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable)
$otherAccount.id = $otherId
$ctx.Cache["$otherId|False"] = @{ Code = 200; Data = $otherAccount }
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'model.connection')[0].observed.targetResolution -eq 'AmbiguousReadAccountHost') 'Two already-read account claims for host remain ambiguous'
Assert-True (!(Find-Check $ctx 'model.deployment').Count) 'Ambiguous host does not choose an account'
$modelConnection.properties.metadata.ResourceId = 'invalid-explicit-id'
$ctx = New-TestContext $fixture 'model-invalid-explicit'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'model.connection')[0].status -eq 'Unknown') 'Malformed explicit ResourceId is not silently overridden by host association'
$modelConnection.properties.metadata.Remove('ResourceId')
$modelConnection.properties.target = 'https://fixtureaccount.privatelink.openai.azure.com/'
$ctx = New-TestContext $fixture 'model-alias-target'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'model.connection')[0].status -eq 'Unknown') 'Only original canonical model host can establish missing-ID association'

$fixture = New-TopologyFixture $topologies[0]
$fixture.responses[$fixture.test.account].Data.properties.disableLocalAuth = $true
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture @('Core','Models')) $catalog
Assert-True ((Find-Check $ctx 'model.authentication')[0].status -eq 'Failed') 'APIKey/disableLocalAuth mismatch'
Assert-True (!(Find-Check $ctx 'rbac.model.intendedIdentity').Count) 'APIKey path does not require MI model grant'
$fixture = New-TopologyFixture $topologies[2]
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture @('Core','Traces')) $catalog
Assert-True ((Find-Check $ctx 'monitoring.connection')[0].status -eq 'Unknown') 'Older15a monitoring required only when selected'
$fixture = New-TopologyFixture $topologies[0]
$options = New-TestOptions $fixture
$options.Caller = ''
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'rbac.assets.evaluationCaller')[0].status -eq 'NotAssessed') 'Never substitute operator for omitted optional caller'
Assert-True ((Get-Outcome $ctx.Checks).exitCode -eq 0) 'Healthy Core without optional caller passes selected implemented checks'
$options.Profiles = @('Core','Scheduled')
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'identity.scheduled')[0].principal -eq $fixture.test.principal) 'Scheduled uses project MI'
Assert-True (!(Find-Check $ctx 'rbac.assets.evaluationCaller')[0].required) 'Scheduled does not require unspecified interactive caller'

$zone = "$($fixture.test.rg)/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
$fixture.responses["$zone/A"].Data.value[0].properties.aRecords[0].ipv4Address = '10.0.1.99'
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture) $catalog
Assert-True (@(Find-Check $ctx 'dns.records' | Where-Object status -eq 'Failed').Count -gt 0) 'Proven PE DNS mismatch fails'
$fixture = New-TopologyFixture $topologies[2]
$peGroups = "$($fixture.test.rg)/providers/Microsoft.Network/privateEndpoints/storage/privateDnsZoneGroups"
$fixture.responses[$peGroups].Data.value = @()
$ctx = New-TestContext $fixture
Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture) $catalog
Assert-True (@(Find-Check $ctx 'dns.zoneGroups' | Where-Object status -eq 'Unknown').Count -gt 0) 'Custom DNS without groups is Unknown, not Failed'
$hostsPath = Join-Path $OutputDirectory 'fixture.hosts'
@('127.0.0.1 localhost', '10.0.1.5 fixturestorage.blob.core.windows.net # fixture', '10.0.1.6 unrelated.example') | Set-Content $hostsPath
$overrides = @(Get-HostsOverrides @('fixturestorage.blob.core.windows.net') $hostsPath)
Assert-True ($overrides.Count -eq 1 -and $overrides[0].address -eq '10.0.1.5') 'Hosts file only reports target names'
Assert-True (!(Get-EndpointHost 'https://fixturestorage.blob.core.windows.net/?sig=secret')) 'Reject SAS-bearing endpoint URLs'
Assert-True (!(Get-EndpointHost 'https://evil.example/')) 'Reject unrecognized outbound probe targets'
Assert-True ((Get-EndpointMappingStatus @('20.0.0.1') @('10.0.1.5')) -eq 'Unknown') 'Public answer is a host-path Unknown, not Azure configuration Failed'
Assert-True ((Get-EndpointMappingStatus @('10.0.1.99') @('10.0.1.5')) -eq 'Unknown') 'Private address alone does not prove the right endpoint'
Assert-True ((Get-EndpointMappingStatus @('10.0.1.5') @('10.0.1.5')) -eq 'Passed') 'Exact expected endpoint mapping passes selected host check'
Assert-Throws { Test-LocalNetwork $ctx } 'Fixture cannot run network probes'
Assert-True (@(Wait-NetworkOperation ([Threading.Tasks.Task]::CompletedTask) 1).Count -eq 0) 'Awaited void task emits no console object'
Assert-True (@(Wait-NetworkOperation ([Threading.Tasks.Task]::FromResult('sentinel')) 1).Count -eq 0) 'Awaited generic result is also suppressed'
Assert-Throws { Wait-NetworkOperation ([Threading.Tasks.Task]::FromException([InvalidOperationException]::new('fixture'))) 1 } 'Await failure still propagates to Unknown path handler'
Assert-True (!(Get-KnownPrivateLinkMapping 'custom.privatelink.unrelated.example')) 'Never strip private-link labels on arbitrary hosts'
Assert-True (!(Get-KnownPrivateLinkMapping 'extra.label.privatelink.openai.azure.com')) 'Only exact single-label Azure service mapping is supported'
$aliasContext = New-TestContext (New-TopologyFixture $topologies[0]) 'alias-order'
$peId = "$($fixture.test.rg)/providers/Microsoft.Network/privateEndpoints/foundry"
Add-Endpoint $aliasContext 'https://fixtureaccount.privatelink.openai.azure.com' $fixture.test.account 'account' @('10.0.1.6') -PrivateEndpointId $peId
Assert-True ($aliasContext.Endpoints.Count -eq 0) 'Alias alone does not invent canonical TLS target'
Add-Endpoint $aliasContext 'https://fixtureaccount.openai.azure.com' $fixture.test.account 'model'
Assert-True ($aliasContext.Endpoints['fixtureaccount.openai.azure.com'].expectedIps[0] -eq '10.0.1.6') 'Alias can bind after original canonical host discovery'
$wrongResource = New-TestContext (New-TopologyFixture $topologies[0]) 'alias-resource-mismatch'
Add-Endpoint $wrongResource 'https://fixtureaccount.openai.azure.com' "$($fixture.test.account)-other" 'account'
Add-Endpoint $wrongResource 'https://fixtureaccount.privatelink.openai.azure.com' $fixture.test.account 'account' @('10.0.1.6') -PrivateEndpointId $peId
Assert-True ($wrongResource.Endpoints['fixtureaccount.openai.azure.com'].expectedIps.Count -eq 0) 'Do not attach PE alias IPs to another ARM resource'

$fixture = New-TopologyFixture $topologies[0]
$collection = "$($fixture.test.project)/connections"
$malformed = New-TopologyFixture $topologies[0]
$malformed.responses[$malformed.test.account].Data = $null
$malformedContext = New-TestContext $malformed 'malformed'
Assert-True ((Read-Arm $malformedContext $malformed.test.account).Reason -eq 'InvalidMetadataShape') 'Malformed metadata is Unknown, not a crash'
$fixture.responses[$collection].Data.nextLink = "https://evil.example${collection}?api-version=2025-06-01"
$ctx = New-TestContext $fixture
Assert-True ((Read-Arm $ctx $collection -Collection).Reason -eq 'RejectedPaging') 'Reject hostile paging host'
Assert-True ($ctx.Requests.Count -eq 1) 'No hostile paging request issued'
$fixture.responses[$collection].Data.nextLink = "https://management.azure.com${collection}?api-version=2025-06-01&`$skiptoken=page2"
$fixture.responses[$fixture.responses[$collection].Data.nextLink] = @{Code=200;Data=@{value=@()}}
$ctx = New-TestContext $fixture
Assert-True ((Read-Arm $ctx $collection -Collection).Code -eq 200) 'Safe same-collection paging works'
$fixture.responses[$fixture.responses[$collection].Data.nextLink].Data.nextLink = $fixture.responses[$collection].Data.nextLink
$ctx = New-TestContext $fixture
Assert-True ((Read-Arm $ctx $collection -Collection).Reason -eq 'PagingCycle') 'Paging cycles are bounded'
Assert-True ((Get-Outcome @(@{required=$true;status='NotApplicable'})).exitCode -eq 2) 'Skipped required check cannot pass'
Assert-True ((Get-Outcome @(@{required=$true;status='Warning'})).exitCode -eq 2) 'Required warning is inconclusive'
Assert-True ((Get-Outcome @(@{required=$true;status='Failed'},@{required=$true;status='Unknown'})).exitCode -eq 1) 'Failure takes precedence'
$fake = Join-Path $PSScriptRoot 'Fake-AzureCli.ps1'
$ctx = New-DiagnosticContext '' $fake @()
foreach ($code in @(403,404,503)) {
    $uri = "https://management.azure.com$($fixture.test.account)/projects/failure${code}?api-version=2025-06-01"
    $result = Invoke-CliMetadata $ctx @('rest','--method','get','--url',$uri,'--query',(Get-MetadataProjection 'Resource' $false),'--output','json','--only-show-errors')
    Assert-True ($result.Code -eq $code) "Safe CLI error classification $code"
    Assert-True (($result | ConvertTo-Json) -notmatch 'sensitive-sentinel') 'No raw errors escape transport'
}
Assert-Throws { Invoke-CliMetadata $ctx @('account','set','--subscription','fixture') } 'CLI transport rejects subscription mutation'
Assert-Throws { Invoke-CliMetadata $ctx @('storage','account','keys','list') } 'CLI transport rejects keys'
Assert-Throws { Invoke-CliMetadata $ctx @('rest','--method','get','--url',$validUri,'--query','@','--output','json','--only-show-errors') } 'CLI transport rejects unprojected payloads'
Assert-Throws { Invoke-CliMetadata $ctx @('rest','--method','get','--url',$validUri,'--query',(Get-MetadataProjection 'Resource' $false),'--output','json','--only-show-errors','--debug') } 'CLI transport rejects appended debug flags'
$invalidOutput = & (Join-Path $PSHOME $(if ($IsWindows) {'pwsh.exe'} else {'pwsh'})) -NoProfile -File (Join-Path $scripts 'Invoke-VNetProjectDiagnostics.ps1') -ProjectResourceId invalid
Assert-True ($LASTEXITCODE -eq 3) 'Invalid invocation exits3 without Azure'
$projections = @()
foreach ($kind in @('Resource','Connection','Authorization','Role','Deployment','Capability','PrivateConnection','Storage','Monitoring','Network','Dependency')) {
    foreach ($collection in @($true, $false)) {
        $projections += @{ kind = $kind; collection = $collection; query = Get-MetadataProjection $kind $collection }
    }
}
$projections | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $OutputDirectory 'projections.json')
. (Join-Path $PSScriptRoot 'Test-NoiseClassification.ps1')
. (Join-Path $PSScriptRoot 'Test-AzurePowerShell.ps1')
Write-Output "PASS: $script:assertions offline assertions. Artifacts: $OutputDirectory"
