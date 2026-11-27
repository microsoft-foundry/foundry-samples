$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'Rest.ps1')

$lines = azd -C $root env get-values
if ($LASTEXITCODE -ne 0) { throw 'Select the hosted sample azd environment first.' }
foreach ($line in $lines) {
    if ($line -match '^([A-Z][A-Z0-9_]*)="(.*)"$') {
        Set-Item "Env:$($Matches[1])" $Matches[2]
    }
}
foreach ($name in @(
    'AZURE_AI_PROJECT_ENDPOINT', 'AZURE_SUBSCRIPTION_ID', 'AZURE_TENANT_ID', 'AZURE_RESOURCE_GROUP',
    'AZURE_AI_ACCOUNT_NAME', 'AZURE_AI_PROJECT_NAME', 'MCP_ENDPOINT', 'MCP_SCOPE_URI')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing azd provision output: $name"
    }
}
$account = az account show -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $account.tenantId -ne $env:AZURE_TENANT_ID -or
    $account.id -ne $env:AZURE_SUBSCRIPTION_ID) {
    throw 'Azure CLI must be signed into the hosted sample tenant and subscription.'
}

$principal = az ad signed-in-user show --query id -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($principal)) {
    throw 'Sign in with an Azure CLI user authorized to configure Foundry access.'
}
$projectScope = "/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:AZURE_AI_ACCOUNT_NAME)/projects/$($env:AZURE_AI_PROJECT_NAME)"
$assignments = az role assignment list --assignee $principal --scope $projectScope --query "[?roleDefinitionName=='Foundry User']" -o json
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Foundry project assignments.' }
if (@($assignments | ConvertFrom-Json).Count -eq 0) {
    az role assignment create --assignee-object-id $principal --assignee-principal-type User --role 'Foundry User' --scope $projectScope -o none
    if ($LASTEXITCODE -ne 0) { throw 'Assign Foundry User to the provisioning identity before continuing.' }
}

$uri = "https://management.azure.com/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.CognitiveServices/accounts/$($env:AZURE_AI_ACCOUNT_NAME)/projects/$($env:AZURE_AI_PROJECT_NAME)/connections/greeting-agent-on-behalf-of-user?api-version=2025-10-01-preview"
$connection = Invoke-AzureRest GET $uri 'https://management.azure.com/'
if ($connection.properties.category -ne 'RemoteTool' -or
    $connection.properties.authType -ne 'AgentOnBehalfOfUser' -or
    $connection.properties.target -ne $env:MCP_ENDPOINT -or
    @($connection.properties.scopes).Count -ne 1 -or
    $connection.properties.scopes[0] -ne $env:MCP_SCOPE_URI -or
    $null -ne $connection.properties.audience -or
    $null -ne $connection.properties.metadata.audience) {
    throw 'The greeting connection does not match the scopes-only AgentOnBehalfOfUser contract.'
}

$name = 'hosted-greeting-tools'
$existing = azd -C $root ai toolbox show $name --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    if ("$existing" -notmatch '(?i)404|not found') {
        throw "Unable to inspect the hosted greeting toolbox: $existing"
    }
    azd -C $root ai toolbox create $name --from-file (Join-Path $root 'toolbox.yaml') --no-prompt --output json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the hosted greeting toolbox.' }
}
$toolbox = azd -C $root ai toolbox show $name --output json
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace("$toolbox") -or
    "$toolbox" -notmatch [regex]::Escape('greeting-agent-on-behalf-of-user')) {
    throw 'The hosted greeting toolbox does not contain the expected MCP connection.'
}
azd -C $root env set TOOLBOX_NAME $name
if ($LASTEXITCODE -ne 0) { throw 'Unable to record the toolbox name.' }
Write-Host 'The hosted greeting toolbox is available.'
