Write-Host "========================================"
Write-Host "  Playwright Workspace Role Assignment"
Write-Host "========================================"

$azdEnv = @{}
azd env get-values 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)="(.*)"$') {
        $azdEnv[$Matches[1]] = $Matches[2]
    }
}

$authType = $azdEnv['PLAYWRIGHT_AUTH_TYPE']
$playwrightResourceId = $azdEnv['PLAYWRIGHT_SERVICE_RESOURCE_ID']

if ([string]::IsNullOrWhiteSpace($playwrightResourceId) -or [string]::IsNullOrWhiteSpace($authType)) {
    Write-Host "Necessary params not configured - skipping role assignment."
    exit 0
}

if ($authType -eq 'ApiKey') {
    Write-Host "Auth type is API Key - no role assignment needed."
    exit 0
}

$principalId = $null
$principalType = "ServicePrincipal"

if ($authType -eq 'ProjectManagedIdentity') {
    Write-Host "Assigning role to Project Managed Identity..."
    $projectId = $azdEnv['AZURE_AI_PROJECT_ID']
    if ([string]::IsNullOrWhiteSpace($projectId)) {
        Write-Host "AZURE_AI_PROJECT_ID not found - skipping role assignment."
        exit 0
    }
    $principalId = az resource show --id $projectId --query "identity.principalId" -o tsv 2>$null
}
elseif ($authType -eq 'AgenticIdentityToken') {
    Write-Host "Assigning role to Agent Identity..."
    $projectEndpoint = if ($azdEnv['AZURE_AI_PROJECT_ENDPOINT']) { $azdEnv['AZURE_AI_PROJECT_ENDPOINT'] }
                       elseif ($azdEnv['FOUNDRY_PROJECT_ENDPOINT']) { $azdEnv['FOUNDRY_PROJECT_ENDPOINT'] }
                       else { $null }
    if ([string]::IsNullOrWhiteSpace($projectEndpoint)) {
        Write-Host "Could not determine project endpoint - skipping role assignment."
        exit 0
    }

    $agentName = ($azdEnv.Keys | Where-Object { $_ -match '^AGENT_.*_NAME$' } | ForEach-Object { $azdEnv[$_] }) | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($agentName)) {
        Write-Host "Could not determine agent name - skipping role assignment."
        exit 0
    }

    $principalId = az rest `
        --method GET `
        --url ($projectEndpoint + "/agents/" + $agentName + "?api-version=v1") `
        --resource https://ai.azure.com `
        --query "instance_identity.principal_id" `
        --output tsv
}

if ([string]::IsNullOrWhiteSpace($principalId)) {
    Write-Host "Could not determine principal ID - skipping role assignment."
    exit 0
}

Write-Host "  Principal ID: $principalId"

$roleDefinitionId = "78cf819f-0969-4ebe-8759-015c6efcd5bf"
Write-Host "Assigning Playwright Workspace Contributor role on: $playwrightResourceId"

$existing = az role assignment list `
    --assignee $principalId `
    --role $roleDefinitionId `
    --scope $playwrightResourceId `
    --query "[0].id" -o tsv 2>$null

if ($existing) {
    Write-Host "Role already assigned."
    exit 0
}

$maxRetries = 3
$retryDelay = 10
$assigned = $false

for ($i = 1; $i -le $maxRetries; $i++) {
    az role assignment create `
        --assignee-object-id $principalId `
        --assignee-principal-type $principalType `
        --role $roleDefinitionId `
        --scope $playwrightResourceId `
        --only-show-errors | Out-Null

    if ($LASTEXITCODE -eq 0) {
        $assigned = $true
        break
    }

    if ($i -lt $maxRetries) {
        Write-Host "  Attempt $i failed, retrying in ${retryDelay}s..."
        Start-Sleep -Seconds $retryDelay
    }
}

if ($assigned) {
    Write-Host "Playwright Workspace Contributor role assigned successfully."
} else {
    Write-Warning "Could not assign role after $maxRetries attempts. Assign 'Playwright Workspace Contributor' manually to principal '$principalId' on the workspace."
}
