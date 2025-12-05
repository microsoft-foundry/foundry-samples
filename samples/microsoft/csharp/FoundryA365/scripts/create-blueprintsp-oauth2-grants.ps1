$ErrorActionPreference = "Stop"

$blueprintSP = az ad sp show --id $env:AGENT_IDENTITY_BLUEPRINT_ID --query id -o tsv

if ([string]::IsNullOrEmpty($blueprintSP)) {
    throw "Failed to get service principal for blueprint ID $($env:AGENT_IDENTITY_BLUEPRINT_ID)"
}

Write-Host "Creating OAuth2 permission grants for blueprint service principal..."


$apxAppId = "5a807f24-c9de-44ee-a3a7-329e88a00ffc"

$apxSP = az ad sp show --id $apxAppId --query id -o tsv
if ([string]::IsNullOrEmpty($apxSP)) {
    throw "Failed to get service principal for APEX app ID $apxAppId"
}

$prodMCPAppId = "ea9ffc3e-8a23-4a7d-836d-234d7c7565c1"
$prodMCP_SP = az ad sp show --id $prodMCPAppId --query id -o tsv

if ([string]::IsNullOrEmpty($prodMCP_SP)) {
    throw "Failed to get service principal for Prod MCP app ID $prodMCPAppId"
}

# 00000003-0000-0000-c000-000000000000 is graph appId
$graphToken = az account get-access-token --resource https://graph.microsoft.com/ --query accessToken -o tsv


$mcpOauthGrant = @"
{
  "clientId": "$blueprintSP",
  "consentType": "AllPrincipals",
  "principalId": null,
  "resourceId": "$prodMCP_SP",
  "scope": "McpServers.M365Admin.All McpServers.DASearch.All McpServers.WebSearch.All McpServers.Files.All AgentTools.MOSEvents.All McpServers.Admin365Graph.All McpServers.ERPAnalytics.All McpServers.DataverseCustom.All McpServers.Dataverse.All McpServers.D365Service.All McpServers.D365Sales.All McpServers.Management.All McpServersMetadata.Read.All McpServers.Developer.All McpServers.CopilotMCP.All McpServers.OneDriveSharepoint.All McpServers.Mail.All McpServers.Teams.All McpServers.Me.All McpServers.Calendar.All McpServers.SharepointLists.All McpServers.Knowledge.All McpServers.Excel.All McpServers.Word.All McpServers.PowerPoint.All"
}
"@
# Catch "Permission entry already exists" error and continue
try {
    $response = Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/oauth2PermissionGrants" `
        -Method Post `
        -Headers @{
            "Content-Type" = "application/json"
            "Accept"       = "application/json"
            "Authorization" = "Bearer $($graphToken)"
        } `
        -Body $mcpOauthGrant

    Write-Host ""
    Write-Host "MCP oauth grant response:"
    $response | ConvertTo-Json -Depth 5 | Write-Host

} catch {
    $err = $_.ErrorDetails.Message | ConvertFrom-Json
    if ($err.error.code -eq "Request_BadRequest" -and
        $err.error.message -like "*Permission entry already exists*") {

        Write-Host "Permission already exists  ignoring."
    }
    else {
        throw
    }
}


try {
    $apxOauthGrant = @"
    {
        "clientId": "$blueprintSP",
        "consentType": "AllPrincipals",
        "principalId": null,
        "resourceId": "$apxSP",
        "scope": "AgentData.ReadWrite"
    }
"@

    $response = Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/oauth2PermissionGrants" `
        -Method Post `
        -Headers @{
            "Content-Type" = "application/json"
            "Accept"       = "application/json"
            "Authorization" = "Bearer $($graphToken)"
        } `
        -Body $apxOauthGrant

    Write-Host ""
    Write-Host "APX oauth grant response:"
    $response | ConvertTo-Json -Depth 5 | Write-Host
}
catch {
    $err = $_.ErrorDetails.Message | ConvertFrom-Json
    if ($err.error.code -eq "Request_BadRequest" -and
        $err.error.message -like "*Permission entry already exists*") {

        Write-Host "Permission already exists  ignoring."
    }
    else {
        throw
    }
}
