# Collection entry point: token, runner facts, Azure reads, then network tests. This is the only stage with I/O.

function New-DiagCollectContext {
    param([int]$Budget = 150, [int]$RequestTimeoutSec = 30)
    [pscustomobject]@{
        Http              = { param($Method, $Uri, $Headers, $Body, $TimeoutSec) Invoke-DiagDefaultHttp $Method $Uri $Headers $Body $TimeoutSec }
        Sleep             = { param($Seconds) Start-Sleep -Seconds $Seconds }
        Imds              = { param($Path) Invoke-DiagImds $Path }
        DnsServers        = { Get-DiagDnsServers }
        Proxy             = { Get-DiagProxy }
        TokenProvider     = { param($Ctx) Get-DiagToken $Ctx }
        Budget            = $Budget
        RequestTimeoutSec = $RequestTimeoutSec
        Cache             = @{}
        Requests          = [Collections.Generic.List[object]]::new()
        Errors            = [Collections.Generic.List[object]]::new()
        BudgetReported    = $false
        Token             = $null
        TokenSource       = $null
        RunnerVmId        = $null
        Probe             = $true
        ProbeCaps         = @{ DnsMs = 5000; TcpMs = 5000; TlsMs = 10000; FirstByteMs = 20000; PhaseSec = 60 }
    }
}

function Get-DiagToolCommit {
    try {
        $c = git -C $PSScriptRoot rev-parse --short HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $c -match '^[0-9a-f]{7,40}$') { return $c }
    }
    catch { }
    'unknown'
}

function Invoke-DiagCollect {
    param([Parameter(Mandatory)][string]$ProjectResourceId, [string]$ConnectionName, $Ctx)
    if (!$Ctx) { $Ctx = New-DiagCollectContext }
    $started = [datetime]::UtcNow
    $timer = [Diagnostics.Stopwatch]::StartNew()

    try { $t = & $Ctx.TokenProvider $Ctx }
    catch {
        Add-DiagCollectorError $Ctx 'token' 'Unauthorized' $_.Exception.Message
        throw [InvalidOperationException]$_.Exception.Message
    }
    $Ctx.Token = $t.Token
    $Ctx.TokenSource = $t.Source

    $runner = Get-DiagRunnerInfo $Ctx
    $Ctx.RunnerVmId = $runner.azureVmResourceId

    $discovery = Invoke-DiagDiscover $Ctx $ProjectResourceId $ConnectionName

    $probes = @()
    if ($Ctx.Probe) {
        $targets = Get-DiagProbeTargets $discovery $runner.dnsServers
        try { $probes = Invoke-DiagProbes $Ctx $targets }
        catch { Add-DiagCollectorError $Ctx 'probe' 'Other' "Network tests failed to run: $($_.Exception.Message)" }
    }
    else {
        $probes = @(foreach ($t in (Get-DiagProbeTargets $discovery $runner.dnsServers)) {
                [ordered]@{ host = $t.host; port = $t.port; purpose = $t.purpose; dns = $null; attempts = @(); outcome = 'Skipped'; budgetHit = $false }
            })
    }
    $Ctx.Token = $null

    [ordered]@{
        schema          = 1
        tool            = [ordered]@{ commit = (Get-DiagToolCommit) }
        run             = [ordered]@{
            startedUtc = $started.ToString('o'); durationMs = [int]$timer.ElapsedMilliseconds; masked = $false
            project = $ProjectResourceId; runner = $runner
        }
        discovery       = $discovery
        requests        = @($Ctx.Requests)
        probes          = @($probes)
        collectorErrors = @($Ctx.Errors)
    }
}
