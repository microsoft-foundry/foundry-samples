#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$srcDir = Join-Path $PSScriptRoot ".." "src" "openai-computer-tool"
Push-Location $srcDir
try {
    python main.py provision
} finally {
    Pop-Location
}
