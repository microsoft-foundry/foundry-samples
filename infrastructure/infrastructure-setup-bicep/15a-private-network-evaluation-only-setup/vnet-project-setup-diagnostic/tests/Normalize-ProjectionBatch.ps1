# Offline-only comparison of post-JMESPath output with the native projection.
param([Parameter(Mandatory)][string]$InputPath, [Parameter(Mandatory)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\scripts\ArmReader.ps1')
$cases = Get-Content -LiteralPath $InputPath -Raw | ConvertFrom-Json -AsHashtable
$results = @($cases | ForEach-Object {
    ConvertTo-ArmMetadata $_.data $_.kind $_.collection
})
ConvertTo-Json -InputObject $results -Depth 90 | Set-Content -LiteralPath $OutputPath -Encoding utf8
