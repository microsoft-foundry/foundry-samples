#requires -Version 7.2
# Runs every check against the healthy baseline and every scenario in tests/scenarios.
# A scenario lists the results it expects; any other result in the same areas must be OK.
param([string]$Filter = '*')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'scripts/Core.ps1')
foreach ($file in Get-ChildItem (Join-Path $root 'scripts/checks') -Filter *.ps1) { . $file.FullName }
. (Join-Path $PSScriptRoot 'Fixtures.ps1')

$script:failures = [Collections.Generic.List[string]]::new()
$script:assertions = 0
function Assert-True { param([bool]$Condition, [string]$Message) $script:assertions++; if (!$Condition) { $script:failures.Add($Message) } }

function Format-Result { param($r) "$($r.id)@$($r.path) [$(Get-ArmName $r.resource)] $($r.status)$(if ($r.severity) { ":$($r.severity)" })$(if ($r.gap) { ":$($r.gap)" }) — $($r.seen)" }

function Test-ResultShape {
    param($Results, [string]$Scenario)
    foreach ($r in $Results) {
        Assert-True ($r.title -and $r.layer -and $r.area) "[$Scenario] $($r.key): missing title/layer/area."
        if ($r.status -eq 'Problem') {
            Assert-True ([bool]$r.seen -and [bool]$r.action -and [bool]$r.owner) "[$Scenario] $($r.key): Problem needs seen, owner and action."
        }
        if ($r.status -eq 'CouldNotCheck') { Assert-True ([bool]$r.seen) "[$Scenario] $($r.key): CouldNotCheck needs seen." }
    }
}

function Invoke-Scenario {
    param([string]$Name, [scriptblock]$Mutate, [hashtable]$Expect, [string[]]$Allow = @())
    $evidence = New-HealthyEvidence
    if ($Mutate) { & $Mutate $evidence }
    # Replay path: every scenario goes through JSON exactly like a customer's evidence file.
    $json = $evidence | ConvertTo-Json -Depth 64
    $evidence = $json | ConvertFrom-Json -AsHashtable
    $results = Invoke-DiagAnalysis $evidence
    Test-ResultShape $results $Name

    $areas = @{}
    $matched = @{}
    foreach ($pattern in $Expect.Keys) {
        $id, $path = $pattern -split '@', 2
        $want = $Expect[$pattern]
        $hits = @($results | Where-Object { $_.id -eq $id -and (!$path -or $_.path -eq $path) })
        Assert-True ($hits.Count -gt 0) "[$Name] expected '$pattern' => $want, but no result had that id."
        if (!$hits.Count) { continue }
        $good = @($hits | Where-Object { ($_.status + $(if ($_.severity) { ":$($_.severity)" }) + $(if ($_.gap) { ":$($_.gap)" })) -eq $want })
        Assert-True ($good.Count -gt 0) "[$Name] '$pattern' expected $want, got $(($hits | ForEach-Object { Format-Result $_ }) -join ' | ')"
        foreach ($hit in $hits) {
            $areas[$hit.area] = $true
            $matched[$hit.key] = $true
            # Other results with the same id (e.g. account vs project) must be OK or the expected status.
            $got = $hit.status + $(if ($hit.severity) { ":$($hit.severity)" }) + $(if ($hit.gap) { ":$($hit.gap)" })
            Assert-True ($got -eq $want -or $hit.status -eq 'OK') "[$Name] '$pattern' unexpected sibling $(Format-Result $hit)"
        }
    }
    foreach ($r in $results) {
        if ($matched[$r.key] -or $r.status -eq 'OK' -or !$areas[$r.area]) { continue }
        if ($Allow -contains $r.id) { continue }
        Assert-True $false "[$Name] unexpected $(Format-Result $r)"
    }
    $results
}

# 1. Healthy baseline: everything OK.
$healthy = Invoke-Scenario -Name 'healthy-private' -Expect @{}
foreach ($r in $healthy) {
    Assert-True ($r.status -eq 'OK') "[healthy-private] not OK: $(Format-Result $r)"
}
Assert-True ($healthy.Count -gt 0) '[healthy-private] produced no results.'

# 2. Scenarios.
$count = 1
foreach ($file in Get-ChildItem (Join-Path $PSScriptRoot 'scenarios') -Filter *.ps1 -ErrorAction SilentlyContinue) {
    foreach ($scenario in @(& $file.FullName)) {
        if ($scenario.Name -notlike $Filter) { continue }
        $null = Invoke-Scenario -Name $scenario.Name -Mutate $scenario.Mutate -Expect $scenario.Expect -Allow @($scenario.Allow)
        $count++
    }
}

# 3. Contract: unknown schema is rejected; a check that throws does not stop the others.
$bad = New-HealthyEvidence; $bad.schema = 99
$threw = $false; try { $null = Invoke-DiagAnalysis $bad } catch { $threw = $true }
Assert-True $threw 'Unsupported schema must throw.'

if ($script:failures.Count) {
    $script:failures | ForEach-Object { Write-Host "FAIL $_" -ForegroundColor Red }
    Write-Host "$($script:failures.Count) of $script:assertions assertions failed across $count scenarios." -ForegroundColor Red
    exit 1
}
Write-Host "PASS $script:assertions assertions, $count scenarios, $($healthy.Count) healthy results." -ForegroundColor Green
