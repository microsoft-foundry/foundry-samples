# Probe checks: network tests recorded from the machine that ran the diagnostic (the runner).
# Every result here has scope ThisMachine: it reflects the runner's network path, which may differ from the agent subnet's.

$script:ProbeMonitorQueryHosts = @('api.loganalytics.io', 'api.applicationinsights.io')
$script:ProbeMonitorQueryFqdn = 'api.monitor.azure.com'   # AMPLS private endpoint name the query hosts resolve through
$script:ProbeFailedOutcomes = @('Stalled', 'Blocked', 'Refused', 'Reset', 'TlsFailed')
$script:ProbeTrustedIssuer = '(?i)Microsoft|DigiCert'
$script:ProbeOutcomeRank = @{ Stalled = 5; Blocked = 4; Reset = 3; Refused = 2; TlsFailed = 1; Reachable = 0 }
$script:ProbeStallLikely = 'Consistent with a firewall, network virtual appliance or TLS inspection holding the connection without forwarding it (network security group and permission problems fail fast instead).'

function Get-DiagProbeStallAction {
    param([string]$HostName)
    "On the firewall or appliance in the agent subnet's route, allow $HostName on 443 from the agent subnet, exclude it from TLS inspection and intrusion prevention, and check its logs for drops."
}

function Get-DiagProbePath {
    param([string]$Purpose)
    switch ($Purpose) {
        'MonitorPrivate' { 'MonitorQuery' }
        { $_ -in $script:DiagPaths } { $_ }
        default { $null }
    }
}

function Test-DiagPrivateIp {
    param([string]$Ip)
    $Ip -match '^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)'
}

function Get-DiagProbeNames {
    # Every name the probe host can match a private endpoint FQDN under.
    param($Probe)
    $names = @($Probe.host) + @($Probe.dns.cnameChain)
    $names += @($names | Where-Object { $_ } | ForEach-Object { $_ -ireplace '\.privatelink\.', '.' })
    if ($Probe.host -in $script:ProbeMonitorQueryHosts) { $names += $script:ProbeMonitorQueryFqdn }
    @($names | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('.').ToLowerInvariant() } | Select-Object -Unique)
}

# Private endpoint IPs the probe host should resolve to, from the dependency's private endpoints.
function Get-DiagProbeExpected {
    param($Evidence, $Probe)
    $deps = @($Evidence.discovery.dependencies | Where-Object { $_ })
    $dep = $deps | Where-Object { @($_.hosts) -icontains $Probe.host } | Select-Object -First 1
    $path = $(if ($dep) { $dep.path } else { Get-DiagProbePath $Probe.purpose })
    $source = $(if ($dep -and @($dep.privateEndpoints).Count) { @($dep) } elseif ($path) { @($deps | Where-Object path -eq $path) } else { @() })
    $peIds = @($source | ForEach-Object { @($_.privateEndpoints) } | Where-Object { $_ } | Select-Object -Unique)
    $names = Get-DiagProbeNames $Probe
    $ips = [Collections.Generic.List[string]]::new()
    $refs = [Collections.Generic.List[string]]::new()
    foreach ($peId in $peIds) {
        $pe = Get-Ev $Evidence $peId
        if ($pe.Ok) {
            $refs.Add((Get-EvRef $pe))
            foreach ($c in @($pe.Data.properties.customDnsConfigs | Where-Object { $_ -and $_.fqdn })) {
                if ($c.fqdn.TrimEnd('.').ToLowerInvariant() -in $names) { @($c.ipAddresses) | Where-Object { $_ } | ForEach-Object { $ips.Add($_) } }
            }
        }
        $groups = Get-Ev $Evidence "$peId/privateDnsZoneGroups"
        if ($groups.Ok) {
            foreach ($cfg in @($groups.Data | ForEach-Object { @($_.properties.privateDnsZoneConfigs) } | Where-Object { $_ })) {
                foreach ($rs in @($cfg.properties.recordSets | Where-Object { $_ -and $_.fqdn })) {
                    if ($rs.fqdn.TrimEnd('.').ToLowerInvariant() -in $names) { @($rs.ipAddresses) | Where-Object { $_ } | ForEach-Object { $ips.Add($_) } }
                }
            }
        }
    }
    @{ Ips = @($ips | Select-Object -Unique); PrivateEndpoints = $peIds; Evidence = @($refs) }
}

