# Runs within Test-Diagnostics.ps1, using its offline fixtures and assertions.
$fixture = New-TopologyFixture $topologies[0]
$options = New-TestOptions $fixture
$options.Caller = ''
$ctx = New-TestContext $fixture 'noise-healthy-core'
Invoke-ConfigurationAssessment $ctx $options $catalog
$outcome = Get-Outcome $ctx.Checks
Assert-True ($outcome.exitCode -eq 0 -and $outcome.coverageStatus -eq 'Incomplete') 'Healthy Core passes implemented checks with explicit coverage incompleteness'
Assert-True ($outcome.status -eq 'Passed for selected implemented checks') 'Summary never claims blanket project health'
Assert-True ($outcome.actionableGroups.Count -eq 0) 'No action item is manufactured from omitted caller or runtime coverage'
$caller = (Find-Check $ctx 'rbac.assets.evaluationCaller')[0]
Assert-True ($caller.classification -eq 'Coverage' -and $caller.severity -eq 'Info' -and !$caller.required) 'Omitted caller is informational unassessed coverage'
$options.Caller = '99999999-9999-9999-9999-999999999999'
$ctx = New-TestContext $fixture 'noise-explicit-caller'
Invoke-ConfigurationAssessment $ctx $options $catalog
$caller = (Find-Check $ctx 'rbac.assets.evaluationCaller')[0]
Assert-True ($caller.classification -eq 'Finding' -and $caller.status -eq 'Unknown' -and $caller.required) 'Explicit caller without sufficient evidence remains required Unknown'
Assert-True ((Get-Outcome $ctx.Checks).exitCode -eq 2) 'Explicit caller gaps still block selected implemented result'
$options.Caller = ''
$fixture.responses[$fixture.test.storage] = @{Code=403;Data=$null}
$ctx = New-TestContext $fixture 'noise-required-403'
Invoke-ConfigurationAssessment $ctx $options $catalog
$outcome = Get-Outcome $ctx.Checks
Assert-True ($outcome.exitCode -eq 2 -and 'storage.resource' -in $outcome.actionableGroups.id) 'Actual required storage403 remains visible and inconclusive'
Assert-True ((Find-Check $ctx 'storage.resource')[0].severity -eq 'Warning') '403 is not relabeled optional coverage'
$fixture.responses[$fixture.test.storage] = @{Code=408;Data=$null}
$ctx = New-TestContext $fixture 'noise-required-timeout'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Get-Outcome $ctx.Checks).exitCode -eq 2 -and (Find-Check $ctx 'storage.resource')[0].observed.readStatus -eq 408) 'A required metadata timeout remains visible and inconclusive'

$fixture = New-TopologyFixture $topologies[1]
$ctx = New-TestContext $fixture 'noise-private-traces'
$options = New-TestOptions $fixture @('Core','Traces','Agent')
$options.Caller = ''
$options.PrivilegedTraceContent = $true
Invoke-ConfigurationAssessment $ctx $options $catalog
foreach ($id in @('monitoring.queryPathCoverage','monitoring.privilegedCoverage','agent.coverage')) {
    $check = (Find-Check $ctx $id)[0]
    Assert-True ($check.classification -eq 'Coverage' -and $check.status -eq 'NotAssessed' -and $check.severity -eq 'Info' -and !$check.required) "$id is an implementation limit, not a prerequisite failure"
}
Assert-True ((Get-Outcome $ctx.Checks).exitCode -eq 0) 'Unimplemented selected scenario coverage alone does not fail actual implemented checks'
$fixture.responses[$fixture.test.workspace].Data.properties.Remove('publicNetworkAccessForQuery')
$ctx = New-TestContext $fixture 'noise-required-query-metadata'
Invoke-ConfigurationAssessment $ctx $options $catalog
Assert-True ((Find-Check $ctx 'monitoring.queryPolicy')[0].required -and (Get-Outcome $ctx.Checks).exitCode -eq 2) 'Missing actual required query policy is not hidden as an implementation limit'

