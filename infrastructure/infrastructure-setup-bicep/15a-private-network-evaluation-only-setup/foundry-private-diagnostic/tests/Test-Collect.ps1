#requires -Version 7.2
# Tests the collector offline: a fake ARM endpoint built from the healthy fixture (plus secrets that must be dropped),
# masking, and real local sockets for the network tests.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'scripts/Core.ps1')
foreach ($folder in 'checks', 'collect') { foreach ($file in Get-ChildItem (Join-Path $root "scripts/$folder") -Filter *.ps1) { . $file.FullName } }
. (Join-Path $PSScriptRoot 'Fixtures.ps1')

$script:failures = [Collections.Generic.List[string]]::new()
$script:assertions = 0
function Assert-True { param([bool]$Condition, [string]$Message) $script:assertions++; if (!$Condition) { $script:failures.Add($Message) } }

$ids = Get-TestIds
$token = 'TESTTOKEN-' + [guid]::NewGuid()
$secrets = 'SECRETVALUE-1', 'eyJhbGciOiJIUzI1NiJ9.fake', 'sig=SIGVALUE', 'AccountKey=KEYVALUE', 'InstrumentationKey='

# ARM responses: fixture data plus fields the collector must never keep.
function New-FakeArm {
    param($Fixture)
    $store = @{}
    foreach ($r in $Fixture.requests) {
        if ($r.method -eq 'POST') { $store["post#$(($r.key -split '#', 2)[1])".ToLowerInvariant()] = @{ status = $r.status; data = $r.data }; continue }
        if ($r.status -ne 200) { if ($r.status) { $store[$r.path.ToLowerInvariant()] = @{ status = $r.status } }; continue }
        $data = ($r.data | ConvertTo-Json -Depth 64 | ConvertFrom-Json -AsHashtable)
        $items = $(if ($data -is [Collections.IList]) { @($data) } else { @($data) })
        foreach ($o in $items) {
            if (!$o -or !$o.properties) { continue }
            $o.properties.connectionString = 'InstrumentationKey=SECRETVALUE-1;IngestionEndpoint=https://x'
            $o.properties.InstrumentationKey = 'SECRETVALUE-1'
            $o.properties.credentials = @{ key = 'SECRETVALUE-1'; sas = 'sv=2022&sig=SIGVALUE' }
            $o.properties.unlistedField = 'eyJhbGciOiJIUzI1NiJ9.fake'
            if ($o.properties.target -and $o.properties.target -like 'https://*') { $o.properties.target = "$($o.properties.target)?sv=2022&sig=SIGVALUE" }
        }
        $store[$r.path.ToLowerInvariant()] = @{ data = $data; collection = [bool](Get-DiagArmRule $r.path).Collection }
    }
    $store
}

function New-TestContext {
    param($Store, [int]$Budget = 150)
    $ctx = New-DiagCollectContext -Budget $Budget
    $calls = [Collections.Generic.List[object]]::new()
    $ctx | Add-Member -NotePropertyName Calls -NotePropertyValue $calls
    $ctx.Http = {
        param($Method, $Uri, $Headers, $Body, $TimeoutSec)
        $calls.Add([ordered]@{ method = $Method; uri = $Uri; auth = $Headers.Authorization })
        $u = [uri]$Uri
        $path = $u.AbsolutePath.TrimEnd('/').ToLowerInvariant()
        if ($Method -eq 'POST') {
            $q = "$(($Body | ConvertFrom-Json).query)"
            $label = $(if ($q -match "== '([\d.]+)'") { "nexthop:$($Matches[1])" } elseif ($q -match 'virtualhubs') { 'virtualhubs' })
            $hit = $Store["post#$label"]
            if (!$hit) { return @{ Status = 200; Content = '{"data":[]}' } }
            if ($hit.status -ne 200) { return @{ Status = $hit.status; Content = '{"error":{"code":"AuthorizationFailed"}}' } }
            return @{ Status = 200; Content = (@{ data = @($hit.data) } | ConvertTo-Json -Depth 64) }
        }
        $entry = $Store[$path]
        if (!$entry) { return @{ Status = 404; Content = '{"error":{"code":"NotFound","message":"secret sig=SIGVALUE"}}' } }
        if ($entry.status -and $entry.status -ne 200) { return @{ Status = $entry.status; Content = '{"error":{"code":"AuthorizationFailed"}}' } }
        if ($path.EndsWith('/metrics')) {
            $m = $entry.data
            $points = @(if ($null -ne $m.maximum) { @{ maximum = $m.maximum; average = $m.average } })
            return @{ Status = 200; Content = (@{ value = @(@{ timeseries = @(@{ data = $points }) }) } | ConvertTo-Json -Depth 10) }
        }
        if (!$entry.collection) { return @{ Status = 200; Content = ($entry.data | ConvertTo-Json -Depth 64) } }
        $all = @($entry.data)
        $apiVersion = [regex]::Match($u.Query, 'api-version=([^&]+)').Groups[1].Value
        $page2 = $u.Query -match 'skiptoken=2'
        if ($all.Count -gt 1 -and !$page2) {
            $next = "https://management.azure.com$($u.AbsolutePath)?api-version=$apiVersion&`$skiptoken=2"
            return @{ Status = 200; Content = (@{ value = @($all[0]); nextLink = $next } | ConvertTo-Json -Depth 64) }
        }
        $rest = $(if ($page2) { @($all | Select-Object -Skip 1) } else { $all })
        @{ Status = 200; Content = (@{ value = @($rest) } | ConvertTo-Json -Depth 64) }
    }.GetNewClosure()
    $ctx.Sleep = { param($s) }
    $ctx.Imds = { param($Path) if ($Path -like 'instance/compute*') { return @{ resourceId = $ids.Vm } }; throw 'no imds' }.GetNewClosure()
    $ctx.DnsServers = { @('168.63.129.16') }
    $ctx.Proxy = { [ordered]@{ system = 'none'; env = @() } }
    $ctx.TokenProvider = { param($c) @{ Token = $token; Source = 'ManagedIdentity' } }.GetNewClosure()
    $ctx.Probe = $false
    $ctx
}

