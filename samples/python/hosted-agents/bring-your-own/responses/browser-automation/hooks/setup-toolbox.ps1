# ── Setup Browser Automation Toolbox ──────────────────────────────────────────
# This script creates a new version of the browser-automation-tools toolbox.
# Called by postprovision.ps1 after connection setup.
# Always creates a new version to pick up any connection changes, then publishes it.

Write-Host ""
Write-Host "Creating browser-automation-tools toolbox..."

$azdEnv = @{}
azd env get-values 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)="(.*)"$') {
        $azdEnv[$Matches[1]] = $Matches[2]
    }
}

$projectEndpoint = if ($azdEnv['AZURE_AI_PROJECT_ENDPOINT']) { $azdEnv['AZURE_AI_PROJECT_ENDPOINT'] }
                   elseif ($azdEnv['FOUNDRY_PROJECT_ENDPOINT']) { $azdEnv['FOUNDRY_PROJECT_ENDPOINT'] }
                   else { $null }

if ([string]::IsNullOrWhiteSpace($projectEndpoint)) {
    Write-Error "Could not determine project endpoint. Set AZURE_AI_PROJECT_ENDPOINT or FOUNDRY_PROJECT_ENDPOINT."
    exit 1
}

$projectId = $azdEnv['AZURE_AI_PROJECT_ID']
if ([string]::IsNullOrWhiteSpace($projectId)) {
    Write-Error "Could not determine project ID. Set AZURE_AI_PROJECT_ID."
    exit 1
}
$connectionId = "$projectId/connections/browserautomation"

$toolboxName = "browser-automation-tools"
$token = az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv

$toolboxBody = @{
    tools = @(
        @{
            type = "browser_automation"
            browser_automation = @{
                connection = @{
                    project_connection_id = $connectionId
                }
            }
        }
    )
} | ConvertTo-Json -Depth 5 -Compress

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

# POST creates a new version (works for both new and existing toolboxes)
try {
    $response = Invoke-RestMethod -Method POST `
        -Uri "${projectEndpoint}/toolboxes/${toolboxName}/versions?api-version=v1" `
        -Headers $headers -Body $toolboxBody
    $versionId = $response.version
} catch {
    Write-Error "Failed to create toolbox version: $_"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($versionId)) {
    Write-Error "Toolbox creation did not return a version ID."
    exit 1
}

Write-Host "  Created version: $versionId"

# Publish the new version as default
azd ai toolbox publish $toolboxName $versionId
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to publish toolbox version '$versionId'. The agent may not work without a default version."
    exit 1
}

azd env set TOOLBOX_NAME $toolboxName

Write-Host "✅ Toolbox '$toolboxName' v${versionId} created and published."