$ErrorActionPreference = "Stop"

$agentUrl = "$($env:AZURE_AI_PROJECT_ENDPOINT)/agents/$($env:AGENT_NAME)/versions?api-version=2025-11-15-preview"

$agentCreationBody = @{
    definition = @{
        kind = "hosted"
        image = "$($env:AZURE_CONTAINER_REGISTRY_ENDPOINT)/hello-world-a365-agent:a365preview001"
        cpu = "2"
        memory = "4Gi"
        environment_variables = @{}
        container_protocol_versions = @(
            @{
                protocol = "activity_protocol"
                version = "v1"
            }
        )
    }
    metadata = @{
        botid = "$($env:AGENT_IDENTITY_BLUEPRINT_ID)"
    }
    description="Foundry digital worker."
}

$jsonBody = $agentCreationBody | ConvertTo-Json -Depth 5

$aiAzureToken = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv


Write-Host "Creating agent version..."
Write-Host "JSON Body:"
Write-Host $jsonBody

# Send POST request
$response = Invoke-RestMethod -Uri $agentUrl `
    -Method Post `
    -Headers @{
        "Content-Type" = "application/json"
        "Accept"       = "application/json"
        "Authorization" = "Bearer $($aiAzureToken)"
    } `
    -Body $jsonBody

Write-Host ""
Write-Host "Response:"
$response | ConvertTo-Json -Depth 100 | Write-Host

# & "$PSScriptRoot/create-application-deployment.ps1" -AgentName $response.name -AgentVersion $response.version

& "$PSScriptRoot/start-foundry-container-agent.ps1" -AgentName $response.name -AgentVersion $response.version