# Explains one failed attempt: which layer failed, what was seen, and what it is consistent with.
function Get-DiagProbeFailure {
    param([string]$HostName, $Attempt)
    $ip = $Attempt.ip
    $tcp = $Attempt.tcp; $tls = $Attempt.tls; $http = $Attempt.http
    $where = "$HostName ($ip)"
    $allow = "Allow outbound TCP 443 to $ip ($HostName) from the agent subnet in its network security group, route table and any firewall in the path."
    if ($tcp -and !$tcp.ok) {
        switch ($tcp.error) {
            'Refused' {
                return @{ Layer = 'Route'; Seen = "From this machine, $ip`:443 refused the connection to $HostName."
                    Likely = 'Consistent with a firewall or proxy rejecting the connection, or nothing listening at that IP (for example a deleted private endpoint).'
                    Action = "Check that $ip is the current private endpoint IP for $HostName and that no firewall or proxy rejects port 443." }
            }
            'Reset' {
                return @{ Layer = 'Route'; Seen = "From this machine, the connection to $where was reset while connecting."
                    Likely = 'Consistent with a firewall, proxy or appliance closing the connection.'; Action = $allow }
            }
            'Unreachable' {
                return @{ Layer = 'Route'; Seen = "From this machine, $where was unreachable (no route)."
                    Likely = "Consistent with no route to $ip, or a route with next hop None."; Action = $allow }
            }
            default {
                return @{ Layer = 'Route'; Seen = "From this machine, the TCP connection to $ip`:443 ($HostName) timed out after $(if ($tcp.ms) { $tcp.ms } else { 5000 }) ms."
                    Likely = 'Consistent with a network security group, route or firewall silently dropping the traffic.'; Action = $allow }
            }
        }
    }
    if ($tls -and !$tls.ok) {
        $issuer = $tls.issuer
        $foreign = $issuer -and $issuer -notmatch $script:ProbeTrustedIssuer
        switch ($tls.error) {
            'Untrusted' {
                if ($foreign) {
                    return @{ Layer = 'Tls'; Seen = "From this machine, the certificate for $where was issued by '$issuer', which isn't trusted."
                        Likely = 'Consistent with TLS inspection by a firewall or proxy.'
                        Action = "Exclude $HostName from TLS inspection on the firewall or proxy; the agent environment doesn't trust the inspection certificate." }
                }
                return @{ Layer = 'Tls'; Seen = "From this machine, the Microsoft certificate for $where wasn't trusted$(if ($issuer) { " (issuer '$issuer')" })."
                    Likely = "Consistent with this machine missing current root certificates."
                    Action = "Update this machine's trusted root certificates and run the diagnostic again."; Owner = 'Customer' }
            }
            'NameMismatch' {
                return @{ Layer = 'Tls'; Seen = "From this machine, $where presented a certificate for '$($tls.subject)' instead of $HostName."
                    Likely = 'Consistent with traffic reaching a different service, such as a proxy or a wrong DNS record.'
                    Action = "Check the DNS record for $HostName and any proxy or firewall that answers on its behalf." }
            }
            'Timeout' {
                # Accepted, then silence during the handshake: a stall, not a certificate problem.
                return @{ Layer = 'Response'; Seen = "From this machine, $where accepted the connection, then stopped responding during the TLS handshake (no answer within 10 s)."
                    Likely = $script:ProbeStallLikely; Action = (Get-DiagProbeStallAction $HostName) }
            }
            'Reset' {
                return @{ Layer = 'Tls'; Seen = "From this machine, the connection to $where was reset during the TLS handshake."
                    Likely = 'Consistent with a firewall, proxy or appliance closing the connection.'
                    Action = "Check the firewall or appliance on the path to $HostName`: allow it on 443 and exclude it from TLS inspection." }
            }
            default {
                return @{ Layer = 'Tls'; Seen = "From this machine, the TLS handshake with $where failed ($($tls.error))."
                    Action = "Check the firewall, proxy or appliance on the path to $HostName on port 443." }
            }
        }
    }
    if ($http -and $null -eq $http.status) {
        if ($http.error -eq 'Reset') {
            return @{ Layer = 'Response'; Seen = "From this machine, $where completed TLS, then reset the connection before answering."
                Likely = 'Consistent with a firewall, proxy or appliance closing the connection after inspecting it.'
                Action = "Check the firewall or appliance on the path to $HostName`: allow it on 443 and review its logs for drops." }
        }
        if ($http.error -eq 'NoResponse' -or $Attempt.outcome -eq 'Stalled') {
            return @{ Layer = 'Response'; Seen = "From this machine, $where accepted the connection, then stopped responding after TLS (no answer within 20 s)."
                Likely = $script:ProbeStallLikely; Action = (Get-DiagProbeStallAction $HostName) }
        }
        return @{ Layer = 'Response'; Seen = "From this machine, $where completed TLS but the request failed ($($http.error))."
            Action = "Check the firewall, proxy or appliance on the path to $HostName on port 443." }
    }
    $null
}