function Get-ResultMap {
    param($Evidence)
    $e = $Evidence | ConvertTo-Json -Depth 64 | ConvertFrom-Json -AsHashtable
    $map = @{}
    foreach ($r in (Invoke-DiagAnalysis $e)) { $map["$($r.id)@$($r.path)@$(Get-ArmName $r.resource)"] = "$($r.status)$(if ($r.severity) { ":$($r.severity)" })$(if ($r.gap) { ":$($r.gap)" })" }
    $map
}

# --- 1. Collect from the fake ARM endpoint --------------------------------------------------------------------------
$fixture = New-HealthyEvidence
$store = New-FakeArm $fixture
$ctx = New-TestContext $store
$evidence = Invoke-DiagCollect -ProjectResourceId $ids.Project -Ctx $ctx
$json = $evidence | ConvertTo-Json -Depth 64

Assert-True ($evidence.schema -eq 1 -and $evidence.run.project -eq $ids.Project) 'Top-level schema/run fields.'
Assert-True ($evidence.run.runner.azureVmResourceId -eq $ids.Vm -and $evidence.run.runner.tokenSource -eq 'ManagedIdentity') 'Runner info from IMDS and token source.'
foreach ($c in $ctx.Calls) {
    $okPost = $c.method -eq 'POST' -and $c.uri -like 'https://management.azure.com/providers/Microsoft.ResourceGraph/resources?*'
    Assert-True ($c.method -eq 'GET' -or $okPost) "Only GET and the Resource Graph POST are allowed; saw $($c.method) $($c.uri)."
    Assert-True ($c.uri -like 'https://management.azure.com/*') "Requests go to ARM only; saw $($c.uri)."
}
Assert-True (!$json.Contains($token)) 'The access token must not appear in evidence.'
foreach ($s in $secrets) { Assert-True (!$json.Contains($s)) "Evidence must not contain '$s'." }
Assert-True (!($json -match '(?i)connectionString|credentials|unlistedField')) 'Non-allowlisted fields are dropped.'
Assert-True ($evidence.Contains('_index') -eq $false) 'No _index in collected evidence.'

$connections = @(($evidence.requests | Where-Object { $_.key -ieq "GET $($ids.Project)/connections" }).data)
Assert-True ($connections.Count -eq 2) "Paging merges all pages (got $($connections.Count) connections)."
Assert-True (@($connections | Where-Object { "$($_.properties.target)".Contains('?') }).Count -eq 0) 'Connection target query strings are stripped.'
$pagedCalls = @($ctx.Calls | Where-Object { $_.uri -like "*$($ids.Project)/connections*" })
Assert-True ($pagedCalls.Count -eq 2) "Paged collection needs 2 calls (got $($pagedCalls.Count))."
Assert-True (@($evidence.requests | Group-Object { $_.key.ToLowerInvariant() } | Where-Object Count -gt 1).Count -eq 0) 'Each path is read once.'

