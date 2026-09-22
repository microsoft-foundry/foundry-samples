$ErrorActionPreference = "Stop"

$AzureAIProjectEndpoint = $env:AZURE_AI_PROJECT_ENDPOINT
$AgentName = $env:AGENT_NAME
$AzureContainerRegistryEndpoint = $env:AZURE_CONTAINER_REGISTRY_ENDPOINT

# Runtime settings injected into the hosted agent container (moved out of the Dockerfile).
$authorityEndpoint = "https://login.microsoftonline.com/$($env:TENANT_ID)"
$azureOpenAIEndpoint = "https://$($env:ACCOUNT_NAME).openai.azure.com/"
$modelDeployment = $env:MODEL_NAME


$agentUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)/versions?api-version=2025-11-15-preview"

$agentCreationBody = @{
    definition = @{
        kind = "hosted"
        image = "$($AzureContainerRegistryEndpoint)/hello-world-a365-agent:latest"
        cpu = "2"
        memory = "4Gi"
        environment_variables = @{
            "Connections__ServiceConnection__Settings__AuthorityEndpoint" = $authorityEndpoint
            "AzureOpenAIEndpoint"                                         = $azureOpenAIEndpoint
            "ModelDeployment"                                             = $modelDeployment
        }
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
    description = "Foundry autopilot."
    agent_endpoint = @{
        protocols = @("activity")
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
$blueprintClientId = $response.blueprint.client_id
Write-Host "Agent GUID: $agentGuid"
Write-Host "Agent Version: $agentVersion"
Write-Host "Blueprint Client Id: $blueprintClientId"

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

            # Refresh identity client ids once they are populated by provisioning.
            if ($pollResponse.instance_identity.client_id) { $agentDefaultInstanceClientId = $pollResponse.instance_identity.client_id }
            if ($pollResponse.blueprint.client_id) { $blueprintClientId = $pollResponse.blueprint.client_id }
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
$accountScope = "/subscriptions/$($env:SUBSCRIPTION_ID)/resourceGroups/$($env:RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:ACCOUNT_NAME)"
$cognitiveServicesUserRoleId = "a97b65f3-24c7-4388-baec-2e87135dc908"

Write-Host "Granting Cognitive Services User role to client id $agentDefaultInstanceClientId on scope $accountScope"

$roleAssignmentOutput = az role assignment create `
    --assignee $agentDefaultInstanceClientId `
    --role $cognitiveServicesUserRoleId `
    --scope $accountScope 2>&1 | Out-String

if ($LASTEXITCODE -eq 0) {
    Write-Host "Cognitive Services User role assignment created."
} elseif ($roleAssignmentOutput -match "RoleAssignmentExists") {
    Write-Host "Cognitive Services User role assignment already exists, skipping."
} else {
    throw "Failed to create Cognitive Services User role assignment: $roleAssignmentOutput"
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

# Return agent GUID and blueprint client id for downstream scripts
return [pscustomobject]@{
    AgentGuid         = $agentGuid
    BlueprintClientId = $blueprintClientId
}