$fixture = New-TopologyFixture $topologies[0]
$ctx = New-TestContext $fixture 'noise-inventory'
$attachments = $fixture.responses["$($fixture.test.vnet)/subnets/agents"].Data.properties
1..3 | ForEach-Object { Test-NetworkAttachments $ctx $attachments }
$nsgRows = @($ctx.Checks | Where-Object { $_.id -eq 'network.attachments' -and $_.observed.kind -eq 'networkSecurityGroup' })
Assert-True ($nsgRows.Count -eq 1 -and $nsgRows[0].status -eq 'Observed' -and $nsgRows[0].classification -eq 'Inventory') 'Repeated NSG observation has one inventory row'
Assert-True ((Get-Outcome $ctx.Checks).findingCount -eq 0 -and (Get-Outcome $ctx.Checks).inventoryCount -eq 2) 'NSG/UDR inventory does not inflate health findings'
$ctx = New-TestContext $fixture 'noise-host-context'
Add-LocalHostContext $ctx
$hostContext = (Find-Check $ctx 'endpoint.hostContext')[0]
Assert-True ($hostContext.status -in @('Observed','NotAssessed') -and $hostContext.severity -eq 'Info') 'Actual local host-context collection never manufactures a project warning'
Assert-True (!$hostContext.required) 'Local interface inventory is not a prerequisite'
& {
    # Exercise the default network orchestrator without contacting any endpoint.
    $fixture = New-TopologyFixture $topologies[0]
    $ctx = New-TestContext $fixture 'noise-network-default'
    Invoke-ConfigurationAssessment $ctx (New-TestOptions $fixture) $catalog
    $ctx.Offline = $false
    $script:dispatchedHosts = [Collections.Generic.List[string]]::new()
    function Get-HostsOverrides { param($Names,$Path) return @() }
    function Test-LocalEndpoint {
        param($Context,$Endpoint,[int]$TimeoutSeconds=5,[switch]$AdvancedNetworkDetails)
        Assert-True (!$AdvancedNetworkDetails) 'Default orchestration does not request DNS-only/route detail'
        $script:dispatchedHosts.Add($Endpoint.hostName)
    }
    Test-LocalNetwork $ctx
    Assert-True ($script:dispatchedHosts.Count -eq 4 -and !@($script:dispatchedHosts | Where-Object { $_ -match '\.privatelink\.' }).Count) 'Default dispatch preserves exactly four canonical probe hosts'
    Assert-True ((Find-Check $ctx 'endpoint.advancedDetails')[0].status -eq 'NotAssessed') 'Default omits advanced detail with one explicit coverage record'
    Assert-True (!(Find-Check $ctx 'endpoint.dnsOnly').Count -and !(Find-Check $ctx 'endpoint.route').Count) 'No per-host optional-platform noise in default mode'
    Assert-True (!(Find-Check $ctx 'endpoint.hostContext' | Where-Object severity -eq 'Warning').Count) 'Default host-context result does not manufacture a health warning'
}

# Simulate Linux optional-command availability without running DNS or route probes.
& {
    function Get-Command { param($Name, $ErrorAction) return $null }
    $ctx = New-TestContext $fixture 'noise-linux-optional'
    Test-AdvancedNetworkEvidence $ctx 'fixtureaccount.openai.azure.com' @('10.0.1.6')
    Assert-True ($ctx.Checks.Count -eq 2) 'Optional advanced helper reports both unsupported capabilities'
    foreach ($check in $ctx.Checks) {
        Assert-True ($check.status -eq 'NotAssessed' -and $check.classification -eq 'Coverage' -and $check.severity -eq 'Info') 'Unsupported Linux detail is informational, not Unknown health'
    }
    Assert-True ((Get-Outcome $ctx.Checks).actionableGroups.Count -eq 0) 'Unsupported optional commands do not produce warning summary groups'
}
# A supported command which fails is different from an unsupported command.
& {
    function Get-Command { param($Name, $ErrorAction) return @{Name=$Name} }
    function Start-Job { param($ScriptBlock, $ArgumentList) return @{State='Failed'} }
    function Wait-Job { param($Job, $Timeout) return $Job }
    function Stop-Job { param($Job) }
    function Remove-Job { param($Job, [switch]$Force) }
    $ctx = New-TestContext $fixture 'noise-advanced-failure'
    Test-AdvancedNetworkEvidence $ctx 'fixtureaccount.openai.azure.com' @('10.0.1.6')
    Assert-True (@($ctx.Checks | Where-Object { $_.status -eq 'Unknown' -and $_.classification -eq 'Inventory' }).Count -eq 2) 'Attempted optional probe failures retain explicit Unknown evidence'
    Assert-True ((Get-Outcome $ctx.Checks).actionableGroups.Count -eq 2) 'Actual optional probe errors remain visible, though nonblocking'
}

