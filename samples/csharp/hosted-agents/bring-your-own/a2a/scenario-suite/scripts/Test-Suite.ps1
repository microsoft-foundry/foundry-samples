# Copyright (c) Microsoft. All rights reserved.
[CmdletBinding(DefaultParameterSetName = "Hosted")]
param(
    [Parameter(ParameterSetName = "Hosted", Mandatory)][string]$Deployments,
    [Parameter(ParameterSetName = "Local", Mandatory)][switch]$Local,
    [Parameter(ParameterSetName = "Local", Mandatory)][string]$SdkRoot,
    [string]$Scenarios,
    [string]$Output
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$arguments = @()
if ($Local) {
    $env:AGENTSERVER_DOTNET_SDK_ROOT = (Resolve-Path -LiteralPath $SdkRoot).Path
    & dotnet build (Join-Path $root "src\ScenarioAgents\ScenarioAgents.csproj") --nologo -v:q
    if ($LASTEXITCODE -ne 0) { throw "Scenario host build failed." }
    $arguments += @("--local-server", (Join-Path $root "src\ScenarioAgents\bin\Debug\net10.0\ScenarioAgents.dll"))
}
else { $arguments += @("--deployments", (Resolve-Path -LiteralPath $Deployments).Path) }
if ($Scenarios) { $arguments += @("--scenarios", $Scenarios) }
if (-not $Output) { $Output = Join-Path $root (".runs\" + (Get-Date -Format "yyyyMMdd-HHmmss-fff")) }
$arguments += @("--output", [IO.Path]::GetFullPath($Output))
& dotnet run --project (Join-Path $root "tools\SuiteRunner\SuiteRunner.csproj") -- @arguments
if ($LASTEXITCODE -ne 0) { throw "Scenario assertions failed. Read '$Output\summary.json' and per-scenario wire evidence." }
