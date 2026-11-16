# Network tests from this machine: DNS, TCP, TLS and one unauthenticated HTTPS request per address.
# No credentials are sent. Hosts run in parallel; each stage has a time cap and the whole phase has a deadline.

$script:DiagHostPattern = '^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$'

function Get-DiagProbeTargets {
    param($Discovery, [string[]]$DnsServers)
    $targets = [ordered]@{}
    $add = {
        param([string]$HostName, [string]$Purpose)
        $h = "$HostName".ToLowerInvariant().TrimEnd('.')
        if ($h -match $script:DiagHostPattern -and !$targets.Contains($h) -and $targets.Count -lt 16) {
            $targets[$h] = [ordered]@{ host = $h; port = 443; purpose = $Purpose; resolver = $(if ($DnsServers) { $DnsServers[0] } else { $null }) }
        }
    }
    foreach ($kind in 'Account', 'Storage', 'Workspace', 'AppInsights', 'Model', 'Ampls') {
        foreach ($dep in @($Discovery.dependencies | Where-Object { $_.kind -eq $kind })) { foreach ($h in @($dep.hosts)) { & $add $h $dep.path } }
    }
    & $add 'api.loganalytics.io' 'MonitorQuery'
    & $add 'api.applicationinsights.io' 'MonitorQuery'
    & $add 'management.azure.com' 'Comparison'
    @($targets.Values)
}

