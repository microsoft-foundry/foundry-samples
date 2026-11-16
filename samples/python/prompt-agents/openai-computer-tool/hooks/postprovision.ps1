#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$srcDir = Join-Path $PSScriptRoot ".." "src" "openai-computer-tool"
Push-Location $srcDir
try {
    python create_agent.py
} finally {
    Pop-Location
}
