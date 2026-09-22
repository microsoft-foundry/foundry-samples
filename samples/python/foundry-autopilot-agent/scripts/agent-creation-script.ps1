$ErrorActionPreference = "Stop"

$AzureAIProjectEndpoint = $env:AZURE_AI_PROJECT_ENDPOINT
$AgentName = $env:AGENT_NAME
$AzureContainerRegistryEndpoint = $env:AZURE_CONTAINER_REGISTRY_ENDPOINT

# Runtime settings injected into the hosted agent container.
$authorityEndpoint = "https://login.microsoftonline.com/$($env:TENANT_ID)"
$modelDeployment = $env:MODEL_NAME

if (-not $env:TOOLBOX_ENDPOINT) {
    throw "TOOLBOX_ENDPOINT is required. Run setup-toolbox.ps1 before creating the agent version."
}

$runtimeEnvironmentVariables = @{
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHORITY" = $authorityEndpoint
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID"  = $env:TENANT_ID
    "ModelDeployment"                                      = $modelDeployment
    "TOOLBOX_ENDPOINT"                                     = $env:TOOLBOX_ENDPOINT
}

if ($env:AZURE_DEVOPS_ORGANIZATION) {
    $runtimeEnvironmentVariables["AZURE_DEVOPS_ORGANIZATION"] = $env:AZURE_DEVOPS_ORGANIZATION
}

$agentEndpoint = @{
    protocols = @("activity")
    protocol_configuration = @{
        activity = @{
            enable_m365_public_endpoint = $true
        }
    }
}

$agentUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)/versions?api-version=2025-11-15-preview"

$agentCreationBody = @{
    definition = @{
        kind = "hosted"
        image = "$($AzureContainerRegistryEndpoint)/hello-world-a365-agent:latest"
        cpu = "2"
        memory = "4Gi"
        environment_variables = $runtimeEnvironmentVariables
        container_protocol_versions = @(
            @{
                protocol = "activity_protocol"
                version = "2.0.0"
            }
        )
    }
    metadata = @{
        enableVnextExperience = "true"
    }
    description = "Foundry autopilot."
    agent_endpoint = $agentEndpoint
    digital_worker_type = "m365"
}
    
$jsonBody = $agentCreationBody | ConvertTo-Json -Depth 5

Write-Host "Getting access token for https://ai.azure.com ..."

$aiAzureToken = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv --tenant $env:TENANT_ID

Write-Host "Token length: $($aiAzureToken.Length)"

$headers = @{
    "Content-Type" = "application/json"
    "Accept" = "application/json"
    "Authorization" = "Bearer $aiAzureToken"
    "Foundry-Features" = "DigitalWorker=V1Preview"
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

$agentVersion = $response.version
$agentGuid = $response.agent_guid
$agentDefaultInstanceClientId = $response.instance_identity.client_id
$blueprintClientId = $response.blueprint.client_id
Write-Host "Agent GUID: $agentGuid"
Write-Host "Agent Version: $agentVersion"
Write-Host "Blueprint Client Id: $blueprintClientId"

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

            # Identity client IDs may not be populated until provisioning completes.
            if ($pollResponse.instance_identity.client_id) {
                $agentDefaultInstanceClientId = $pollResponse.instance_identity.client_id
            }
            if ($pollResponse.blueprint.client_id) {
                $blueprintClientId = $pollResponse.blueprint.client_id
            }
        }
        catch {
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

$accountScope = "/subscriptions/$($env:SUBSCRIPTION_ID)/resourceGroups/$($env:RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:ACCOUNT_NAME)"
$projectScope = "$accountScope/projects/$($env:PROJECT_NAME)"
$foundryUserRoleName = "Foundry User"

Write-Host "Granting Foundry User role to client id $agentDefaultInstanceClientId on scope $projectScope"

$roleAssignmentOutput = az role assignment create `
    --assignee $agentDefaultInstanceClientId `
    --role $foundryUserRoleName `
    --scope $projectScope 2>&1 | Out-String

if ($LASTEXITCODE -eq 0) {
    Write-Host "Foundry User role assignment created."
}
elseif ($roleAssignmentOutput -match "RoleAssignmentExists") {
    Write-Host "Foundry User role assignment already exists, skipping."
}
else {
    throw "Failed to create Foundry User role assignment: $roleAssignmentOutput"
}

$patchUrl = "$($AzureAIProjectEndpoint)/agents/$($AgentName)?api-version=2025-11-15-preview"
$agentEndpoint["authorization_schemes"] = @(
    @{ "type" = "BotServiceRbac" }
)
$patchBody = @{
    agent_endpoint = $agentEndpoint
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

return [pscustomobject]@{
    AgentGuid = $agentGuid
    BlueprintClientId = $blueprintClientId
}