# Self-contained so it can run in a parallel runspace.
$script:DiagProbeHost = {
    param($T, $Caps, [datetime]$DeadlineUtc)
    $ErrorActionPreference = 'Stop'
    $rank = @{ Stalled = 6; Blocked = 5; Reset = 4; Refused = 3; TlsFailed = 2; Reachable = 1 }
    $msLeft = { [int]($DeadlineUtc - [datetime]::UtcNow).TotalMilliseconds }
    $socketCode = {
        param($e)
        $x = $e
        while ($x) { if ($x -is [Net.Sockets.SocketException]) { return "$($x.SocketErrorCode)" }; $x = $x.InnerException }
        $null
    }
    $probe = [ordered]@{ host = $T.host; port = $T.port; purpose = $T.purpose; dns = $null; attempts = @(); outcome = $null; budgetHit = $false }

    $dns = [ordered]@{ resolver = $T.resolver; cnameChain = @($T.host); answers = @(); ms = 0; error = $null }
    if ($T.ips) { $dns.answers = @($T.ips) }
    else {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            $task = [Net.Dns]::GetHostAddressesAsync($T.host)
            if (!$task.Wait([math]::Min($Caps.DnsMs, [math]::Max(0, (& $msLeft))))) { $dns.error = 'Timeout' }
            else { $dns.answers = @($task.Result | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | ForEach-Object { $_.IPAddressToString }) }
        }
        catch {
            $dns.error = switch (& $socketCode $_.Exception) { 'HostNotFound' { 'NXDOMAIN' } 'NoData' { 'NXDOMAIN' } 'TryAgain' { 'ServerFailure' } default { 'Other' } }
        }
        $dns.ms = [int]$sw.ElapsedMilliseconds
        if (!$dns.error -and !$dns.answers.Count) { $dns.error = 'NXDOMAIN' }
        if (!$dns.error -and $IsWindows -and (Get-Command Resolve-DnsName -ErrorAction SilentlyContinue)) {
            try {
                $records = Resolve-DnsName -Name $T.host -Type A -DnsOnly -QuickTimeout -ErrorAction Stop
                $dns.cnameChain = @($T.host) + @($records | Where-Object { $_.Type -eq 'CNAME' } | ForEach-Object { "$($_.NameHost)".ToLowerInvariant() })
            }
            catch { }
        }
    }
    $probe.dns = $dns
    if ($dns.error) { $probe.outcome = 'DnsFailed'; return $probe }

    $needMs = $Caps.TcpMs + $Caps.TlsMs + $Caps.FirstByteMs
    $attempts = foreach ($ip in @($dns.answers | Select-Object -First 2)) {
        if ((& $msLeft) -lt $needMs) { $probe.budgetHit = $true; break }
        $a = [ordered]@{ ip = $ip; tcp = $null; tls = $null; http = $null; outcome = $null }
        $client = [Net.Sockets.TcpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
        try {
            $sw = [Diagnostics.Stopwatch]::StartNew()
            try {
                $task = $client.ConnectAsync([Net.IPAddress]::Parse($ip), [int]$T.port)
                if (!$task.Wait($Caps.TcpMs)) { $a.tcp = [ordered]@{ ok = $false; ms = [int]$sw.ElapsedMilliseconds; error = 'Timeout' }; $a.outcome = 'Blocked' }
                else { $a.tcp = [ordered]@{ ok = $true; ms = [int]$sw.ElapsedMilliseconds; error = $null } }
            }
            catch {
                $code = & $socketCode $_.Exception
                $err, $out = switch ($code) {
                    'ConnectionRefused' { 'Refused', 'Refused' } 'ConnectionReset' { 'Reset', 'Reset' } 'TimedOut' { 'Timeout', 'Blocked' }
                    { $_ -in 'NetworkUnreachable', 'HostUnreachable' } { 'Unreachable', 'Blocked' } default { 'Unreachable', 'Blocked' }
                }
                $a.tcp = [ordered]@{ ok = $false; ms = [int]$sw.ElapsedMilliseconds; error = $err }; $a.outcome = $out
            }
            if ($a.outcome) { $a; continue }

            # TLS. The handshake is synchronous so the certificate callback runs on this thread.
            $cert = @{ issuer = $null; root = $null; subject = $null; errors = 'None' }
            $callback = [Net.Security.RemoteCertificateValidationCallback] {
                param($sender, $certificate, $chain, $errors)
                if ($certificate) { $cert.issuer = $certificate.Issuer; $cert.subject = $certificate.Subject }
                if ($chain -and $chain.ChainElements.Count) { $cert.root = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate.Subject }
                $cert.errors = "$errors"
                $true
            }
            $client.ReceiveTimeout = $Caps.TlsMs; $client.SendTimeout = $Caps.TlsMs
            $ssl = [Net.Security.SslStream]::new($client.GetStream(), $false, $callback)
            $sw = [Diagnostics.Stopwatch]::StartNew()
            $tlsError = $null
            try { $ssl.AuthenticateAsClient($T.host) }
            catch {
                $code = & $socketCode $_.Exception
                $tlsError = switch ($code) { 'TimedOut' { 'Timeout' } 'ConnectionReset' { 'Reset' } 'ConnectionAborted' { 'Reset' } default {
                        if ($_.Exception.ToString() -match 'EOF|0 bytes|forcibly closed') { 'Reset' } else { 'Other' } } }
            }
            if (!$tlsError -and $cert.errors -match 'NameMismatch') { $tlsError = 'NameMismatch' }
            elseif (!$tlsError -and $cert.errors -ne 'None') { $tlsError = 'Untrusted' }
            $a.tls = [ordered]@{ ok = !$tlsError; ms = [int]$sw.ElapsedMilliseconds; issuer = $cert.issuer; rootIssuer = $cert.root; subject = $cert.subject; error = $tlsError }
            if ($tlsError) {
                $a.outcome = switch ($tlsError) { 'Timeout' { 'Stalled' } 'Reset' { 'Reset' } default { 'TlsFailed' } }
                $a; continue
            }

            # One unauthenticated request; any HTTP status means the far end answered.
            $client.ReceiveTimeout = $Caps.FirstByteMs
            $request = [Text.Encoding]::ASCII.GetBytes("GET / HTTP/1.1`r`nHost: $($T.host)`r`nUser-Agent: foundry-private-diagnostic`r`nAccept: */*`r`nConnection: close`r`n`r`n")
            $sw = [Diagnostics.Stopwatch]::StartNew()
            $buffer = [byte[]]::new(16384); $read = 0; $httpError = $null; $firstByte = $null
            try {
                $ssl.Write($request, 0, $request.Length); $ssl.Flush()
                $n = $ssl.Read($buffer, 0, $buffer.Length)
                if ($n -eq 0) { $httpError = 'Reset' }
                else {
                    $firstByte = [int]$sw.ElapsedMilliseconds; $read = $n
                    $client.ReceiveTimeout = 2000
                    while ($read -lt $buffer.Length -and [Text.Encoding]::ASCII.GetString($buffer, 0, $read) -notmatch "`r`n`r`n") {
                        try { $n = $ssl.Read($buffer, $read, $buffer.Length - $read) } catch { break }
                        if ($n -eq 0) { break }
                        $read += $n
                    }
                }
            }
            catch {
                $code = & $socketCode $_.Exception
                $httpError = switch ($code) { 'TimedOut' { 'NoResponse' } 'ConnectionReset' { 'Reset' } 'ConnectionAborted' { 'Reset' } default { 'Other' } }
            }
            $head = $(if ($read) { [Text.Encoding]::ASCII.GetString($buffer, 0, $read) } else { '' })
            $status = $null
            if ($head -match '^HTTP/\d(?:\.\d)?\s+(\d{3})') { $status = [int]$Matches[1] } elseif ($read -and !$httpError) { $httpError = 'Other' }
            $server = $null
            if ($head -match '(?im)^server:\s*([^\r\n]{1,80})') { $server = $Matches[1].Trim() }
            $a.http = [ordered]@{
                status = $status; firstByteMs = $firstByte; server = $server
                msRequestId = [bool]($head -match '(?im)^(x-ms-request-id|apim-request-id|x-ms-correlation-request-id|request-id|x-azure-ref|x-ms-ags-diagnostic):')
                error = $httpError
            }
            $a.outcome = $(if ($status) { 'Reachable' } elseif ($httpError -eq 'NoResponse') { 'Stalled' } elseif ($httpError -eq 'Reset') { 'Reset' } else { 'TlsFailed' })
            $ssl.Dispose()
            $a
        }
        finally { $client.Dispose() }
    }
    $probe.attempts = @($attempts)
    $probe.outcome = $(if ($probe.attempts.Count) { @($probe.attempts | Sort-Object { $rank[$_.outcome] } -Descending)[0].outcome } else { 'Skipped' })
    $probe
}

function Invoke-DiagProbes {
    param([Parameter(Mandatory)]$Ctx, [object[]]$Targets)
    if (!$Targets.Count) { return @() }
    $caps = $Ctx.ProbeCaps
    $deadline = [datetime]::UtcNow.AddSeconds($caps.PhaseSec)
    $source = $script:DiagProbeHost.ToString()
    $results = $Targets | ForEach-Object -ThrottleLimit 16 -TimeoutSeconds ($caps.PhaseSec + 15) -Parallel {
        $fn = [scriptblock]::Create($using:source)
        try { & $fn $_ $using:caps $using:deadline }
        catch { [ordered]@{ host = $_.host; error = $_.Exception.Message } }
    }
    $byHost = @{}
    foreach ($r in @($results)) { if ($r -and $r.host -and $r.Contains('dns')) { $byHost[$r.host] = $r } }
    @(foreach ($t in $Targets) {
            if ($byHost.ContainsKey($t.host)) { $byHost[$t.host] }
            else {
                [ordered]@{ host = $t.host; port = $t.port; purpose = $t.purpose; dns = $null; attempts = @(); outcome = 'Skipped'; budgetHit = $true }
            }
        })
}
