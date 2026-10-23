#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$srcDir = Join-Path $PSScriptRoot ".." "src" "openai-computer-tool"
Push-Location $srcDir
try {
    dotnet run -- --create-agent
} finally {
    Pop-Location
}
