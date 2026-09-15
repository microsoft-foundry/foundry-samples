#!/usr/bin/env pwsh

if ($env:SKIP_POSTPROVISION -eq "true") {
    Write-Host "Skipping post-provision data-plane operations because SKIP_POSTPROVISION=true."
    return
}

Write-Host "Starting post-provision script..."

Write-Host "Resources were deployed to: location $env:LOCATION subscriptionId $env:SUBSCRIPTION_ID agentName $env:AGENT_NAME"

Write-Host "===============Creating Foundry Toolbox==============="
& "$PSScriptRoot/setup-toolbox.ps1"

Write-Host "===============Stopping Active Agent Sessions==============="
& "$PSScriptRoot/stop-agent-sessions.ps1"

# Write-Host "===============Building and pushing Docker image==============="
& "$PSScriptRoot/build-docker-image-acr.ps1"

Write-Host "===============Creating Agent Version==============="
$agentInfo = & "$PSScriptRoot/agent-creation-script.ps1"
$agentGuid = $agentInfo.AgentGuid
$blueprintClientId = $agentInfo.BlueprintClientId
Write-Host "Agent GUID: $agentGuid, Blueprint Client Id: $blueprintClientId"

Write-Host "===============Publishing digital worker==============="

& "$PSScriptRoot/publish-digital-worker.ps1" -BlueprintClientId $blueprintClientId

Write-Host ""
Write-Host "Post-provision script finished."
