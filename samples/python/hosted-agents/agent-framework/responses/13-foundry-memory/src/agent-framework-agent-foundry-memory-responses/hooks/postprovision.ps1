#!/usr/bin/env pwsh
# azd postprovision hook (Windows / pwsh).
#
# Runs after `azd provision` and creates the Foundry Memory Store.
# It stores MEMORY_STORE_NAME so the agent can reach the store.

$ErrorActionPreference = "Stop"

# Check $LASTEXITCODE after each native command and fail loudly.
function Invoke-Checked {
    param([scriptblock] $Script, [string] $What)
    & $Script
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)." }
}

# Run from the sample directory; resolve the script from any azd cwd.
Set-Location (Split-Path -Parent $PSScriptRoot)

# The manifest declares the embedding deployment.
if (-not $env:AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME) {
    $env:AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME = "text-embedding-3-small"
    Invoke-Checked {
        azd env set AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME `
            $env:AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME
    } "env set AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME"
}

# Default and persist the store name for agent deployment.
if (-not $env:MEMORY_STORE_NAME) {
    $env:MEMORY_STORE_NAME = "agent_framework_memory"
    Invoke-Checked { azd env set MEMORY_STORE_NAME $env:MEMORY_STORE_NAME } "env set MEMORY_STORE_NAME"
}

Write-Host "Provisioning the Foundry Memory Store '$($env:MEMORY_STORE_NAME)'..."
# Install the locked runtime dependencies used by the provisioning script.
Invoke-Checked { uv sync --frozen --no-dev --no-install-project } "uv sync"
# Idempotent: an existing store with the same name is left untouched.
Invoke-Checked { uv run --no-sync python provision_memory_store.py } "provision_memory_store.py"

# Ensure agent.yaml receives the name if init resolved it before this
# hook ran.
# This keeps the deployed agent connected to the provisioned store.
$manifest = Join-Path (Get-Location) "agent.yaml"
if (Test-Path $manifest) {
    $content = [System.IO.File]::ReadAllText($manifest)
    $pattern = '(?m)(^[ \t]*-[ \t]*name:[ \t]*MEMORY_STORE_NAME[ \t]*\r?\n[ \t]*value:[ \t]*).*$'
    $updated = [System.Text.RegularExpressions.Regex]::Replace($content, $pattern, ('${1}' + $env:MEMORY_STORE_NAME))
    if ($updated -ne $content) {
        [System.IO.File]::WriteAllText($manifest, $updated)
        Write-Host "Set MEMORY_STORE_NAME in agent.yaml to '$($env:MEMORY_STORE_NAME)' for deploy."
    }
}

Write-Host "Done. MEMORY_STORE_NAME = $($env:MEMORY_STORE_NAME)"
