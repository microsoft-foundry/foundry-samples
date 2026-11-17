# Copyright (c) Microsoft. All rights reserved.

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $ProjectResourceId,
    [Parameter(Mandatory)]
    [string] $DeploymentDirectory,
    [string] $EnvironmentName = "echo-a2a-dotnet-dev"
)

$ErrorActionPreference = "Stop"
$source = Split-Path $PSScriptRoot -Parent

$destination = [IO.Path]::GetFullPath($DeploymentDirectory)
$sourcePrefix = $source.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if ($destination.Equals($source, [StringComparison]::OrdinalIgnoreCase) -or
    $destination.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "DeploymentDirectory must be outside this sample. azd cannot copy a template into itself."
}

$projectDirectory = Join-Path $destination "echo-a2a-dotnet"
if (Test-Path -LiteralPath $projectDirectory) {
    throw "The deployment copy already exists. To redeploy it, enter '$projectDirectory' and run 'azd deploy echo-a2a-dotnet --no-prompt'."
}

New-Item -ItemType Directory -Path $destination -Force | Out-Null
Push-Location $destination
try {
    & azd ai agent init -m (Join-Path $source "azure.yaml") `
        --project-id $ProjectResourceId --deploy-mode code --runtime dotnet_10 `
        --entry-point EchoA2A.dll --dep-resolution bundled `
        --environment $EnvironmentName --no-prompt
    if ($LASTEXITCODE -ne 0) { throw "azd initialization failed; no deployment was attempted." }

    Set-Location -LiteralPath $projectDirectory
    & azd ai project show --output json
    if ($LASTEXITCODE -ne 0) { throw "Could not verify the selected Foundry project." }

    & azd deploy echo-a2a-dotnet --no-prompt
    if ($LASTEXITCODE -ne 0) { throw "Foundry deployment failed. Inspect azd diagnostics before retrying." }
}
finally {
    Pop-Location
}
