#requires -Version 7.2
<#
.SYNOPSIS
Read-only diagnostic for Foundry projects that use a private network.

.DESCRIPTION
Reads the project's Azure configuration (REST, read-only), tests the network path from this machine,
and reports what is OK, what is a problem, and what it couldn't check.
Writes evidence.json, results.json, report.md and details.md to the output directory.

Exit codes: 0 no problems; 1 problems found; 2 couldn't check something important; 3 script or input error.

.EXAMPLE
./Diagnose.ps1 -ProjectResourceId /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>

.EXAMPLE
./Diagnose.ps1 -EvidencePath ./evidence.json   # replay a saved evidence file offline
#>
param(
    [string]$ProjectResourceId,
    [string]$SubscriptionId,
    [string]$ResourceGroup,
    [string]$AccountName,
    [string]$ProjectName,
    [string]$ConnectionName,
    [string]$OutputDirectory,
    [string]$EvidencePath,
    [switch]$Mask,
    [Parameter(ValueFromRemainingArguments)][object[]]$UnknownArguments
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
. (Join-Path $root 'Core.ps1')
# Dot-source at script scope so the functions stay visible to Invoke-DiagAnalysis.
foreach ($folder in 'checks', 'report', 'collect') {
    $dir = Join-Path $root $folder
    if (Test-Path $dir) { foreach ($file in Get-ChildItem $dir -Filter *.ps1) { . $file.FullName } }
}

function Resolve-DiagProjectId {
    if ($ProjectResourceId) {
        if ($ProjectResourceId -notmatch '^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.CognitiveServices/accounts/[^/]+/projects/[^/]+$') {
            throw [ArgumentException]'ProjectResourceId must look like /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>.'
        }
        return $ProjectResourceId.TrimEnd('/')
    }
    $missing = @('SubscriptionId', 'ResourceGroup', 'AccountName', 'ProjectName' | Where-Object { !(Get-Variable $_ -ValueOnly) })
    if ($missing.Count) { throw [ArgumentException]"Give -ProjectResourceId, or all of: -$($missing -join ', -')." }
    "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName/projects/$ProjectName"
}

function Write-DiagJson {
    param($Value, [string]$Path)
    $Value | ConvertTo-Json -Depth 64 | Set-Content -LiteralPath $Path -Encoding utf8NoBOM
}

try {
    if ($UnknownArguments) { throw [ArgumentException]"Unknown argument(s): $($UnknownArguments -join ' '). Run Get-Help ./Diagnose.ps1." }
    if ($EvidencePath) {
        if ($ProjectResourceId -or $SubscriptionId -or $Mask) { throw [ArgumentException]'-EvidencePath replays a saved file; don''t combine it with project parameters or -Mask.' }
        if (!(Test-Path -LiteralPath $EvidencePath -PathType Leaf)) { throw [ArgumentException]"Evidence file not found: $EvidencePath" }
        $evidence = Get-Content -LiteralPath $EvidencePath -Raw | ConvertFrom-Json -AsHashtable
    }
    else {
        $projectId = Resolve-DiagProjectId
        if (!(Get-Command Invoke-DiagCollect -ErrorAction SilentlyContinue)) { throw 'Collector scripts are missing from scripts/collect.' }
        $evidence = Invoke-DiagCollect -ProjectResourceId $projectId -ConnectionName $ConnectionName
        if ($Mask) { $evidence = ConvertTo-DiagMaskedEvidence $evidence }
    }

    $outDir = $(if ($OutputDirectory) { $OutputDirectory } else { Join-Path (Get-Location) "foundry-diagnostic-$((Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss'))" })
    $null = New-Item -ItemType Directory -Force -Path $outDir

    if (!$EvidencePath) {
        $evidence.Remove('_index')
        Write-DiagJson $evidence (Join-Path $outDir 'evidence.json')
    }
    $results = Invoke-DiagAnalysis $evidence
    $summary = Get-DiagSummary -Results $results -Evidence $evidence

    $files = @()
    if (!$EvidencePath) { $files += Join-Path $outDir 'evidence.json' }
    Write-DiagJson ([ordered]@{ summary = $summary; results = $results }) (Join-Path $outDir 'results.json')
    Get-DiagReportMarkdown -Summary $summary -Results $results -Evidence $evidence | Set-Content -LiteralPath (Join-Path $outDir 'report.md') -Encoding utf8NoBOM
    Get-DiagDetailsMarkdown -Results $results | Set-Content -LiteralPath (Join-Path $outDir 'details.md') -Encoding utf8NoBOM
    $files += 'results.json', 'report.md', 'details.md' | ForEach-Object { Join-Path $outDir $_ }

    Write-DiagConsole -Summary $summary -Results $results -Evidence $evidence -Files $files
    exit $summary.exitCode
}
catch {
    $message = $(if ($_.Exception -is [ArgumentException]) { "Input error: $($_.Exception.Message)" } else { "Diagnostic failed: $($_.Exception.Message)" })
    Write-Host $message -ForegroundColor Red
    exit 3
}
