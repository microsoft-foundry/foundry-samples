  $ErrorActionPreference = "Stop"

  function Grant-AzureRole {
      param(
          [Parameter(Mandatory = $true)][string]$Assignee,
          [Parameter(Mandatory = $true)][string]$Role,
          [Parameter(Mandatory = $true)][string]$Scope,
          [Parameter(Mandatory = $true)][string]$Description
      )

      Write-Host "Granting $Description to $Assignee on scope $Scope"
      $roleAssignmentOutput = az role assignment create `
          --assignee $Assignee `
          --role $Role `
          --scope $Scope 2>&1 | Out-String

      if ($LASTEXITCODE -eq 0) {
          Write-Host "$Description role assignment created."
      } elseif ($roleAssignmentOutput -match "RoleAssignmentExists") {
          Write-Host "$Description role assignment already exists, skipping."
      } else {
          throw "Failed to create $Description role assignment: $roleAssignmentOutput"
      }
  }

  $AzureAIProjectEndpoint = $env:AZURE_AI_PROJECT_ENDPOINT
  $AgentName = $env:AGENT_NAME
  $AzureContainerRegistryEndpoint = $env:AZURE_CONTAINER_REGISTRY_ENDPOINT
  $MAIBName = $env:MAIB_NAME

  # Message content stays off unless the azd environment opts in.
  $azdEnvironmentArgs = if ($env:AZURE_ENV_NAME) { @("-e", $env:AZURE_ENV_NAME) } else { @() }
  $captureMessageContent = & azd env get-value OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT @azdEnvironmentArgs 2>$null
  $captureMessageContent = if ($LASTEXITCODE -eq 0 -and "$captureMessageContent".Trim() -eq "true") { "true" } else { "false" }
  $environmentVariables = @{
      "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT" = $captureMessageContent
  }
  if (-not [string]::IsNullOrWhiteSpace($env:DIRECT_MESSAGE_ALLOWLIST_TABLE_SERVICE_URI)) {
      $environmentVariables.DirectMessageAllowListTableServiceUri = $env:DIRECT_MESSAGE_ALLOWLIST_TABLE_SERVICE_URI
  }
  if (-not [string]::IsNullOrWhiteSpace($env:DIRECT_MESSAGE_ALLOWLIST_TABLE_NAME)) {
      $environmentVariables.DirectMessageAllowListTableName = $env:DIRECT_MESSAGE_ALLOWLIST_TABLE_NAME
  }

  $agentUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)/versions?api-version=2025-11-15-preview"

  $agentCreationBody = @{
      definition = @{
          kind = "hosted"
          image = "$($AzureContainerRegistryEndpoint)/workstream-manager-agent1:latest"
          cpu = "2"
          memory = "4Gi"
          environment_variables = $environmentVariables
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
      description = "Foundry digital worker 26."
      agent_endpoint = @{
        protocols = @("activity")
      }
      blueprint_reference = @{
        type = "ManagedAgentIdentityBlueprint"
        blueprint_id = $MAIBName
      }
  }

  $jsonBody = $agentCreationBody | ConvertTo-Json -Depth 5

  Write-Host "Getting access token for https://ai.azure.com ..."

  $aiAzureToken = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv


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
  $agentGuid = $response.agent_guid
  $agentDefaultInstanceClientId = $response.instance_identity.client_id
  Write-Host "Agent GUID: $agentGuid"
  Write-Host "Agent Version: $agentVersion"
  Write-Host "Agent default instance client id: $agentDefaultInstanceClientId"

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

  # Grant Cognitive Services User role on the foundry account to the agent's default instance identity.
  # The Foundry runtime creates this identity when the agent version is provisioned and injects its client id
  # into the running container as FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID. Our Responses API code uses that
  # identity (per Adi's sync from foundry-ai-teammate), so it must have the role on the Cognitive Services account.
  $subscriptionId = if ($env:SUBSCRIPTION_ID) { $env:SUBSCRIPTION_ID } else { $env:AZURE_SUBSCRIPTION_ID }
  $resourceGroup = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { $env:AZURE_RESOURCE_GROUP }
  $accountName = $env:ACCOUNT_NAME
  $accountScope = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.CognitiveServices/accounts/$accountName"
  $cognitiveServicesUserRoleId = "a97b65f3-24c7-4388-baec-2e87135dc908"

  Grant-AzureRole `
      -Assignee $agentDefaultInstanceClientId `
      -Role $cognitiveServicesUserRoleId `
      -Scope $accountScope `
      -Description "Cognitive Services User"

  if (-not [string]::IsNullOrWhiteSpace($env:DIRECT_MESSAGE_ALLOWLIST_STORAGE_ACCOUNT_RESOURCE_ID)) {
      Grant-AzureRole `
          -Assignee $agentDefaultInstanceClientId `
          -Role "Storage Table Data Contributor" `
          -Scope $env:DIRECT_MESSAGE_ALLOWLIST_STORAGE_ACCOUNT_RESOURCE_ID `
          -Description "Agent Storage Table Data Contributor (DM Allowlist)"
  }

  if (-not [string]::IsNullOrWhiteSpace($env:WORK_ITEMS_STORAGE_ACCOUNT_RESOURCE_ID)) {
      Grant-AzureRole `
          -Assignee $agentDefaultInstanceClientId `
          -Role "Storage Table Data Contributor" `
          -Scope $env:WORK_ITEMS_STORAGE_ACCOUNT_RESOURCE_ID `
          -Description "Agent Storage Table Data Contributor (Work Items)"
  }

  # Patch agent endpoint with activity protocol
  $patchUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)?api-version=2025-11-15-preview"
  $patchBody = @{
      agent_endpoint = @{
          protocols = @("activity")
          authorization_schemes = @(
            @{ "type" = "BotServiceRbac" }
        )
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
  
  Write-Host ""
  Write-Host "Patch Response:"
  $patchResponse | ConvertTo-Json -Depth 100 | Write-Host

  # Return agent GUID for downstream scripts
  return $agentGuid