foreach ($form in @('missing','null','empty')) {
    $fixture = New-TopologyFixture $topologies[0]
    $dnsOptions = $fixture.responses[$fixture.test.vnet].Data.properties.dhcpOptions
    switch ($form) {
        missing { $dnsOptions.Remove('dnsServers') }
        null { $dnsOptions.dnsServers = $null }
        empty { $dnsOptions.dnsServers = @() }
    }
    $ctx = New-TestContext $fixture "dns-servers-$form"
    $accountRead = Read-Arm $ctx $fixture.test.account
    $topology = Test-SubnetConfiguration $ctx $accountRead $fixture.test.account
    $resolver = (Find-Check $ctx 'network.resolvers')[0]
    Assert-True ($topology.CustomDns -eq $false -and $resolver.observed.dnsServers.Count -eq 0 -and $resolver.observed.resolverType -eq 'AzureProvided') "Readable $form DNS-server collection is Azure-provided DNS"

    $peId = "$($fixture.test.rg)/providers/Microsoft.Network/privateEndpoints/storage"
    $groupId = "$peId/privateDnsZoneGroups"
    $record = $fixture.responses[$groupId].Data.value[0].properties.privateDnsZoneConfigs[0].properties.recordSets[0]
    switch ($form) {
        missing { $record.Remove('ipAddresses') }
        null { $record.ipAddresses = $null }
        empty { $record.ipAddresses = @() }
    }
    # Exercise single-address fallback, not just a copy of the original expression.
    $fixture.responses[$peId].Data.properties.customDnsConfigs[0].ipAddresses = $null
    $ctx = New-TestContext $fixture "dns-record-$form"
    Test-PrivateEndpointConfiguration $ctx $fixture.test.storage 'blob' @{VnetId=$fixture.test.vnet;CustomDns=$false}
    $recordCheck = (Find-Check $ctx 'dns.records')[0]
    Assert-True ($recordCheck.status -eq 'Passed' -and $recordCheck.observed.records[0].expectedIps[0] -eq '10.0.1.5') "Actual DNS check uses sole PE address for $form record IP array"
}
$fixture = New-TopologyFixture $topologies[0]
$fixture.responses[$fixture.test.vnet] = @{Code=403}
$ctx = New-TestContext $fixture 'dns-unreadable-vnet'
$topology = Test-SubnetConfiguration $ctx (Read-Arm $ctx $fixture.test.account) $fixture.test.account
Assert-True ($null -eq $topology.CustomDns -and (Find-Check $ctx 'network.resolvers')[0].status -eq 'Unknown') 'Unreadable resolver configuration is not guessed to be Azure DNS'
$fixture.responses[$fixture.test.vnet] = @{Code=200;Data=@{id=$fixture.test.vnet}}
$ctx = New-TestContext $fixture 'dns-missing-required-vnet-properties'
$topology = Test-SubnetConfiguration $ctx (Read-Arm $ctx $fixture.test.account) $fixture.test.account
Assert-True ($null -eq $topology.CustomDns -and (Find-Check $ctx 'network.resolvers')[0].status -eq 'Unknown') 'A missing required properties object is not silently treated as readable default DNS'

