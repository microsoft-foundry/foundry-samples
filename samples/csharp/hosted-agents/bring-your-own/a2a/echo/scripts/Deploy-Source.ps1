# Copyright (c) Microsoft. All rights reserved.

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $SdkRoot,
    [Parameter(Mandatory)]
    [string] $ProjectResourceId,
    [Parameter(Mandatory)]
    [string] $DeploymentDirectory,
    [string] $EnvironmentName = "echo-a2a-dotnet-dev"
)

$ErrorActionPreference = "Stop"
$source = Split-Path $PSScriptRoot -Parent
$sdk = (Resolve-Path -LiteralPath $SdkRoot).Path
$sdkProject = Join-Path $sdk "sdk\agentserver\Azure.AI.AgentServer.A2A\src\Azure.AI.AgentServer.A2A.csproj"
if (-not (Test-Path -LiteralPath $sdkProject)) {
    throw "SdkRoot must contain the unpublished Azure.AI.AgentServer.A2A project."
}

$destination = [IO.Path]::GetFullPath($DeploymentDirectory)
$sourcePrefix = $source.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if ($destination.Equals($source, [StringComparison]::OrdinalIgnoreCase) -or
    $destination.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "DeploymentDirectory must be outside this sample. azd cannot copy a template into itself."
}

$projectDirectory = Join-Path $destination "echo-a2a-dotnet"
if (Test-Path -LiteralPath $projectDirectory) {
    throw "The deployment copy already exists. To redeploy it, set AGENTSERVER_DOTNET_SDK_ROOT, enter '$projectDirectory', and run 'azd deploy echo-a2a-dotnet --no-prompt'."
}

$previousSdkRoot = $env:AGENTSERVER_DOTNET_SDK_ROOT
$env:AGENTSERVER_DOTNET_SDK_ROOT = $sdk
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
    $env:AGENTSERVER_DOTNET_SDK_ROOT = $previousSdkRoot
}
