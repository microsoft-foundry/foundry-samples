# Copyright (c) Microsoft. All rights reserved.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SdkRoot,
    [Parameter(Mandatory)][string]$ProjectResourceId,
    [Parameter(Mandatory)][string]$DeploymentDirectory,
    [string]$EnvironmentName = "dotnet-a2a-suite",
    [string]$StateFile,
    [ValidateRange(1, 12)][int[]]$Scenarios = (1..12)
)
$ErrorActionPreference = "Stop"
$source = Split-Path $PSScriptRoot -Parent
$destination = [IO.Path]::GetFullPath($DeploymentDirectory)
if ($destination.StartsWith($source.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $destination.Equals($source, [StringComparison]::OrdinalIgnoreCase)) { throw "Use a deployment directory outside this sample." }
$env:AGENTSERVER_DOTNET_SDK_ROOT = (Resolve-Path -LiteralPath $SdkRoot).Path
$hashes = Get-ChildItem (Join-Path $SdkRoot "sdk\agentserver") -Recurse -File |
    Where-Object { $_.Extension -in @(".cs", ".csproj", ".props", ".targets") -and $_.FullName -notmatch '\\(bin|obj|artifacts)\\' } |
    Sort-Object FullName | Get-FileHash -Algorithm SHA256
$env:A2A_SUITE_SOURCE_SHA = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
    [Text.Encoding]::UTF8.GetBytes(($hashes.Hash -join "`n")))).ToLowerInvariant()
if (-not $StateFile) { $StateFile = Join-Path $source ".runs\deployment.json" }
New-Item -ItemType Directory -Path (Split-Path ([IO.Path]::GetFullPath($StateFile)) -Parent) -Force | Out-Null
$root = Join-Path $destination "a2a-dotnet-scenarios"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Push-Location $destination
try {
    if (-not (Test-Path -LiteralPath (Join-Path $root "azure.yaml"))) {
        & azd ai agent init -m (Join-Path $source "azure.yaml") --project-id $ProjectResourceId `
            --deploy-mode code --runtime dotnet_10 --entry-point ScenarioAgents.dll --dep-resolution bundled `
            --environment $EnvironmentName --no-prompt
        if ($LASTEXITCODE -ne 0) { throw "Suite initialization failed." }
    }
    Set-Location -LiteralPath $root
    foreach ($file in (Get-ChildItem -LiteralPath $source -Recurse -File |
        Where-Object { $_.FullName -notmatch '\\(\.azure|\.runs|bin|obj|\.git)\\' })) {
        $relative = [IO.Path]::GetRelativePath($source, $file.FullName)
        $target = Join-Path $root $relative
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }
    $values = & azd env get-values --output json --environment $EnvironmentName
    if ($LASTEXITCODE -ne 0) { throw "Could not read the initialized azd environment." }
    $values = ($values -join "`n") | ConvertFrom-Json
    $endpoint = $values.AZURE_AI_PROJECT_ENDPOINT
    if (-not $endpoint) { $endpoint = $values.AZURE_AIPROJECT_ENDPOINT }
    if (-not $endpoint) { $endpoint = $values.FOUNDRY_PROJECT_ENDPOINT }
    if (-not $endpoint) { throw "azd did not expose a Foundry project endpoint." }
    if ($values.AZURE_AI_PROJECT_ID -ne $ProjectResourceId) { throw "Deployment environment points at a different project." }
    & azd env set A2A_SUITE_SOURCE_SHA $env:A2A_SUITE_SOURCE_SHA --environment $EnvironmentName
    if ($LASTEXITCODE -ne 0) { throw "Could not record the source fingerprint." }
    $agents = @()
    $failures = @()
    if (Test-Path -LiteralPath $StateFile) {
        $previous = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        if ($previous.projectResourceId -ne $ProjectResourceId -or $previous.deploymentRoot -ne $root -or
            $previous.environment -ne $EnvironmentName) { throw "StateFile belongs to another deployment." }
        foreach ($agent in $previous.agents) {
            $fingerprint = if ($agent.sourceSha) { $agent.sourceSha } else { $previous.sourceSha }
            $agents += [ordered]@{ scenario = $agent.scenario; name = $agent.name; version = $agent.version; sourceSha = $fingerprint }
        }
        $failures = @($previous.failedDeployments)
    }
    $names = @("echo", "tasks", "streaming", "multiturn", "longrunning", "custombuild", "handler", "native", "tier1", "tier2", "tier3", "persistence")
    foreach ($number in ($Scenarios | Sort-Object -Unique)) {
        $name = "a2a-dotnet-s{0:D2}-{1}" -f $number, $names[$number - 1]
        $agents = @($agents | Where-Object { $_.scenario -ne $number })
        $failures = @($failures | Where-Object { $_ -ne $name })
        & azd deploy $name --no-prompt --environment $EnvironmentName
        if ($LASTEXITCODE -ne 0) { $failures += $name }
        else {
            $current = & azd env get-values --output json --environment $EnvironmentName
            if ($LASTEXITCODE -ne 0) { throw "Cannot pin deployed version of $name." }
            $current = ($current -join "`n") | ConvertFrom-Json
            $key = "AGENT_" + ($name -replace "-", "_").ToUpperInvariant() + "_VERSION"
            $version = $current.$key
            if (-not $version) { throw "Missing $key; refusing to guess a version." }
            $agents += [ordered]@{ scenario = $number; name = $name; version = [string]$version; sourceSha = $env:A2A_SUITE_SOURCE_SHA }
        }
        [ordered]@{ projectEndpoint = $endpoint; projectResourceId = $ProjectResourceId; deploymentRoot = $root
            environment = $EnvironmentName; sourceSha = $env:A2A_SUITE_SOURCE_SHA; agents = $agents; failedDeployments = $failures
        } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $StateFile
    }
    if ($failures.Count) { throw "Deployments failed: $($failures -join ', '). Successful versions are pinned in $StateFile." }
    Write-Host "Selected agents deployed. Test without deploying: .\scripts\Test-Suite.ps1 -Deployments '$StateFile'"
}
finally { Pop-Location }
