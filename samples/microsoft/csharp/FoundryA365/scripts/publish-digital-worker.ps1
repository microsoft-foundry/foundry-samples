#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

Write-Host "Starting post-provision script..."

# AZURE_LOCATION is a default azd environment variable
Write-Host "Resources were deployed to: location $env:LOCATION blueprintId $env:AGENT_IDENTITY_BLUEPRINT_ID subscriptionId $env:SUBSCRIPTION_ID applicationName $env:APPLICATION_NAME"

# Construct JSON body based on Microsoft365PublishRequest
$body = @{
    botId               = $env:AGENT_IDENTITY_BLUEPRINT_ID
    publishAsDigitalWorker = $true
    appPublishScope     = "Tenant"
    subscriptionId      = $env:SUBSCRIPTION_ID
    agentName           = $env:APPLICATION_NAME
    appVersion          = "1.0.0"
    shortDescription    = "Foundry A365 Agent deployed via Azure Developer CLI"
    fullDescription     = "A Foundry A365 agent example that demonstrates integration with Microsoft 365 and Azure Cognitive Services."
    developerName       = "Azure Developer"
    developerWebsiteUrl = "https://azure.microsoft.com"
    privacyUrl          = "https://privacy.microsoft.com"
    termsOfUseUrl       = "https://www.microsoft.com/legal/terms-of-use"
    useAgenticUserTemplate = $true
    agenticUserTemplate = @{
            Id                         = "digitalWorkerTemplate"
            File                       = "agenticUserTemplateManifest.json"
            SchemaVersion              = "0.1.0-preview"
            AgentIdentityBlueprintId   = $env:AGENT_IDENTITY_BLUEPRINT_ID
            CommunicationProtocol      = "activityProtocol"
    }
}

$jsonBody = $body | ConvertTo-Json -Depth 10

$aiAzureToken = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv


Write-Host "Sending Microsoft 365 publish request to example.com..."
Write-Host "JSON Body:"
Write-Host $jsonBody

$workspaceName = "$($env:ACCOUNT_NAME)@$($env:PROJECT_NAME)@AML"
# Send POST request

try{
    $response = Invoke-RestMethod -Uri "https://$($env:LOCATION).api.azureml.ms/agent-asset/v2.0/subscriptions/$($env:SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.MachineLearningServices/workspaces/$($workspaceName)/microsoft365/publish" `
    -Method Post `
    -Headers @{
        "Content-Type" = "application/json"
        "Accept"       = "application/json"
        "Authorization" = "Bearer $($aiAzureToken)"
    } `
    -Body $jsonBody

    Write-Host ""
    Write-Host "Response:"
    $response | ConvertTo-Json -Depth 5 | Write-Host
}
catch {
        $err = $_.ErrorDetails.Message | ConvertFrom-Json
    if ($err.error.code -eq "UserError" -and
        $err.error.message -like "*version already exists*") {

        Write-Host "A digital worker is already published with this version. Ignoring."
    }
    else {
        throw
    }
}

Write-Host ""
Write-Host "Publish digital worker script finished."
