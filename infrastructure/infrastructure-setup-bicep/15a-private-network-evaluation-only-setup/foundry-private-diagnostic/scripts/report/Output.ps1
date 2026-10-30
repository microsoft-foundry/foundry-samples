# Console and markdown output. Reads results and summary only; writes nothing to Azure.

$script:DiagPathLabels = @{ Foundry = 'Foundry'; Storage = 'Storage'; MonitorQuery = 'Monitor query'; Models = 'Models' }
$script:DiagOwnerLabels = @{ AzureAdmin = 'Azure admin'; NetworkTeam = 'Network team'; ResourceOwner = 'Resource owner'; Customer = 'You' }
$script:DiagLayerLabels = [ordered]@{ Name = 'Name'; Route = 'Route'; Nsg = 'NSG'; Firewall = 'Firewall'; Tls = 'TLS'; Response = 'Response'; Access = 'Access'; Config = 'Config' }

function Format-DiagCell {
    param([string]$Cell)
    $star = $(if ($Cell.EndsWith('*')) { '*' } else { '' })
    $label = switch ($Cell.TrimEnd('*')) { 'Problem' { 'PROBLEM' } 'CouldNotCheck' { '?' } 'OK' { 'OK' } default { '–' } }
    "$label$star"
}

function Get-DiagTarget {
    param($Evidence)
    $project = $(if ($Evidence -and $Evidence.run) { $Evidence.run.project })
    if (!$project) { return 'unknown project' }
    "$(Get-ArmName $project) ($(Get-ArmName (Get-ArmParent $project)))"
}

function Get-DiagPathTable {
    # Returns rows of fixed-width text.
    param($Summary)
    $width = 15
    $header = 'Path'.PadRight($width) + (($script:DiagLayerLabels.Values | ForEach-Object { $_.PadRight(10) }) -join '')
    $rows = foreach ($p in $Summary.paths) {
        $script:DiagPathLabels[$p.path].PadRight($width) +
            (($script:DiagLayerLabels.Keys | ForEach-Object { (Format-DiagCell $p.layers[$_]).PadRight(10) }) -join '')
    }
    @($header) + @($rows)
}

function Get-DiagStarNote {
    param($Summary)
    $starred = $Summary.paths | Where-Object { $_.layers.Values -match '\*$' }
    if (!$starred) { return $null }
    $note = '* decided only by tests from this machine'
    switch ($Summary.runnerMatch) {
        'Match' { "$note; it uses the same network path as the agent subnet." }
        'Unknown' { "$note; couldn't confirm it uses the agent subnet's network path." }
        default { "$note; its network path differs from the agent subnet ($($Summary.runnerDiffers -join '; '))." }
    }
}

function Get-DiagProblemCard {
    param($Result)
    $lines = @("PROBLEM ($($Result.severity)) $($Result.title)")
    $lines += "  Seen:   $($Result.seen)"
    if ($Result.likely) { $lines += "  Likely: $($Result.likely)" }
    $lines += "  Owner:  $($script:DiagOwnerLabels[$Result.owner])"
    $lines += "  Action: $($Result.action)"
    $lines
}

function Get-DiagGapLine {
    param($Result)
    "$($Result.title): $($Result.seen) Needs: $($Result.needs)"
}

$script:DiagMachineHeading = 'FROM THIS MACHINE (not confirmed on the agent network, so not counted as problems)'

function Get-DiagMachineLines {
    param([object[]]$Results)
    @($Results | Where-Object { $_.offPath } | Sort-Object key | ForEach-Object {
            $seen = "$($_.seen)" -replace '^From this machine, ', ''
            $text = $(if ($seen -ne "$($_.seen)") { $seen } else { "$($_.title): $seen" })
            "$(if ($_.status -eq 'Problem') { 'Failed' } else { 'Not tested' }) — $text"
        })
}

