# Scenarios for Probe checks (network tests recorded from the runner).

function global:Set-ProbeScenarioAttempt {
    # Rewrites every attempt of one probe; $Tcp/$Tls/$Http replace those stages (use $null for a stage never reached).
    param($E, [string]$HostName, [string]$Outcome, $Tcp = 'keep', $Tls = 'keep', $Http = 'keep')
    $p = Get-EvProbe $E $HostName
    foreach ($a in $p.attempts) {
        if ($Tcp -ne 'keep') { $a.tcp = $Tcp }
        if ($Tls -ne 'keep') { $a.tls = $Tls }
        if ($Http -ne 'keep') { $a.http = $Http }
        $a.outcome = $Outcome
    }
    $p.outcome = $Outcome
}

function global:Set-ProbeScenarioProbe {
    param($E, $Probe)
    $E.probes = @(@($E.probes | Where-Object { $_.host -ine $Probe.host }) + , $Probe)
}

@(
    # probe.dns — resolution from this machine vs the private endpoint IP.
    @{ Name = 'probe-dns-public-ip'
       Mutate = { param($E) Set-ProbeScenarioProbe $E (New-TestProbe 'api.loganalytics.io' 'MonitorQuery' @('20.42.73.1') @('api.loganalytics.io.trafficmanager.net') -HttpStatus 404) }
       Expect = @{ 'probe.dns@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'probe-dns-other-private-ip'
       Mutate = { param($E) Set-ProbeScenarioProbe $E (New-TestProbe 'acct.services.ai.azure.com' 'Foundry' @('10.1.5.99') @('acct.privatelink.services.ai.azure.com')) }
       Expect = @{ 'probe.dns@Foundry' = 'Problem:High' } }
    @{ Name = 'probe-dns-mixed-answers'
       Mutate = { param($E) Set-ProbeScenarioProbe $E (New-TestProbe 'stacct.blob.core.windows.net' 'Storage' @('10.1.5.7', '20.60.1.1') @('stacct.privatelink.blob.core.windows.net') -HttpStatus 400) }
       Expect = @{ 'probe.dns@Storage' = 'Problem:Medium' } }
    @{ Name = 'probe-dns-nxdomain'
       Mutate = { param($E) $p = Get-EvProbe $E 'stacct.blob.core.windows.net'; $p.dns.answers = @(); $p.dns.error = 'NXDOMAIN'; $p.attempts = @(); $p.outcome = 'DnsFailed' }
       Expect = @{ 'probe.dns@Storage' = 'Problem:High' } }

    # probe.path — TCP, TLS and first-byte failures.
    @{ Name = 'probe-tcp-timeout'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'acct.services.ai.azure.com' Blocked -Tcp ([ordered]@{ ok = $false; ms = 5000; error = 'Timeout' }) -Tls $null -Http $null }
       Expect = @{ 'probe.path@Foundry' = 'Problem:High' } }
    @{ Name = 'probe-tcp-refused'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'acct.services.ai.azure.com' Refused -Tcp ([ordered]@{ ok = $false; ms = 2; error = 'Refused' }) -Tls $null -Http $null }
       Expect = @{ 'probe.path@Foundry' = 'Problem:High' } }
    @{ Name = 'probe-tcp-unreachable'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'stacct.blob.core.windows.net' Blocked -Tcp ([ordered]@{ ok = $false; ms = 1; error = 'Unreachable' }) -Tls $null -Http $null }
       Expect = @{ 'probe.path@Storage' = 'Problem:High' } }
    @{ Name = 'probe-http-reset'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'stacct.blob.core.windows.net' Reset -Http ([ordered]@{ status = $null; firstByteMs = $null; server = $null; msRequestId = $null; error = 'Reset' }) }
       Expect = @{ 'probe.path@Storage' = 'Problem:High' } }
    @{ Name = 'probe-tls-untrusted-inspection'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'api.loganalytics.io' TlsFailed -Http $null `
               -Tls ([ordered]@{ ok = $false; ms = 30; issuer = 'CN=Contoso Firewall Inspection CA, O=Contoso'; rootIssuer = 'CN=Contoso Root'; subject = 'CN=api.loganalytics.io'; error = 'Untrusted' }) }
       Expect = @{ 'probe.path@MonitorQuery' = 'Problem:High'; 'probe.tlsIssuer@MonitorQuery' = 'Problem:High'; 'probe.comparison' = 'Problem:High' } }
    @{ Name = 'probe-tls-untrusted-microsoft-issuer'
       Mutate = { param($E) $p = Get-EvProbe $E 'acct.services.ai.azure.com'; $t = $p.attempts[0].tls; $t.ok = $false; $t.error = 'Untrusted'
               Set-ProbeScenarioAttempt $E 'acct.services.ai.azure.com' TlsFailed -Http $null }
       Expect = @{ 'probe.path@Foundry' = 'Problem:High' } }
    @{ Name = 'probe-tls-name-mismatch'
       Mutate = { param($E) $p = Get-EvProbe $E 'acct.services.ai.azure.com'; $t = $p.attempts[0].tls; $t.ok = $false; $t.error = 'NameMismatch'; $t.subject = 'CN=proxy.contoso.com'
               Set-ProbeScenarioAttempt $E 'acct.services.ai.azure.com' TlsFailed -Http $null }
       Expect = @{ 'probe.path@Foundry' = 'Problem:High' } }
    @{ Name = 'probe-tls-inspection-trusted'
       Mutate = { param($E) $t = (Get-EvProbe $E 'stacct.blob.core.windows.net').attempts[0].tls; $t.issuer = 'CN=Contoso Firewall Inspection CA, O=Contoso'; $t.rootIssuer = 'CN=Contoso Root' }
       Expect = @{ 'probe.tlsIssuer@Storage' = 'Problem:Medium' } }
    # The real case: api.loganalytics.io accepted the connection, then went silent.
    @{ Name = 'probe-http-stall-monitor-only'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'api.loganalytics.io' Stalled -Http ([ordered]@{ status = $null; firstByteMs = $null; server = $null; msRequestId = $null; error = 'NoResponse' }) }
       Expect = @{ 'probe.path@MonitorQuery' = 'Problem:High'; 'probe.comparison' = 'Problem:High' } }
    @{ Name = 'probe-tls-timeout-stall'
       Mutate = { param($E) Set-ProbeScenarioAttempt $E 'api.loganalytics.io' Stalled -Http $null `
               -Tls ([ordered]@{ ok = $false; ms = 10000; issuer = $null; rootIssuer = $null; subject = $null; error = 'Timeout' }) }
       Expect = @{ 'probe.path@MonitorQuery' = 'Problem:High'; 'probe.comparison' = 'Problem:High' } }
    @{ Name = 'probe-all-egress-stall'
       Mutate = { param($E)
           $silent = [ordered]@{ status = $null; firstByteMs = $null; server = $null; msRequestId = $null; error = 'NoResponse' }
           foreach ($h in 'api.loganalytics.io', 'api.applicationinsights.io', 'management.azure.com') { Set-ProbeScenarioAttempt $E $h Stalled -Http $silent } }
       Expect = @{ 'probe.path@MonitorQuery' = 'Problem:High'; 'probe.comparison' = 'Problem:High' }; Allow = @('probe.path') }
    @{ Name = 'probe-comparison-missing'
       Mutate = { param($E)
           $E.probes = @($E.probes | Where-Object { $_.purpose -ne 'Comparison' })
           Set-ProbeScenarioAttempt $E 'api.loganalytics.io' Stalled -Http ([ordered]@{ status = $null; firstByteMs = $null; server = $null; msRequestId = $null; error = 'NoResponse' }) }
       Expect = @{ 'probe.path@MonitorQuery' = 'Problem:High'; 'probe.comparison' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'probe-mixed-attempts-worst-wins'
       Mutate = { param($E)
           $p = New-TestProbe 'acct.services.ai.azure.com' 'Foundry' @('10.1.5.4', '10.1.5.4') @('acct.privatelink.services.ai.azure.com')
           $p.attempts[1].http = [ordered]@{ status = $null; firstByteMs = $null; server = $null; msRequestId = $null; error = 'NoResponse' }
           $p.attempts[1].outcome = 'Stalled'; $p.outcome = 'Stalled'
           Set-ProbeScenarioProbe $E $p }
       Expect = @{ 'probe.path@Foundry' = 'Problem:High' } }

    # probe.fromMicrosoft — an answer without x-ms-request-id.
    @{ Name = 'probe-proxy-answers'
       Mutate = { param($E) $h = (Get-EvProbe $E 'acct.services.ai.azure.com').attempts[0].http; $h.msRequestId = $false; $h.status = 403; $h.server = 'squid' }
       Expect = @{ 'probe.fromMicrosoft@Foundry' = 'Problem:Medium' } }
    # Azure gateways often answer 404 or 200 without a request ID; that alone isn't a proxy.
    @{ Name = 'probe-azure-404-without-request-id'
       Mutate = { param($E) $h = (Get-EvProbe $E 'acct.services.ai.azure.com').attempts[0].http; $h.msRequestId = $false; $h.status = 404; $h.server = 'Kestrel' }
       Expect = @{ 'probe.fromMicrosoft@Foundry' = 'OK' } }
    @{ Name = 'probe-gateway-error-without-request-id'
       Mutate = { param($E) $h = (Get-EvProbe $E 'acct.services.ai.azure.com').attempts[0].http; $h.msRequestId = $false; $h.status = 502; $h.server = $null }
       Expect = @{ 'probe.fromMicrosoft@Foundry' = 'Problem:Medium' } }

    # Missing or skipped tests.
    @{ Name = 'probe-old-evidence'; Mutate = { param($E) $E.Remove('probes') }
       Expect = @{ 'probe.path' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'probe-monitor-host-missing'
       Mutate = { param($E) $E.probes = @($E.probes | Where-Object { $_.host -ne 'api.loganalytics.io' }) }
       Expect = @{ 'probe.path@MonitorQuery' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'probe-path-host-missing'
       Mutate = { param($E) $E.probes = @($E.probes | Where-Object { $_.purpose -ne 'Storage' }) }
       Expect = @{ 'probe.path@Storage' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'probe-disabled'
       Mutate = { param($E) foreach ($p in $E.probes) { $p.outcome = 'Skipped'; $p.attempts = @(); $p.dns = $null } }
       Expect = @{ 'probe.path' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'probe-budget-hit'
       Mutate = { param($E) $p = Get-EvProbe $E 'stacct.blob.core.windows.net'; $p.outcome = 'Skipped'; $p.budgetHit = $true; $p.attempts = @(); $p.dns = $null }
       Expect = @{ 'probe.path@Storage' = 'CouldNotCheck:Blocking' } }
)
