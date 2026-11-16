#requires -Version 7.2
# End-to-end report tests: replays evidence through Diagnose.ps1 and checks exit codes and output files.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$diagnose = Join-Path $root 'scripts/Diagnose.ps1'
. (Join-Path $root 'scripts/Core.ps1')
foreach ($file in Get-ChildItem (Join-Path $root 'scripts/checks') -Filter *.ps1) { . $file.FullName }
foreach ($file in Get-ChildItem (Join-Path $root 'scripts/report') -Filter *.ps1) { . $file.FullName }
. (Join-Path $PSScriptRoot 'Fixtures.ps1')

$script:failures = [Collections.Generic.List[string]]::new()
$script:assertions = 0
function Assert-True { param([bool]$Condition, [string]$Message) $script:assertions++; if (!$Condition) { $script:failures.Add($Message) } }

$work = Join-Path ([IO.Path]::GetTempPath()) "fpd-report-$([guid]::NewGuid().ToString('n').Substring(0, 8))"
$null = New-Item -ItemType Directory -Path $work

function Invoke-Replay {
    param([string]$Name, [scriptblock]$Mutate)
    $evidence = New-HealthyEvidence
    if ($Mutate) { & $Mutate $evidence }
    $evidence.Remove('_index')
    $file = Join-Path $work "$Name.json"
    $evidence | ConvertTo-Json -Depth 64 | Set-Content -LiteralPath $file -Encoding utf8NoBOM
    $out = Join-Path $work $Name
    $console = & pwsh -NoProfile -File $diagnose -EvidencePath $file -OutputDirectory $out 2>&1 | Out-String
    [pscustomobject]@{
        Exit    = $LASTEXITCODE
        Console = $console
        Report  = Get-Content (Join-Path $out 'report.md') -Raw -ErrorAction SilentlyContinue
        Details = Get-Content (Join-Path $out 'details.md') -Raw -ErrorAction SilentlyContinue
        Results = Get-Content (Join-Path $out 'results.json') -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -AsHashtable
        Out     = $out
    }
}