function Write-DiagConsole {
    param([Parameter(Mandatory)]$Summary, [Parameter(Mandatory)][object[]]$Results, $Evidence, [string[]]$Files = @())
    $when = $(if ($Evidence -and $Evidence.run -and $Evidence.run.startedUtc) { ([datetime]$Evidence.run.startedUtc).ToUniversalTime().ToString('yyyy-MM-dd HH:mm') + ' UTC' })
    Write-Host ''
    Write-Host "Foundry private diagnostic — $(Get-DiagTarget $Evidence)    $when"
    $color = switch ($Summary.exitCode) { 0 { 'Green' } 1 { 'Red' } default { 'Yellow' } }
    Write-Host "$($Summary.headline)    Exit $($Summary.exitCode)" -ForegroundColor $color
    Write-Host ''
    Get-DiagPathTable $Summary | ForEach-Object { Write-Host $_ }
    $note = Get-DiagStarNote $Summary
    if ($note) { Write-Host $note -ForegroundColor DarkGray }
    foreach ($r in Get-DiagSortedProblems $Results) {
        Write-Host ''
        $card = @(Get-DiagProblemCard $r)
        Write-Host $card[0] -ForegroundColor Red
        $card | Select-Object -Skip 1 | ForEach-Object { Write-Host $_ }
    }
    $blocking = @(Get-DiagOnPath $Results | Where-Object { $_.status -eq 'CouldNotCheck' -and $_.gap -eq 'Blocking' })
    if ($blocking.Count) {
        Write-Host ''
        Write-Host "COULDN'T CHECK" -ForegroundColor Yellow
        $blocking | ForEach-Object { Write-Host "  $(Get-DiagGapLine $_)" }
    }
    $limits = @(Get-DiagOnPath $Results | Where-Object gap -eq 'KnownLimit').Count
    if ($limits) { Write-Host "  $limits known limit(s) listed in report.md." -ForegroundColor DarkGray }
    $machine = @(Get-DiagMachineLines $Results)
    if ($machine.Count) {
        Write-Host ''
        Write-Host $script:DiagMachineHeading -ForegroundColor DarkGray
        $machine | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    }
    Write-Host ''
    Write-Host 'Send support: evidence.json (no secrets; add -Mask to hide names).'
    $Files | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
}

function ConvertTo-DiagMarkdownCell { param([string]$Text) ($Text -replace '\|', '\|' -replace "`r?`n", ' ') }

