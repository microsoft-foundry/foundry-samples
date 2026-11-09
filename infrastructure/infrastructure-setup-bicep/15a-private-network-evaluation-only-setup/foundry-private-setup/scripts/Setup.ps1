#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('Toolchain','Plan','Run','Preview','Apply','Reconcile')][string]$Action,
    [string]$ConfigPath,[string]$GraphPath,[string]$OutputPath,[string]$ApprovePlan,
    [string[]]$Nodes,[string]$StateDirectory,[string]$ApprovalsPath,[ValidateRange(1,3)][int]$Concurrency = 3,
    [switch]$AcknowledgeAccountWideImpact)
$entry = @{}; foreach ($key in $PSBoundParameters.Keys) { $entry[$key] = $PSBoundParameters[$key] }
. (Join-Path $PSScriptRoot 'SetupEngine.ps1')
switch ($entry.Action) {
    'Toolchain' {
        $tools = Get-SetupToolchain
        @{ versions = $tools.versions; powerShell = $PSVersionTable.PSVersion.ToString(); bicep = $tools.bicepVersion
            changes = 'None; preinstalled tools only.' } | ConvertTo-Json
    }
    'Plan' {
        $setupInput = Read-SetupInput $entry.ConfigPath
        $graph = New-SetupPlan $setupInput.config $setupInput.options
        Write-Json $entry.OutputPath $graph
        Get-PlanSummary $graph | ConvertTo-Json -Depth 6
    }
    'Run' {
        $graph = Read-Json $entry.GraphPath
        Invoke-SetupRun $graph $entry.StateDirectory $entry.ApprovePlan ([bool]$entry['AcknowledgeAccountWideImpact']) $Concurrency | ConvertTo-Json -Depth 6
    }
    default {
        $graph = Read-Json $entry.GraphPath
        $approvals = if ($entry.Contains('ApprovalsPath')) { Read-Json $entry.ApprovalsPath } else { @{} }
        Invoke-SetupSelection $graph $entry.Nodes $entry.Action $entry.StateDirectory $approvals $Concurrency ([bool]$entry['AcknowledgeAccountWideImpact'])
    }
}