$fixture = New-TopologyFixture $topologies[0]
$peId = "$($fixture.test.rg)/providers/Microsoft.Network/privateEndpoints/foundry"
$config = $fixture.responses["$peId/privateDnsZoneGroups"].Data.value[0].properties.privateDnsZoneConfigs[0]
$config.properties.recordSets[0].ipAddresses = $null
$ctx = New-TestContext $fixture 'dns-multihost-exact'
Test-PrivateEndpointConfiguration $ctx $fixture.test.account 'account' @{VnetId=$fixture.test.vnet;CustomDns=$false}
$recordCheck = @(Find-Check $ctx 'dns.records' | Where-Object { $_.resource -like '*/privatelink.services.ai.azure.com' })[0]
Assert-True ($recordCheck.status -eq 'Passed' -and $recordCheck.observed.records[0].expectedIps.Count -eq 1 -and $recordCheck.observed.records[0].expectedIps[0] -eq '10.0.1.4') 'Multi-host NIC fallback uses exact PE FQDN mapping, never all NIC IPs'
$fixture.responses[$peId].Data.properties.customDnsConfigs[0].ipAddresses = $null
$ctx = New-TestContext $fixture 'dns-multihost-insufficient'
Test-PrivateEndpointConfiguration $ctx $fixture.test.account 'account' @{VnetId=$fixture.test.vnet;CustomDns=$false}
$recordCheck = @(Find-Check $ctx 'dns.records' | Where-Object { $_.resource -like '*/privatelink.services.ai.azure.com' })[0]
Assert-True ($recordCheck.status -eq 'Unknown' -and $recordCheck.observed.records[0].expectedIps.Count -eq 0) 'Insufficient multi-host mapping is Unknown rather than false mismatch'
$fixture = New-TopologyFixture $topologies[0]
$zone = "$($fixture.test.rg)/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
$fixture.responses["$zone/A"].Data.value[0].properties.aRecords += @{ipv4Address='10.0.2.5'}
$ctx = New-TestContext $fixture 'dns-additional-pe-address'
Test-PrivateEndpointConfiguration $ctx $fixture.test.storage 'blob' @{VnetId=$fixture.test.vnet;CustomDns=$false}
Assert-True ((Find-Check $ctx 'dns.records')[0].status -eq 'Unknown') 'Additional addresses potentially belonging to other approved PEs are not automatically failures'
$peId = "$($fixture.test.rg)/providers/Microsoft.Network/privateEndpoints/storage"
$secondPe = "$peId-secondary"
$nicId = "$($fixture.test.rg)/providers/Microsoft.Network/networkInterfaces/storage-secondary"
$fixture.responses[$secondPe] = ($fixture.responses[$peId] | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable)
$fixture.responses[$secondPe].Data.id = $secondPe
$fixture.responses[$secondPe].Data.properties.networkInterfaces = @(@{id=$nicId})
$fixture.responses[$secondPe].Data.properties.customDnsConfigs[0].ipAddresses = @('10.0.2.5')
$fixture.responses[$nicId] = @{Code=200;Data=@{properties=@{ipConfigurations=@(@{properties=@{privateIPAddress='10.0.2.5'}})}}}
$fixture.responses["$secondPe/privateDnsZoneGroups"] = ($fixture.responses["$peId/privateDnsZoneGroups"] | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable)
$fixture.responses["$secondPe/privateDnsZoneGroups"].Data.value[0].properties.privateDnsZoneConfigs[0].properties.recordSets[0].ipAddresses = @('10.0.2.5')
$fixture.responses["$($fixture.test.storage)/privateEndpointConnections"].Data.value += @{
    properties=@{privateEndpoint=@{id=$secondPe};privateLinkServiceConnectionState=@{status='Approved'}}
}
$ctx = New-TestContext $fixture 'dns-two-approved-pes'
Test-PrivateEndpointConfiguration $ctx $fixture.test.storage 'blob' @{VnetId=$fixture.test.vnet;CustomDns=$false}
Assert-True (@(Find-Check $ctx 'dns.records' | Where-Object status -eq 'Failed').Count -eq 0 -and (Find-Check $ctx 'dns.records').Count -eq 2) 'Two verified approved PEs sharing hostname never cause strict-set false failures'
$fixture = New-TopologyFixture $topologies[0]
$fixture.responses["$zone/A"].Data.value[0].properties.aRecords = @(@{ipv4Address='10.0.1.99'})
$ctx = New-TestContext $fixture 'dns-proven-mismatch'
Test-PrivateEndpointConfiguration $ctx $fixture.test.storage 'blob' @{VnetId=$fixture.test.vnet;CustomDns=$false}
Assert-True ((Find-Check $ctx 'dns.records')[0].status -eq 'Failed' -and (Get-Outcome $ctx.Checks).exitCode -eq 1) 'A real contradictory DNS record still fails required findings'

$fixture = New-TopologyFixture $topologies[0]
$ctx = New-TestContext $fixture 'schema2-default'
$fixturePath = Join-Path $OutputDirectory 'schema2-default.fixture.json'
$reportPath = Join-Path $OutputDirectory 'schema2-default'
$output = & (Join-Path $PSHOME $(if ($IsWindows) {'pwsh.exe'} else {'pwsh'})) -NoProfile -File (Join-Path $scripts 'Invoke-VNetProjectDiagnostics.ps1') `
    -ProjectResourceId $fixture.test.project -FixturePath $fixturePath -OutputDirectory $reportPath
Assert-True ($LASTEXITCODE -eq 0) 'Actual CLI default Core without caller can return exit0'
$report = Get-Content (Join-Path $reportPath 'diagnostics.json') -Raw | ConvertFrom-Json -AsHashtable
Assert-True ($report.schemaVersion -eq 2 -and $report.summary.coverageStatus -eq 'Incomplete') 'Schema2 separates successful findings from explicit incomplete coverage'
Assert-True (($output -join ' ') -match 'Coverage: Incomplete' -and ($output -join ' ') -notmatch 'Actionable:') 'Default healthy console prominently reports coverage without manufactured action items'
$markdown = Get-Content (Join-Path $reportPath 'diagnostics.md') -Raw
foreach ($heading in @('## Actionable summary','## Finding details','## Coverage details','## Inventory details')) {
    Assert-True ($markdown.Contains($heading)) 'Readable report groups action items, finding details, coverage and inventory'
}