# Discovery matches the fixture's view of the project.
$d = $evidence.discovery
Assert-True ($d.account -eq $ids.Account -and $d.agentSubnet -eq $ids.AgentSubnet) 'Discovery finds the account and agent subnet.'
foreach ($kind in 'Account', 'Storage', 'AppInsights', 'Workspace', 'Ampls') {
    $want = @($fixture.discovery.dependencies | Where-Object kind -eq $kind)[0]
    $got = @($d.dependencies | Where-Object kind -eq $kind)[0]
    Assert-True ($null -ne $got) "Discovery has a $kind dependency."
    if (!$got) { continue }
    Assert-True ($got.resource -ieq $want.resource -and $got.path -eq $want.path) "$kind dependency resource/path."
    Assert-True ((@($got.privateEndpoints) -join ',') -ieq (@($want.privateEndpoints) -join ',')) "$kind private endpoints: got $(@($got.privateEndpoints) -join ',')."
    Assert-True ((@($got.hosts | Sort-Object) -join ',') -ieq (@($want.hosts | Sort-Object) -join ',')) "$kind hosts: got $(@($got.hosts) -join ',')."
}
foreach ($p in 'Foundry', 'Storage', 'MonitorQuery', 'Models') {
    Assert-True ($d.paths[$p].used -eq $fixture.discovery.paths[$p].used) "Path $p used=$($fixture.discovery.paths[$p].used)."
}
Assert-True ($d.runner.nic -ieq $ids.Nic -and $d.runner.subnet -ieq $ids.JumpSubnet) 'Discovery follows the runner VM to its NIC and subnet.'
$fixtureKeys = @($fixture.requests | ForEach-Object { $_.key.ToLowerInvariant() })
$missing = @($fixtureKeys | Where-Object { $k = $_; !($evidence.requests | Where-Object { $_.key.ToLowerInvariant() -eq $k }) })
Assert-True ($missing.Count -eq 0) "Collector reads every path the fixture has; missing: $($missing -join ', ')."

# The checks reach the same verdicts on collected evidence as on the fixture (probes come from the fixture).
$evidence.probes = $fixture.probes
$want = Get-ResultMap $fixture
$got = Get-ResultMap $evidence
foreach ($k in $want.Keys) { Assert-True ($got[$k] -eq $want[$k]) "Check verdict differs for $k`: fixture $($want[$k]), collected $($got[$k])." }
foreach ($k in $got.Keys) { Assert-True ($want.ContainsKey($k)) "Extra check result on collected evidence: $k = $($got[$k])." }

# The collector reaches the same verdicts as the network scenarios when it reads their evidence from ARM.
# Scenarios that edit discovery directly, or hide what discovery would need to find, have no ARM equivalent.
$notReplayable = @('egress-vwan-hub-unreadable', 'pe-connections-old-evidence', 'storage-connections-unreadable')
# Scenarios that hide or remove a resource keep its fixture discovery; replay compares only the checks they target.
$expectOnly = @('pe-connections-unreadable', 'storage-private-no-pe', 'storage-selected-networks-no-pe',
    'storage-public-no-pe', 'storage-pe-unreadable', 'monitor-component-not-found', 'monitor-component-unreadable', 'monitor-component-classic',
    'monitor-ampls-not-found', 'monitor-ampls-no-pe')
$replayed = 0
foreach ($file in 'Egress', 'Firewall', 'Nva', 'PrivateEndpoint', 'Dns', 'Nsg', 'Storage', 'Monitoring') {
    foreach ($scenario in @(& (Join-Path $PSScriptRoot "scenarios/$file.ps1"))) {
        if ($scenario.Name -in $notReplayable -or ($scenario.Mutate -and $scenario.Mutate.ToString() -match '\.discovery\b')) { continue }
        $source = New-HealthyEvidence
        if ($scenario.Mutate) { & $scenario.Mutate $source }
        $source = $source | ConvertTo-Json -Depth 64 | ConvertFrom-Json -AsHashtable
        $collected = Invoke-DiagCollect -ProjectResourceId $ids.Project -Ctx (New-TestContext (New-FakeArm $source))
        $collected.probes = $source.probes
        $want = Get-ResultMap $source; $got = Get-ResultMap $collected
        if ($scenario.Name -in $expectOnly) {
            $targets = @($scenario.Expect.Keys)
            $inScope = { param($k) @($targets | Where-Object { $k -like "$_@*" }).Count -gt 0 }
            foreach ($map in $want, $got) { foreach ($k in @($map.Keys)) { if (!(& $inScope $k)) { $map.Remove($k) } } }
            Assert-True ($want.Count -gt 0) "[replay $($scenario.Name)] No expected check results to compare."
        }
        $diff = @($want.Keys + $got.Keys | Sort-Object -Unique | Where-Object { $want[$_] -ne $got[$_] -and ($_ -split '@')[0] -notin @($scenario.Allow) } | ForEach-Object { "$_ (scenario $($want[$_]), collected $($got[$_]))" })
        Assert-True ($diff.Count -eq 0) "[replay $($scenario.Name)] $($diff -join '; ')"
        $replayed++
    }
}
Assert-True ($replayed -gt 100) "Replayed $replayed scenarios."