try {
    # Exit 0: healthy.
    $run = Invoke-Replay 'healthy'
    Assert-True ($run.Exit -eq 0) "healthy: exit $($run.Exit), expected 0. $($run.Console)"
    Assert-True ($run.Results.summary.exitCode -eq 0) 'healthy: summary.exitCode should be 0.'
    Assert-True ($run.Report -match '0 problems') 'healthy: report headline missing.'
    Assert-True (!(Test-Path (Join-Path $run.Out 'evidence.json'))) 'replay must not rewrite evidence.json.'
    Assert-True ($run.Report -notmatch '## Problems') 'healthy: report should have no problems section.'

    # Exit 1: a problem.
    $run = Invoke-Replay 'problem' { param($E) (Get-EvData $E (Get-TestIds).AgentSubnet).properties.delegations = @() }
    Assert-True ($run.Exit -eq 1) "problem: exit $($run.Exit), expected 1."
    Assert-True ($run.Console -match 'PROBLEM \(High\) Agent subnet delegation') 'problem: console card missing.'
    Assert-True ($run.Report -match '### High: Agent subnet delegation') 'problem: report card missing.'
    Assert-True ($run.Report -match '\*\*Action:\*\* ') 'problem: report action missing.'
    Assert-True ($run.Details -match '\| subnet.delegation \| Problem \(High\)') 'problem: details row missing.'
    $cfg = $run.Results.summary.paths | Where-Object path -eq 'Foundry'
    Assert-True ($cfg.firstProblem -eq 'Config') "problem: firstProblem '$($cfg.firstProblem)', expected Config."

    # Exit 2: only a blocking gap.
    $run = Invoke-Replay 'blocking' { param($E) Set-EvStatus $E (Get-TestIds).Vnet 403 }
    Assert-True ($run.Exit -eq 2) "blocking: exit $($run.Exit), expected 2."
    Assert-True ($run.Report -match "## Couldn't check") 'blocking: report gap section missing.'
    Assert-True ($run.Console -match "COULDN'T CHECK") 'blocking: console gap section missing.'

    # Known limits don't change the exit code.
    $run = Invoke-Replay 'known-limit' { param($E) Remove-EvRequest $E "$((Get-TestIds).Project)/connections" }
    Assert-True ($run.Exit -eq 0) "known-limit: exit $($run.Exit), expected 0."
    Assert-True ($run.Report -match '## Known limits') 'known-limit: report section missing.'

    # Off the agent network: this machine's network findings are listed apart and don't change the exit code.
    $run = Invoke-Replay 'off-path' { param($E)
        $E.discovery.runner = [ordered]@{ vm = $null; nic = $null; subnet = $null }; $E.run.runner.azureVmResourceId = $null
        $h = (Get-EvProbe $E 'acct.services.ai.azure.com').attempts[0].http; $h.msRequestId = $false; $h.status = 403; $h.server = 'squid' }
    Assert-True ($run.Exit -eq 0) "off-path: exit $($run.Exit), expected 0. $($run.Console)"
    Assert-True ($run.Console -match 'FROM THIS MACHINE') 'off-path: console section missing.'
    Assert-True ($run.Console -notmatch 'PROBLEM \(') 'off-path: console should have no problem cards.'
    Assert-True ($run.Report -match '## From this machine') 'off-path: report section missing.'
    Assert-True ($run.Report -match '\d+ from this machine') 'off-path: headline count missing.'
    $flagged = @($run.Results.results | Where-Object { $_.id -eq 'probe.fromMicrosoft' -and $_.status -eq 'Problem' })
    Assert-True ($flagged.Count -eq 1 -and $flagged[0].offPath) 'off-path: probe.fromMicrosoft should be marked offPath.'

    # Exit 3: input errors, including parameter binding.
    foreach ($case in @(
            @{ Name = 'unknown-param'; Args = @('-Bogus', '1') },
            @{ Name = 'bad-project-id'; Args = @('-ProjectResourceId', 'not-an-id') },
            @{ Name = 'partial-project'; Args = @('-SubscriptionId', 'x') },
            @{ Name = 'missing-evidence'; Args = @('-EvidencePath', (Join-Path $work 'nope.json')) },
            @{ Name = 'replay-with-mask'; Args = @('-EvidencePath', (Join-Path $work 'healthy.json'), '-Mask') })) {
        $null = & pwsh -NoProfile -File $diagnose @($case.Args) 2>&1
        Assert-True ($LASTEXITCODE -eq 3) "$($case.Name): exit $LASTEXITCODE, expected 3."
    }
    $bad = New-HealthyEvidence; $bad.schema = 99; $bad.Remove('_index')
    $badFile = Join-Path $work 'schema.json'; $bad | ConvertTo-Json -Depth 64 | Set-Content $badFile
    $null = & pwsh -NoProfile -File $diagnose -EvidencePath $badFile -OutputDirectory (Join-Path $work 'schema') 2>&1
    Assert-True ($LASTEXITCODE -eq 3) "unsupported schema: exit $LASTEXITCODE, expected 3."

    # Summary rules (pure).
    $r = @(
        (New-DiagResult -Id a.one -Area Probe -Title A -Status Problem -Severity High -Scope ThisMachine -Path MonitorQuery -Layer Response -Seen s -Owner NetworkTeam -Action x),
        (New-DiagResult -Id a.two -Area Firewall -Title B -Status CouldNotCheck -Gap Blocking -Path MonitorQuery -Layer Firewall -Seen s -Needs n),
        (New-DiagResult -Id a.three -Area Probe -Title C -Status OK -Scope ThisMachine -Path MonitorQuery -Layer Tls -Seen s))
    $s = Get-DiagSummary -Results $r
    $p = $s.paths | Where-Object path -eq 'MonitorQuery'
    Assert-True ($p.layers.Response -eq 'Problem*') "summary: Response '$($p.layers.Response)', expected Problem*."
    Assert-True ($p.layers.Firewall -eq 'CouldNotCheck') "summary: Firewall '$($p.layers.Firewall)', expected CouldNotCheck."
    Assert-True ($p.layers.Tls -eq 'OK*') "summary: Tls '$($p.layers.Tls)', expected OK*."
    Assert-True ($p.layers.Name -eq '–') "summary: Name '$($p.layers.Name)', expected –."
    Assert-True ($p.firstProblem -eq 'Response') "summary: firstProblem '$($p.firstProblem)'."
    Assert-True ($s.exitCode -eq 1) 'summary: problem + blocking should exit 1.'
    Assert-True ($s.runnerMatch -eq 'Unknown') 'summary: runnerMatch should default to Unknown.'
}
finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}

if ($script:failures.Count) {
    $script:failures | ForEach-Object { Write-Host "FAIL $_" -ForegroundColor Red }
    Write-Host "$($script:failures.Count) of $script:assertions assertions failed." -ForegroundColor Red
    exit 1
}
Write-Host "PASS $script:assertions report assertions." -ForegroundColor Green
