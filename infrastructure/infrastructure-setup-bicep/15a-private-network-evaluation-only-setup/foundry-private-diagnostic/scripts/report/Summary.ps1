# Builds the run summary from results. Pure: no I/O.

$script:DiagLayerOrder = @('Name', 'Route', 'Nsg', 'Firewall', 'Tls', 'Response', 'Access', 'Config')

function Get-DiagExitCode {
    param([object[]]$Results)
    $Results = @(Get-DiagOnPath $Results)
    if (@($Results | Where-Object status -eq 'Problem').Count) { return 1 }
    if (@($Results | Where-Object { $_.status -eq 'CouldNotCheck' -and $_.gap -eq 'Blocking' }).Count) { return 2 }
    0
}

function Get-DiagCell {
    # Worst result on one layer of one path: Problem > CouldNotCheck > OK; '–' when no checks apply.
    param([object[]]$Results)
    # Where the diagnostic ran describes the runner, not the setup; the headline and star note report it.
    $Results = @(Get-DiagOnPath $Results | Where-Object { $_.id -notin @('runner.match', 'runner.location') })
    if (!$Results.Count) { return '–' }
    $status = $(if ($Results | Where-Object status -eq 'Problem') { 'Problem' }
        elseif ($Results | Where-Object status -eq 'CouldNotCheck') { 'CouldNotCheck' }
        else { 'OK' })
    $decisive = @($Results | Where-Object status -eq $status)
    $machineOnly = !($decisive | Where-Object scope -ne 'ThisMachine')
    $status + $(if ($machineOnly) { '*' } else { '' })
}

function Get-DiagSummary {
    param([Parameter(Mandatory)][object[]]$Results, $Evidence)
    $onPath = @(Get-DiagOnPath $Results)
    $offPath = @($Results | Where-Object { $_.offPath })
    $problems = @($onPath | Where-Object status -eq 'Problem')
    $gaps = @($onPath | Where-Object status -eq 'CouldNotCheck')
    $ok = @($Results | Where-Object status -eq 'OK')

    $runner = $Results | Where-Object id -eq 'runner.match' | Select-Object -First 1
    $runnerMatch = $(if ($runner -and $runner.details.runnerMatch) { $runner.details.runnerMatch } else { 'Unknown' })
    $runnerDiffers = @($(if ($runner -and $runner.details.differs) { $runner.details.differs }))

    $used = @()
    if ($Evidence -and $Evidence.discovery -and $Evidence.discovery.paths) {
        $used = @($script:DiagPaths | Where-Object { $Evidence.discovery.paths[$_] -and $Evidence.discovery.paths[$_].used })
    }
    if (!$used.Count) { $used = @($Results | Where-Object path | ForEach-Object path | Select-Object -Unique) }

    $paths = foreach ($path in $script:DiagPaths | Where-Object { $_ -in $used }) {
        # Project-wide results (no path) count for every used path.
        $pathResults = @($Results | Where-Object { $_.path -eq $path -or !$_.path })
        $layers = [ordered]@{}
        foreach ($layer in $script:DiagLayerOrder) {
            $layers[$layer] = Get-DiagCell @($pathResults | Where-Object layer -eq $layer)
        }
        $first = $script:DiagLayerOrder | Where-Object { $layers[$_] -like 'Problem*' } | Select-Object -First 1
        [ordered]@{ path = $path; layers = $layers; firstProblem = $(if ($first) { $first } else { $null }) }
    }

    $parts = @()
    $parts += "$($problems.Count) problem$(if ($problems.Count -ne 1) { 's' })"
    $blocking = @($gaps | Where-Object gap -eq 'Blocking').Count
    if ($gaps.Count) { $parts += "$($gaps.Count) couldn't check$(if ($blocking -ne $gaps.Count) { " ($blocking blocking)" })" }
    $parts += "$($ok.Count) OK"
    if ($offPath.Count) { $parts += "$($offPath.Count) from this machine" }

    [ordered]@{
        headline      = $parts -join ', '
        exitCode      = Get-DiagExitCode $Results
        runnerMatch   = $runnerMatch
        runnerDiffers = $runnerDiffers
        paths         = @($paths)
    }
}

function Get-DiagSortedProblems {
    # High before Medium before Low, then by the layer order (earliest layer is usually the cause).
    param([object[]]$Results)
    $sev = @{ High = 0; Medium = 1; Low = 2 }
    @(Get-DiagOnPath $Results | Where-Object status -eq 'Problem' |
        Sort-Object { $sev[$_.severity] }, { [array]::IndexOf($script:DiagLayerOrder, $_.layer) }, key)
}

# Results that describe the setup; offPath ones only describe the machine that ran the diagnostic.
function Get-DiagOnPath {
    param([object[]]$Results)
    @($Results | Where-Object { $_ -and !$_.offPath })
}