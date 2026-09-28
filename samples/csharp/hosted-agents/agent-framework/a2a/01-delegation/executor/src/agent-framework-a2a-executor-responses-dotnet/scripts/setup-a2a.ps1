<#
.SYNOPSIS
    Enable incoming A2A on the executor agent (data plane). After this runs,
    the agent answers both Responses and A2A at the same endpoint.

.DESCRIPTION
    PATCHes the executor agent to publish an `agent_card` and add `a2a` to
    its `agent_endpoint.protocols`.

    The matching `RemoteA2A` connection and `a2a_preview` toolbox are declared
    in the caller's azure.yaml and created by `azd provision` on the caller.
    They are not created here.

    All parameters are optional. Defaults come from:
      - ../.env (FOUNDRY_PROJECT_ENDPOINT)
      - "agent-framework-a2a-executor-responses-dotnet" (AgentName, the
        executor's default name from azure.yaml)

    See:
      - https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint

.EXAMPLE
    # Run with all defaults (uses ../.env)
    ./setup-a2a.ps1

.EXAMPLE
    ./setup-a2a.ps1 -AgentName "agent-framework-a2a-executor-responses-dotnet"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)] [string] $ProjectEndpoint,
    [Parameter(Mandatory = $false)] [string] $AgentName
)

$ErrorActionPreference = 'Stop'

# Load ../.env
$envFile = Join-Path $PSScriptRoot "..\.env"
$envVars = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            $envVars[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
        }
    }
}

if (-not $ProjectEndpoint) { $ProjectEndpoint = $envVars["FOUNDRY_PROJECT_ENDPOINT"] }

if (-not $ProjectEndpoint) {
    Write-Error "FOUNDRY_PROJECT_ENDPOINT is not set (expected in $envFile)."
    exit 1
}

if (-not $AgentName) { $AgentName = "agent-framework-a2a-executor-responses-dotnet" }

$baseUrl = $ProjectEndpoint.TrimEnd('/')
$targetA2AUrl = "$baseUrl/agents/$AgentName/endpoint/protocols/a2a/"
$displayA2AUrl = $targetA2AUrl.TrimEnd('/')

Write-Host "Project endpoint: $baseUrl"
Write-Host "Agent name:       $AgentName"
Write-Host "Target A2A URL:   $displayA2AUrl"
Write-Host ""
Write-Host "Enabling incoming A2A on agent '$AgentName'..."

$enableBody = @{
    agent_card = @{
        description = "A math expert that performs arithmetic operations and explains the steps."
        version = "1.0"
        skills = @(
            @{
                id = "arithmetic"
                name = "Arithmetic and math expert"
                description = "Performs arithmetic operations (addition, subtraction, multiplication, division, exponentiation) and returns concise numeric answers."
            }
        )
    }
    agent_endpoint = @{
        protocols = @("responses", "a2a")
    }
} | ConvertTo-Json -Depth 6

$bodyFile = New-TemporaryFile
try {
    $enableBody | Out-File $bodyFile -Encoding utf8
    az rest `
        --method PATCH `
        --url ($baseUrl + "/agents/" + $AgentName + "?api-version=v1") `
        --resource https://ai.azure.com `
        --headers "Content-Type=application/json" `
        --body "@$bodyFile" `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to enable incoming A2A on agent '$AgentName'."
    }
}
finally {
    Remove-Item -LiteralPath $bodyFile -Force
}

Write-Host "done."
Write-Host ""
Write-Host "Incoming A2A enabled."
Write-Host "  A2A endpoint:  $displayA2AUrl"
Write-Host "  Agent card:    $displayA2AUrl/agentCard/v0.3"
Write-Host ""
Write-Host "Next: when running 'azd ai agent init' on the caller, paste the A2A endpoint"
Write-Host "above as the 'a2a_executor_endpoint' parameter. 'azd provision' on the caller"
Write-Host "will then create the RemoteA2A connection + a2a_preview toolbox automatically."
