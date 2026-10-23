#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$srcDir = Join-Path $PSScriptRoot ".." "src" "openai-computer-tool"
Push-Location $srcDir
try {
    dotnet run -- --create-agent
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet run -- --create-agent failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
