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
          image = "$($AzureContainerRegistryEndpoint)/workstream-manager-agent:a365preview001"
          cpu = "2"
          memory = "4Gi"
          environment_variables = @{}
          container_protocol_versions = @(
              @{
                  protocol = "activity_protocol"
                  version  = "2.0.0"
              }
          )
      }
      metadata = @{
        enableVnextExperience = "true"
      }
      description = "Foundry digital worker."
      agent_endpoint = @{
        protocols = @("activity")
      }
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
      "Foundry-Features" = "HostedAgents=V1Preview,AgentEndpoints=V1Preview"
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

  # Output the agent version
  $agentVersion = $response.version
  Write-Host "Agent Version: $agentVersion"

  # Poll for agent version provisioning status
  $maxRetries = 30
  $delaySeconds = 10
  $provisioningStatus = $response.status
  if (-not $provisioningStatus) { $provisioningStatus = "Unknown" }

  Write-Host "Initial provisioning status: $provisioningStatus"

  $pollUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)/versions/$($agentVersion)?api-version=2025-11-15-preview"

  if ($provisioningStatus -ne "active" -and $provisioningStatus -ne "failed") {
      for ($i = 1; $i -lt $maxRetries; $i++) {
          Write-Host "Waiting ${delaySeconds}s before poll $($i + 1)/${maxRetries}..."
          Start-Sleep -Seconds $delaySeconds

          try {
              $pollResponse = Invoke-RestMethod -Uri $pollUrl `
                  -Method Get `
                  -Headers $headers `
                  -ErrorAction Stop

              $provisioningStatus = $pollResponse.status
              if (-not $provisioningStatus) { $provisioningStatus = "Unknown" }
          } catch {
              Write-Host "Poll failed: $($_.Exception.Message)"
          }

          Write-Host "Provisioning status: $provisioningStatus"

          if ($provisioningStatus -eq "active" -or $provisioningStatus -eq "failed") {
              break
          }
      }
  }

  Write-Host "Agent version provisioned: $provisioningStatus"

  if ($provisioningStatus -ne "active") {
      throw "Agent version provisioning status is '$provisioningStatus', expected 'active'."
  }

  # Patch agent endpoint with activity protocol
  $patchUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)?api-version=2025-11-15-preview"
  $patchBody = @{
      agent_endpoint = @{
          protocols = @("activity")
      }
  } | ConvertTo-Json -Depth 5

  Write-Host "Patching agent endpoint at: $patchUrl"
  Write-Host "Patch Body:"
  Write-Host $patchBody

  $patchResponse = Invoke-RestMethod -Uri $patchUrl `
      -Method Patch `
      -Headers $headers `
      -Body $patchBody `
      -ErrorAction Stop
  
  $blueprintClientId = $patchResponse.blueprint.client_id

  Write-Host ""
  Write-Host "Patch Response:"
  $patchResponse | ConvertTo-Json -Depth 100 | Write-Host

  $DeploymentScriptOutputs = @{
      agentVersion = $agentVersion
      blueprintClientId = $blueprintClientId

  }

'''

  }
}

output agentVersion string = psScript.properties.outputs.agentVersion
output blueprintClientId string = psScript.properties.outputs.blueprintClientId