function Get-DiagReportMarkdown {
    param([Parameter(Mandatory)]$Summary, [Parameter(Mandatory)][object[]]$Results, $Evidence)
    $md = [Collections.Generic.List[string]]::new()
    $md.Add("# Foundry private diagnostic — $(Get-DiagTarget $Evidence)")
    $md.Add('')
    $md.Add("**$($Summary.headline)** · exit code $($Summary.exitCode)$(if ($Evidence -and $Evidence.run.startedUtc) { " · $($Evidence.run.startedUtc)" })")
    $md.Add('')
    $md.Add('| Path | ' + ($script:DiagLayerLabels.Values -join ' | ') + ' |')
    $md.Add('|---|' + (($script:DiagLayerLabels.Keys | ForEach-Object { '---' }) -join '|') + '|')
    foreach ($p in $Summary.paths) {
        $md.Add("| $($script:DiagPathLabels[$p.path]) | " + (($script:DiagLayerLabels.Keys | ForEach-Object { Format-DiagCell $p.layers[$_] }) -join ' | ') + ' |')
    }
    $note = Get-DiagStarNote $Summary
    if ($note) { $md.Add(''); $md.Add("_$($note)_") }
    $md.Add(''); $md.Add('`?` = couldn''t check · `–` = not in this path')

    $problems = Get-DiagSortedProblems $Results
    if ($problems.Count) {
        $md.Add(''); $md.Add('## Problems')
        foreach ($r in $problems) {
            $md.Add(''); $md.Add("### $($r.severity): $($r.title)")
            $md.Add("- **Seen:** $($r.seen)")
            if ($r.likely) { $md.Add("- **Likely:** $($r.likely)") }
            $md.Add("- **Owner:** $($script:DiagOwnerLabels[$r.owner])")
            $md.Add("- **Action:** $($r.action)")
        }
    }
    foreach ($group in @(@{ Gap = 'Blocking'; Title = "Couldn't check" }, @{ Gap = 'KnownLimit'; Title = 'Known limits' })) {
        $items = @(Get-DiagOnPath $Results | Where-Object { $_.status -eq 'CouldNotCheck' -and $_.gap -eq $group.Gap })
        if (!$items.Count) { continue }
        $md.Add(''); $md.Add("## $($group.Title)")
        $md.Add('')
        $items | ForEach-Object { $md.Add("- **$($_.title):** $($_.seen) _Needs:_ $($_.needs)") }
        foreach ($item in $items | Where-Object { $_.details.checklist }) {
            $md.Add(''); $md.Add("**Checklist — $($item.title)**")
            $item.details.checklist | ForEach-Object { $md.Add("- [ ] $_") }
        }
    }
    $machine = @(Get-DiagMachineLines $Results)
    if ($machine.Count) {
        $md.Add(''); $md.Add('## From this machine'); $md.Add('')
        $md.Add('_This machine isn''t confirmed on the agent network, so these network tests don''t count as problems. Run the diagnostic from a VM in the agent virtual network to test the agent path._')
        $md.Add('')
        $machine | ForEach-Object { $md.Add("- $_") }
    }
    $queries = @($Results | Where-Object { $_.details.kql })
    if ($queries.Count) {
        $md.Add(''); $md.Add('## Firewall log query')
        $md.Add(''); $md.Add('Replace `<INCIDENT_TIME_UTC>` with the time an evaluation failed, then run this in the Log Analytics workspace that receives the firewall logs.')
        foreach ($q in $queries) { $md.Add(''); $md.Add('```kusto'); $md.Add($q.details.kql); $md.Add('```') }
    }
    $md.Add(''); $md.Add('## What to send support')
    $md.Add(''); $md.Add('Send `evidence.json`. It contains Azure configuration metadata and network test results, but no keys, tokens, connection strings or data. Run with `-Mask` to replace resource names.')
    $md -join "`n"
}

function Get-DiagDetailsMarkdown {
    param([Parameter(Mandatory)][object[]]$Results)
    $md = [Collections.Generic.List[string]]::new()
    $md.Add('# Foundry private diagnostic — details'); $md.Add('')
    $md.Add('Every check, grouped by area. `*` in the summary table means the result came from tests on this machine.')
    foreach ($area in $script:DiagAreas) {
        $items = @($Results | Where-Object area -eq $area | Sort-Object key)
        if (!$items.Count) { continue }
        $md.Add(''); $md.Add("## $area"); $md.Add('')
        $md.Add('| Check | Status | Path | Layer | Resource | Seen |'); $md.Add('|---|---|---|---|---|---|')
        foreach ($r in $items) {
            $status = $r.status + $(if ($r.severity) { " ($($r.severity))" } elseif ($r.gap) { " ($($r.gap))" })
            $md.Add("| $($r.id) | $status | $($r.path) | $($r.layer) | $(Get-ArmName $r.resource) | $(ConvertTo-DiagMarkdownCell $r.seen) |")
        }
        foreach ($r in $items | Where-Object { $_.status -ne 'OK' -or $_.details.Count }) {
            $md.Add(''); $md.Add("<details><summary>$($r.id) — $(Get-ArmName $r.resource) $($r.path)</summary>"); $md.Add('')
            if ($r.resource) { $md.Add("Resource: ``$($r.resource)``"); $md.Add('') }
            if ($r.needs) { $md.Add("Needs: $($r.needs)"); $md.Add('') }
            if ($r.evidence.Count) { $md.Add('Evidence:'); $r.evidence | ForEach-Object { $md.Add("- ``$_``") }; $md.Add('') }
            if ($r.details.Count) { $md.Add('```json'); $md.Add(($r.details | ConvertTo-Json -Depth 16)); $md.Add('```') }
            $md.Add('</details>')
        }
    }
    $md -join "`n"
}
