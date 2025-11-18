#!/usr/bin/env pwsh
Write-Host "Starting post-provision script..."

# AZURE_LOCATION is a default azd environment variable
Write-Host "Resources were deployed to: location $env:AZURE_LOCATION blueprintId $env:AZURE_AGENT_IDENTITY_BLUEPRINT_ID subscriptionId $env:AZURE_SUBSCRIPTION_ID applicationName $env:AZURE_APPLICATION_NAME"

Write-Host "===============Publishing digital worker==============="

& "$PSScriptRoot/publish-digital-worker.ps1"

# TODO: temporary fix until service starts doing it.
# oAuth2grants for blueprint SP for inheritable scopes to work.
Write-Host "===============OAuth2 grants for blueprint SP==============="
& "$PSScriptRoot/create-blueprintsp-oauth2-grants.ps1"


Write-Host "===============Building and pushing Docker image==============="
& "$PSScriptRoot/build-docker-image.ps1"

Write-Host "===============Creating Foundry container agent==============="
& "$PSScriptRoot/create-foundry-container-agent.ps1"



Write-Host ""
Write-Host "Post-provision script finished."
