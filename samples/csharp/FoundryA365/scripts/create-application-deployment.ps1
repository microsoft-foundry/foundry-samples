param(
    [string]$AgentName,
    [string]$AgentVersion
)

$ErrorActionPreference = "Stop"

$applicationDeploymentBody = @{
    properties =@{
        displayName = "Foundry Agent Deployment"
        protocols = @(
            @{
                protocol = "Activity"
                version = "v1"
            }
        )
        agents = @(
            @{
                agentName = $AgentName
                agentVersion = $AgentVersion
                #TODO: AgentId
            }
        )
        deploymentType = "Hosted"
        minReplicas = 1
        maxReplicas = 1
    }
}


$createDeploymentUrl = "https://management.azure.com/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:ACCOUNT_NAME)/projects/$($env:PROJECT_NAME)/applications/$($env:APPLICATION_NAME)/agentDeployments/foundry-agent-deployment?api-version=2025-10-01-preview"
$jsonDeploymentBody = $applicationDeploymentBody | ConvertTo-Json -Depth 100
Write-Host "Creating application deployment..."
Write-Host "JSON Body:"
Write-Host $jsonDeploymentBody

$managementToken = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv
# Send PUT request
$responseDeployment = Invoke-RestMethod -Uri $createDeploymentUrl `
    -Method Put `
    -Headers @{
        "Content-Type" = "application/json"
        "Accept"       = "application/json"
        "Authorization" = "Bearer $($managementToken)"
    } `
    -Body $jsonDeploymentBody

Write-Host ""
Write-Host "Response:"
$responseDeployment | ConvertTo-Json -Depth 100 | Write-Host


# Write-Host "Starting application deployment..."
# $startDeploymentUrl = "https://management.azure.com/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:ACCOUNT_NAME)/projects/$($env:PROJECT_NAME)/applications/$($env:APPLICATION_NAME)/agentDeployments/foundry-agent-deployment/start?api-version=2025-10-01-preview"

# $responseDeployment = Invoke-RestMethod -Uri $startDeploymentUrl `
#     -Method Post `
#     -Headers @{
#         "Content-Type" = "application/json"
#         "Accept"       = "application/json"
#         "Authorization" = "Bearer $($managementToken)"
#     } `

# Write-Host ""
# Write-Host "Response:"
# $responseDeployment | ConvertTo-Json -Depth 100 | Write-Host

while ($true) {
    Start-Sleep -Seconds 10
    Write-Host "Get application deployment status..."
    $getDeploymentUrl = "https://management.azure.com/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:ACCOUNT_NAME)/projects/$($env:PROJECT_NAME)/applications/$($env:APPLICATION_NAME)/agentDeployments/foundry-agent-deployment?api-version=2025-10-01-preview"

    $responseDeployment = Invoke-RestMethod -Uri $getDeploymentUrl `
        -Method Get `
        -Headers @{
            "Content-Type" = "application/json"
            "Accept"       = "application/json"
            "Authorization" = "Bearer $($managementToken)"
        } `

    Write-Host ""
    Write-Host "Response:"
    $responseDeployment | ConvertTo-Json -Depth 100 | Write-Host
    if ($responseDeployment.properties.state -eq "Running") {
        Write-Host "Deployment succeeded."
        break
    } elseif ($responseDeployment.properties.provisioningState -eq "Failed") {
        Write-Host "Deployment failed."
        break
    } else {
        Write-Host "Deployment in progress..."
    }
}