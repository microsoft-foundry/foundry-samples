#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$ConfigPath,[Parameter(Mandatory)][string]$OutputPath,[string]$BaselinePath)
. (Join-Path $PSScriptRoot 'Inspection.ps1')
$config = Read-SetupConfig $ConfigPath
Assert-SetupContext $config
$report = Get-Inspection $config
if ($BaselinePath) {
    $baseline = Read-Json $BaselinePath
    $report.diff = @(Get-SemanticDiff @{ state = $baseline.state; foundry = $baseline.foundry } @{ state = $report.state; foundry = $report.foundry })
    $report.diffMeaning = 'Observed settings differences, not an automatic repair or a benign-policy classification.'
}
Write-Json $OutputPath $report
