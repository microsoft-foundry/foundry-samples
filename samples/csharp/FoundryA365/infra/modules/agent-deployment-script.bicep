@description('User-assigned managed identity resource ID that the script will run as')
param uamiResourceId string

@description('Azure AI Project Endpoint URL')
param azureAIProjectEndpoint string

@description('Agent name for the Azure AI Project')
param agentName string

@description('Azure Container Registry Endpoint URL')
param azureContainerRegistryEndpoint string

// PowerShell deployment script
resource psScript 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: 'create-agent-script'
  location: resourceGroup().location
  kind: 'AzurePowerShell'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiResourceId}': {}
    }
  }
  properties: {
    // Check supported versions for your region if this fails
    azPowerShellVersion: '11.5'
    timeout: 'PT15M'
    retentionInterval: 'P1D'

    arguments: '-AzureAIProjectEndpoint "${azureAIProjectEndpoint}" -AgentName "${agentName}" -AzureContainerRegistryEndpoint "${azureContainerRegistryEndpoint}"'

    environmentVariables: [
      {
        name: 'RESOURCE_GROUP_NAME'
        value: resourceGroup().name
      }
    ]

    scriptContent: '''
  param(
    [Parameter(Mandatory = $true)]
    [string] $AzureAIProjectEndpoint,
    [Parameter(Mandatory = $true)]
    [string] $AgentName,
    [Parameter(Mandatory = $true)]
    [string] $AzureContainerRegistryEndpoint        
  )

  $ErrorActionPreference = "Stop"

  $agentUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)/versions?api-version=2025-11-15-preview"

  $agentCreationBody = @{
      definition = @{
          kind = "hosted"
          image = "$($AzureContainerRegistryEndpoint)/hello-world-a365-agent:a365preview001"
          cpu = "2"
          memory = "4Gi"
          environment_variables = @{}
          container_protocol_versions = @(
              @{
                  protocol = "activity_protocol"
                  version  = "v1"
              }
          )
      }
      description = "Foundry digital worker."
  }

  $jsonBody = $agentCreationBody | ConvertTo-Json -Depth 5

  Write-Host "Connecting with managed identity..."
  Connect-AzAccount -Identity

  Write-Host "Getting access token for https://ai.azure.com ..."
  $tokenResponse = Get-AzAccessToken -ResourceUrl "https://ai.azure.com"
  $aiAzureToken  = $tokenResponse.Token | ConvertFrom-SecureString -AsPlainText
  Write-Host "Token length: $($aiAzureToken.Length)"

  $headers = @{
      "Content-Type"  = "application/json"
      "Accept"        = "application/json"
      "Authorization" = "Bearer $aiAzureToken"
  }

  Write-Host "Creating agent version at: $agentUrl"
  Write-Host "JSON Body:"
  Write-Host $jsonBody

  $response = Invoke-RestMethod -Uri $agentUrl `
      -Method Post `
      -Headers $headers `
      -Body $jsonBody `
      -ErrorAction Stop

  Write-Host ""
  Write-Host "Response:"
  $response | ConvertTo-Json -Depth 100 | Write-Host

'''

  }
}