# Unreadable connections hide every dependency; collection still reports the blocking gap.
$source = New-HealthyEvidence
Set-EvStatus $source "$($ids.Project)/connections" 403
$source = $source | ConvertTo-Json -Depth 64 | ConvertFrom-Json -AsHashtable
$collected = Invoke-DiagCollect -ProjectResourceId $ids.Project -Ctx (New-TestContext (New-FakeArm $source))
$collected.probes = $source.probes
Assert-True ((Get-ResultMap $collected)['project.connections@@proj'] -eq 'CouldNotCheck:Blocking') 'Unreadable connections are reported as a blocking gap.'

# --- 2. Guards ------------------------------------------------------------------------------------------------------
$guard = New-TestContext $store
Assert-True ($null -eq (Invoke-DiagArm $guard '/subscriptions/x/resourceGroups/r/providers/Microsoft.KeyVault/vaults/kv')) 'Non-allowlisted paths are not read.'
Assert-True ($guard.Calls.Count -eq 0) 'Rejected paths send nothing.'
$threw = $false; try { Invoke-DiagResourceGraph $guard 'anything' 'resources' } catch { $threw = $true }
Assert-True $threw 'Resource Graph rejects unknown labels.'
$threw = $false; try { Get-DiagGraphQuery nextHop -Ip "10.0.0.1' or 1==1" } catch { $threw = $true }
Assert-True $threw 'Next-hop query rejects a non-IP.'
Assert-True (!(Test-DiagNextLink 'https://evil.example.com/x?api-version=1' '/x' '1')) 'Next links to another host are refused.'
Assert-True (!(Test-DiagNextLink 'https://management.azure.com/other?api-version=1' '/x' '1')) 'Next links to another path are refused.'

$small = New-TestContext $store -Budget 5
$e2 = Invoke-DiagCollect -ProjectResourceId $ids.Project -Ctx $small
Assert-True ($e2.requests.Count -le 5) "Budget caps reads (got $($e2.requests.Count))."
Assert-True (@($e2.collectorErrors | Where-Object errorKind -eq 'Budget').Count -eq 1) 'Budget overrun is reported once.'

$noToken = New-TestContext $store
$noToken.TokenProvider = { param($c) throw [InvalidOperationException]'No Azure sign-in found.' }
$threw = $false; try { $null = Invoke-DiagCollect -ProjectResourceId $ids.Project -Ctx $noToken } catch { $threw = $_.Exception.Message -like '*sign-in*' }
Assert-True $threw 'A missing token stops collection with the sign-in message.'
Assert-True ($noToken.Calls.Count -eq 0) 'Nothing is sent without a token.'

$flaky = New-TestContext $store
$inner = $flaky.Http
$state = @{ n = 0 }
$flaky.Http = { param($m, $u, $h, $b, $t) $state.n++; if ($state.n -le 2) { return @{ Status = 429; Content = ''; RetryAfter = '1' } }; & $inner $m $u $h $b $t }.GetNewClosure()
$r = Invoke-DiagArm $flaky $ids.Project
Assert-True ($r.status -eq 200) 'Throttled reads are retried.'
$down = New-TestContext $store
$down.Http = { param($m, $u, $h, $b, $t) throw [TimeoutException]'slow' }
$r = Invoke-DiagArm $down $ids.Project
Assert-True ($null -eq $r.status -and $r.errorKind -eq 'Timeout') 'A request timeout is recorded as Timeout with no status.'