function Get-DiagProbeWorstAttempt {
    param($Probe)
    # Worst attempt: Stalled > Blocked > Reset > Refused > TlsFailed > Reachable (unknown outcomes rank just above Reachable).
    $attempts = @($Probe.attempts | Where-Object { $_ })
    $attempts | Sort-Object -Stable -Descending { $r = $script:ProbeOutcomeRank[[string]$_.outcome]; if ($null -eq $r) { 0.5 } else { $r } } | Select-Object -First 1
}

function Get-DiagProbeAttemptSummary {
    param($Attempt)
    [ordered]@{ ip = $Attempt.ip; outcome = $Attempt.outcome; tcp = $Attempt.tcp.error; tls = $Attempt.tls.error; issuer = $Attempt.tls.issuer
        httpStatus = $Attempt.http.status; firstByteMs = $Attempt.http.firstByteMs; httpError = $Attempt.http.error }
}

function Test-DiagProbe {
    param($Evidence)
    $out = [Collections.Generic.List[object]]::new()
    $common = @{ Area = 'Probe'; Scope = 'ThisMachine' }

    if (!$Evidence.Contains('probes') -or $null -eq $Evidence.probes) {
        $out.Add((New-DiagResult @common -Id probe.path -Title 'Network tests from this machine' -Status CouldNotCheck -Gap KnownLimit -Layer Route `
            -Seen 'This evidence file has no network test results.' -Needs 'Run the current version of the diagnostic to collect them.'))
        return , $out.ToArray()
    }
    $probes = @($Evidence.probes | Where-Object { $_ -and $_.host })

    # Required hosts: the Monitor query hosts always, and at least one host per used path.
    foreach ($h in $script:ProbeMonitorQueryHosts) {
        if (@($probes | Where-Object { $_.host -ieq $h }).Count) { continue }
        $used = Test-DiagPathUsed $Evidence 'MonitorQuery'
        $out.Add((New-DiagResult @common -Id probe.path -Title "Connection to $h" -Status CouldNotCheck -Gap $(if ($used) { 'Blocking' } else { 'KnownLimit' }) `
            -Path MonitorQuery -Layer Route -Resource $h -Seen "No network test was recorded for $h." `
            -Needs 'Run the current version of the diagnostic so it tests this host.'))
    }
    foreach ($path in Get-DiagPathsUsed $Evidence) {
        if ($path -eq 'MonitorQuery') { continue }
        if (@($probes | Where-Object { (Get-DiagProbePath $_.purpose) -eq $path }).Count) { continue }
        $h = @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.path -eq $path } | ForEach-Object { @($_.hosts) } | Where-Object { $_ })[0]
        $label = $(if ($h) { $h } else { "the $path path" })
        $out.Add((New-DiagResult @common -Id probe.path -Title "Connection to $label" -Status CouldNotCheck -Gap Blocking -Path $path -Layer Route `
            -Resource $(if ($h) { $h } else { $path }) -Seen "No network test was recorded for $label." `
            -Needs 'Run the current version of the diagnostic so it tests this host.'))
    }

    foreach ($p in $probes) {
        $h = $p.host
        $path = Get-DiagProbePath $p.purpose
        $isComparison = $p.purpose -eq 'Comparison'
        $ref = "probe:$h"
        $attempts = @($p.attempts | Where-Object { $_ })
        $details = @{ purpose = $p.purpose; outcome = $p.outcome; budgetHit = [bool]$p.budgetHit; resolver = $p.dns.resolver
            cnameChain = @($p.dns.cnameChain); answers = @($p.dns.answers); attempts = @($attempts | ForEach-Object { Get-DiagProbeAttemptSummary $_ }) }

        if ($p.outcome -eq 'Skipped') {
            $budget = [bool]$p.budgetHit
            $out.Add((New-DiagResult @common -Id probe.path -Title "Connection to $h" -Status CouldNotCheck -Gap $(if ($budget) { 'Blocking' } else { 'KnownLimit' }) `
                -Path $path -Layer Route -Resource $h `
                -Seen $(if ($budget) { "The test of $h didn't run because the time limit for network tests ran out." } else { "The test of $h was turned off for this run." }) `
                -Needs $(if ($budget) { 'Run the diagnostic again.' } else { 'Run the diagnostic with network tests on, from a machine in the agent virtual network.' }) `
                -Evidence $ref -Details $details))
            continue
        }

        # probe.dns — this machine resolves the host to the private endpoint IP.
        $dnsFailed = $p.outcome -eq 'DnsFailed' -or ($p.dns -and ($p.dns.error -or !@($p.dns.answers | Where-Object { $_ }).Count))
        if (!$isComparison -and $p.dns) {
            $title = "Name resolution for $h"
            $expected = Get-DiagProbeExpected $Evidence $p
            $answers = @($p.dns.answers | Where-Object { $_ })
            $resolver = $(if ($p.dns.resolver) { " using DNS server $($p.dns.resolver)" } else { '' })
            $dnsDetails = $details.Clone(); $dnsDetails.expected = $expected.Ips; $dnsDetails.privateEndpoints = $expected.PrivateEndpoints
            $refs = @($ref) + $expected.Evidence
            $expectedText = $expected.Ips -join ', '
            if ($dnsFailed) {
                $what = $(if ($p.dns.error -in @('NXDOMAIN', 'NameError', 'NotFound')) { "doesn't exist (NXDOMAIN)" } elseif ($p.dns.error) { "failed ($($p.dns.error))" } else { 'returned no addresses' })
                $out.Add((New-DiagResult @common -Id probe.dns -Title $title -Status Problem -Severity High -Path $path -Layer Name -Resource $h `
                    -Seen "From this machine, the name $h $what$resolver." `
                    -Likely 'Consistent with the DNS server not forwarding to Azure DNS, or a private DNS zone that is linked but has no record for this name.' `
                    -Owner NetworkTeam -Action $(if ($expectedText) { "Make $h resolve to $expectedText from the agent virtual network: add the record to the private DNS zone or forward the zone to Azure DNS (168.63.129.16)." } else { "Make $h resolvable from the agent virtual network (check DNS forwarding to Azure DNS, 168.63.129.16)." }) `
                    -Evidence $refs -Details $dnsDetails))
            }
            elseif (!$expected.Ips.Count) {
                $out.Add((New-DiagResult @common -Id probe.dns -Title $title -Status OK -Path $path -Layer Name -Resource $h `
                    -Seen "From this machine, $h resolves to $($answers -join ', ')$resolver (no private endpoint IP to compare)." -Evidence $refs -Details $dnsDetails))
            }
            else {
                $good = @($answers | Where-Object { $_ -in $expected.Ips })
                $bad = @($answers | Where-Object { $_ -notin $expected.Ips })
                if (!$bad.Count) {
                    $out.Add((New-DiagResult @common -Id probe.dns -Title $title -Status OK -Path $path -Layer Name -Resource $h `
                        -Seen "From this machine, $h resolves to the private endpoint IP $($answers -join ', ')$resolver." -Evidence $refs -Details $dnsDetails))
                }
                else {
                    $public = @($bad | Where-Object { !(Test-DiagPrivateIp $_) })
                    $likely = $(if ($public.Count) { 'Consistent with this DNS server not using the private DNS zone (zone not linked to its virtual network, or custom DNS not forwarding to Azure DNS).' }
                        else { 'Consistent with a stale DNS record or a different private DNS zone (for example one owned by another private link scope).' })
                    $kind = $(if ($public.Count) { 'public IP' } else { 'IP' })
                    $out.Add((New-DiagResult @common -Id probe.dns -Title $title -Status Problem -Severity $(if ($good.Count) { 'Medium' } else { 'High' }) -Path $path -Layer Name -Resource $h `
                        -Seen "From this machine, $h resolves to $kind $($bad -join ', ')$(if ($good.Count) { " as well as $($good -join ', ')" })$resolver; the private endpoint IP is $expectedText." `
                        -Likely $likely -Owner NetworkTeam `
                        -Action "Make $h resolve only to $expectedText from the agent virtual network: link the private DNS zone to it (or forward to Azure DNS, 168.63.129.16) and fix the A record." `
                        -Evidence $refs -Details $dnsDetails))
                }
            }
        }
        if ($dnsFailed) { continue }   # probe.dns already reports it; nothing was connected to.

        # probe.path — DNS → TCP → TLS → first byte.
        $title = "Connection to $h"
        $worst = Get-DiagProbeWorstAttempt $p
        if ($p.outcome -eq 'Reachable' -or !$worst) {
            if ($worst) {
                $out.Add((New-DiagResult @common -Id probe.path -Title $title -Status OK -Path $path -Layer Response -Resource $h `
                    -Seen "From this machine, $h ($($worst.ip)) answered HTTP $($worst.http.status) in $($worst.http.firstByteMs) ms." -Evidence $ref -Details $details))
            }
        }
        else {
            $f = Get-DiagProbeFailure $h $worst
            if (!$f) { $f = @{ Layer = 'Route'; Seen = "From this machine, the test of $h ended with '$($p.outcome)'."; Action = "Check the network path to $h on port 443." } }
            if ($attempts.Count -gt 1) { $f.Seen += " ($(@($attempts | ForEach-Object { "$($_.ip): $($_.outcome)" }) -join ', '))" }
            if ($p.budgetHit) { $f.Seen += ' The time limit for network tests was reached during this test.' }
            $extra = @{}
            if ($f.Likely) { $extra.Likely = $f.Likely }
            $owner = $(if ($f.Owner) { $f.Owner } else { 'NetworkTeam' })
            if ($isComparison) {
                $f.Seen += ' This host is only a reference for comparison.'
            }
            $out.Add((New-DiagResult @common @extra -Id probe.path -Title $title -Status Problem -Severity $(if ($isComparison) { 'Low' } else { 'High' }) `
                -Path $path -Layer $f.Layer -Resource $h -Seen $f.Seen -Owner $owner -Action $f.Action -Evidence $ref -Details $details))
        }

        # probe.tlsIssuer — the certificate comes from Microsoft / DigiCert.
        $withIssuer = @($attempts | Where-Object { $_.tls -and $_.tls.issuer })
        if ($withIssuer.Count) {
            $title = "TLS certificate issuer for $h"
            $foreign = @($withIssuer | Where-Object { $_.tls.issuer -notmatch $script:ProbeTrustedIssuer })
            if (!$foreign.Count) {
                $out.Add((New-DiagResult @common -Id probe.tlsIssuer -Title $title -Status OK -Path $path -Layer Tls -Resource $h `
                    -Seen "From this machine, $h presents a certificate issued by '$($withIssuer[0].tls.issuer)'." -Evidence $ref))
            }
            else {
                $issuer = $foreign[0].tls.issuer
                $untrusted = @($foreign | Where-Object { !$_.tls.ok }).Count -gt 0
                $out.Add((New-DiagResult @common -Id probe.tlsIssuer -Title $title -Status Problem -Severity $(if ($untrusted) { 'High' } else { 'Medium' }) `
                    -Path $path -Layer Tls -Resource $h `
                    -Seen "From this machine, $h presents a certificate issued by '$issuer' instead of Microsoft$(if ($untrusted) { ", and this machine doesn't trust it" } else { '; this machine trusts it, but the agent environment does not' })." `
                    -Likely 'Consistent with TLS inspection by a firewall or proxy.' -Owner NetworkTeam `
                    -Action "Exclude $h from TLS inspection on the firewall or proxy." -Evidence $ref `
                    -Details @{ issuer = $issuer; rootIssuer = $foreign[0].tls.rootIssuer; subject = $foreign[0].tls.subject }))
            }
        }

        # probe.fromMicrosoft — many Azure answers (200s, 404s from the service's gateway) carry no request ID, so
        # a missing ID only counts when the answer also looks like a proxy: 403/407, a 5xx, or a known proxy server.
        $answered = @($attempts | Where-Object { $_.http -and $null -ne $_.http.status -and $null -ne $_.http.msRequestId })
        if ($answered.Count) {
            $title = "Responder for $h"
            $other = @($answered | Where-Object {
                    !$_.http.msRequestId -and (
                        [int]$_.http.status -in @(403, 407) -or [int]$_.http.status -ge 500 -or
                        "$($_.http.server)" -match '(?i)squid|zscaler|bluecoat|fortigate|fortinet|palo ?alto|pan-|checkpoint|websense|forcepoint|netskope|mcafee|sophos|barracuda|cisco|umbrella|proxy')
                })
            if (!$other.Count) {
                $out.Add((New-DiagResult @common -Id probe.fromMicrosoft -Title $title -Status OK -Path $path -Layer Response -Resource $h `
                    -Seen "From this machine, the answer from $h doesn't look like a proxy or firewall." -Evidence $ref))
            }
            else {
                $a = $other[0]
                $out.Add((New-DiagResult @common -Id probe.fromMicrosoft -Title $title -Status Problem -Severity Medium -Path $path -Layer Response -Resource $h `
                    -Seen "From this machine, $h ($($a.ip)) answered HTTP $($a.http.status)$(if ($a.http.server) { " from server '$($a.http.server)'" }) without an Azure request ID." `
                    -Likely 'Consistent with a proxy or firewall answering instead of the Azure service.' -Owner NetworkTeam `
                    -Action "Find the proxy, firewall or appliance that answers for $h and let the traffic through to Azure." -Evidence $ref `
                    -Details @{ status = $a.http.status; server = $a.http.server }))
            }
        }
    }

    # probe.comparison — Monitor query hosts vs management.azure.com, to tell an FQDN-specific block from all egress.
    $monitor = @($probes | Where-Object { $_.host -in $script:ProbeMonitorQueryHosts -and ($_.outcome -eq 'Reachable' -or $_.outcome -in $script:ProbeFailedOutcomes) })
    if ($monitor.Count) {
        $title = 'Monitor query hosts compared with management.azure.com'
        $failed = @($monitor | Where-Object { $_.outcome -in $script:ProbeFailedOutcomes })
        $reference = $probes | Where-Object { $_.purpose -eq 'Comparison' } | Select-Object -First 1
        $refs = @($monitor | ForEach-Object { "probe:$($_.host)" }) + @($(if ($reference) { "probe:$($reference.host)" }))
        $cmp = @{ Path = 'MonitorQuery'; Resource = $(if ($reference) { $reference.host } else { 'management.azure.com' }) }
        if (!$failed.Count) {
            $out.Add((New-DiagResult @common @cmp -Id probe.comparison -Title $title -Status OK -Layer Response `
                -Seen "From this machine, $(@($monitor.host) -join ' and ') answered." -Evidence $refs))
        }
        else {
            $first = $failed[0]
            $f = Get-DiagProbeFailure $first.host (Get-DiagProbeWorstAttempt $first)
            $layer = $(if ($f) { $f.Layer } else { 'Route' })
            $failedText = @($failed | ForEach-Object { "$($_.host) ($($_.outcome.ToLowerInvariant()))" }) -join ' and '
            if (!$reference -or ($reference.outcome -ne 'Reachable' -and $reference.outcome -notin $script:ProbeFailedOutcomes)) {
                $out.Add((New-DiagResult @common @cmp -Id probe.comparison -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer $layer `
                    -Seen "From this machine, $failedText failed, and there is no usable reference test of management.azure.com to compare with." `
                    -Needs 'Run the current version of the diagnostic so it also tests management.azure.com.' -Evidence $refs))
            }
            elseif ($reference.outcome -eq 'Reachable') {
                $out.Add((New-DiagResult @common @cmp -Id probe.comparison -Title $title -Status Problem -Severity High -Layer $layer `
                    -Seen "From this machine, $failedText failed while $($reference.host) answered." `
                    -Likely 'Consistent with a rule that affects only the Azure Monitor query hosts (a firewall FQDN rule, TLS inspection or a DNS override), not all outbound traffic.' `
                    -Owner NetworkTeam -Action 'Allow api.loganalytics.io and api.applicationinsights.io on 443 from the agent subnet on the firewall or appliance, and exclude them from TLS inspection.' `
                    -Evidence $refs -Details @{ monitor = @($monitor | ForEach-Object { @{ host = $_.host; outcome = $_.outcome } }); reference = $reference.outcome }))
            }
            else {
                $out.Add((New-DiagResult @common @cmp -Id probe.comparison -Title $title -Status Problem -Severity High -Layer $layer `
                    -Seen "From this machine, $failedText failed, and $($reference.host) failed too ($($reference.outcome.ToLowerInvariant()))." `
                    -Likely 'Consistent with all outbound HTTPS being blocked or held, for example a default route through a firewall or appliance with no allow rules.' `
                    -Owner NetworkTeam -Action 'Check the default route and the firewall or appliance it points to: allow outbound 443 to the Azure services the agent uses.' `
                    -Evidence $refs -Details @{ monitor = @($monitor | ForEach-Object { @{ host = $_.host; outcome = $_.outcome } }); reference = $reference.outcome }))
            }
        }
    }

    , $out.ToArray()
}