# --- 3. Masking ---------------------------------------------------------------------------------------------------
$masked = ConvertTo-DiagMaskedEvidence ($evidence | ConvertTo-Json -Depth 64 | ConvertFrom-Json -AsHashtable)
$mjson = $masked | ConvertTo-Json -Depth 64
Assert-True ($masked.run.masked -eq $true) 'Masked evidence is flagged.'
foreach ($name in 'rg-foundry', 'rg-network', 'vnet-agents', 'nsg-agents', 'stacct', 'appinsights-conn', 'storage-conn', 'pe-acct', 'vm-jump', 'nic-jump', '/accounts/acct', '/projects/proj', '"law"', '/workspaces/law', 'acct.services') {
    Assert-True (!$mjson.Contains($name)) "Masked evidence still contains '$name'."
}
foreach ($keep in $script:TS, 'privatelink.blob.core.windows.net', 'api.loganalytics.io', '10.1.5.13', $ids.ProjectPrincipal, 'gpt-4o') {
    Assert-True ($mjson.Contains($keep)) "Masking should keep '$keep'."
}
$plain = Get-ResultMap $evidence
$after = Get-ResultMap $masked
$summarize = { param($m) @($m.GetEnumerator() | ForEach-Object { "$(($_.Key -split '@')[0..1] -join '@')=$($_.Value)" } | Sort-Object) -join '|' }
$pl = & $summarize $plain; $af = & $summarize $after
$diff = Compare-Object ($pl -split '\|') ($af -split '\|') | ForEach-Object { "$($_.SideIndicator)$($_.InputObject)" }
Assert-True ($pl -eq $af) "Masked evidence replays to the same verdicts; differs: $($diff -join ', ')"

# --- 4. Network tests against local sockets ----------------------------------------------------------------------
$caps = @{ DnsMs = 2000; TcpMs = 4000; TlsMs = 1500; FirstByteMs = 1500; PhaseSec = 20 }
$silent = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0); $silent.Start()
$closed = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0); $closed.Start(); $closedPort = $closed.LocalEndpoint.Port; $closed.Stop()
try {
    $probeCtx = [pscustomobject]@{ ProbeCaps = $caps }
    $targets = @(
        @{ host = 'stall.test'; port = $silent.LocalEndpoint.Port; purpose = 'MonitorQuery'; resolver = $null; ips = @('127.0.0.1') }
        @{ host = 'refused.test'; port = $closedPort; purpose = 'Comparison'; resolver = $null; ips = @('127.0.0.1') }
        @{ host = 'nxdomain.invalid'; port = 443; purpose = 'Storage'; resolver = $null }
    )
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $probes = Invoke-DiagProbes $probeCtx $targets
    $sw.Stop()
    $byHost = @{}; foreach ($p in $probes) { $byHost[$p.host] = $p }
    Assert-True ($byHost['stall.test'].outcome -eq 'Stalled') "Accepted-then-silent connection is Stalled (got $($byHost['stall.test'].outcome))."
    Assert-True ($byHost['stall.test'].attempts[0].tls.error -eq 'Timeout') 'The stall is recorded at the TLS stage.'
    Assert-True ($byHost['refused.test'].outcome -eq 'Refused') "Closed port is Refused (got $($byHost['refused.test'].outcome))."
    Assert-True ($byHost['nxdomain.invalid'].outcome -eq 'DnsFailed' -and $byHost['nxdomain.invalid'].dns.error) "Unknown name is DnsFailed (got $($byHost['nxdomain.invalid'].outcome))."
    Assert-True ($sw.Elapsed.TotalSeconds -lt 15) "Network tests respect the caps (took $([int]$sw.Elapsed.TotalSeconds)s)."

    $tight = [pscustomobject]@{ ProbeCaps = @{ DnsMs = 1000; TcpMs = 1000; TlsMs = 1000; FirstByteMs = 1000; PhaseSec = 1 } }
    $p = @(Invoke-DiagProbes $tight @(@{ host = 'stall.test'; port = $silent.LocalEndpoint.Port; purpose = 'MonitorQuery'; resolver = $null; ips = @('127.0.0.1') }))[0]
    Assert-True ($p.outcome -eq 'Skipped' -and $p.budgetHit) "A probe that can't finish before the deadline is Skipped with budgetHit (got $($p.outcome))."
}
finally { $silent.Stop() }

$targets = Get-DiagProbeTargets $fixture.discovery @('10.0.0.4')
$hosts = @($targets.host)
foreach ($h in 'api.loganalytics.io', 'api.applicationinsights.io', 'management.azure.com', 'acct.services.ai.azure.com', 'stacct.blob.core.windows.net') {
    Assert-True ($hosts -contains $h) "Probe targets include $h."
}
Assert-True ($hosts.Count -le 16 -and ($hosts | Select-Object -Unique).Count -eq $hosts.Count) 'Probe targets are capped and unique.'
Assert-True (@($targets | Where-Object host -eq 'management.azure.com')[0].purpose -eq 'Comparison') 'management.azure.com is the comparison host.'

if ($script:failures.Count) {
    Write-Host "Test-Collect: FAIL ($($script:failures.Count) of $script:assertions)" -ForegroundColor Red
    $script:failures | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "Test-Collect: PASS ($script:assertions assertions)" -ForegroundColor Green
