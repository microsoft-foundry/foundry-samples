$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'Rest.ps1')

foreach ($name in @(
    'AZURE_AI_PROJECT_ENDPOINT', 'AZURE_AI_MODEL_DEPLOYMENT_NAME', 'AZURE_TENANT_ID',
    'AZURE_SUBSCRIPTION_ID', 'AZURE_RESOURCE_GROUP', 'AZURE_AI_ACCOUNT_NAME',
    'AZURE_AI_PROJECT_NAME', 'MCP_ENDPOINT', 'MCP_RESOURCE_URI',
    'MCP_API_APPLICATION_ID', 'MCP_API_APPLICATION_OBJECT_ID', 'MCP_FUNCTION_APP_NAME')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing azd provision output: $name"
    }
}

$graph = 'https://graph.microsoft.com/v1.0'
$appId = $env:MCP_API_APPLICATION_OBJECT_ID
$app = Invoke-AzureRest GET "$graph/applications/$appId`?`$select=id,identifierUris" 'https://graph.microsoft.com'
if ($env:MCP_RESOURCE_URI -notin @($app.identifierUris)) {
    $uris = @(@($app.identifierUris) + $env:MCP_RESOURCE_URI | Select-Object -Unique)
    Invoke-AzureRest PATCH "$graph/applications/$appId" 'https://graph.microsoft.com' @{ identifierUris = $uris } | Out-Null
    $app = Invoke-AzureRest GET "$graph/applications/$appId`?`$select=identifierUris" 'https://graph.microsoft.com'
    if ($env:MCP_RESOURCE_URI -notin @($app.identifierUris)) {
        throw 'The greeting MCP resource URI was not persisted in Microsoft Entra.'
    }
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

$request = Get-Content (Join-Path $root 'agent\agent.json') -Raw | ConvertFrom-Json
$request.definition.model = $env:AZURE_AI_MODEL_DEPLOYMENT_NAME
$request.definition.tools[0].server_url = $env:MCP_ENDPOINT
$definitionJson = $request.definition | ConvertTo-Json -Depth 30 -Compress
$hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($definitionJson))).ToLowerInvariant()
$request.metadata | Add-Member -NotePropertyName definitionHash -NotePropertyValue $hash -Force
$endpoint = $env:AZURE_AI_PROJECT_ENDPOINT.TrimEnd('/')
$agentUri = "$endpoint/agents/$($request.name)?api-version=v1"
$agent = Invoke-AzureRest GET $agentUri 'https://ai.azure.com' -AllowMissing
if ($null -eq $agent) {
    Invoke-AzureRest POST "$endpoint/agents?api-version=v1" 'https://ai.azure.com' $request | Out-Null
}
elseif ($agent.versions.latest.metadata.definitionHash -ne $hash) {
    $version = @{
        definition = $request.definition
        description = $request.description
        metadata = $request.metadata
    }
    Invoke-AzureRest POST "$endpoint/agents/$($request.name)/versions?api-version=v1" 'https://ai.azure.com' $version | Out-Null
}

$agent = Invoke-AzureRest GET $agentUri 'https://ai.azure.com'
$expectedSchemes = @('AgentBlueprint', 'AzureRbac')
$actualSchemes = @($agent.agent_endpoint.authorization_schemes | ForEach-Object { $_.type } | Sort-Object)
if (($actualSchemes -join ',') -ne ($expectedSchemes -join ',')) {
    Invoke-AzureRest PATCH $agentUri 'https://ai.azure.com' @{
        agent_endpoint = @{ authorization_schemes = $request.agent_endpoint.authorization_schemes }
    } -ContentType 'application/merge-patch+json' | Out-Null
    $agent = Invoke-AzureRest GET $agentUri 'https://ai.azure.com'
}
if ((@($agent.agent_endpoint.authorization_schemes | ForEach-Object { $_.type } | Sort-Object) -join ',') -ne ($expectedSchemes -join ',')) {
    throw 'Agent endpoint authorization readback does not match the two requested schemes.'
}

$blueprintId = [string]$agent.blueprint.client_id
$actorId = [string]$agent.instance_identity.client_id
$parsedBlueprint = [guid]::Empty
$parsedActor = [guid]::Empty
if (-not [guid]::TryParse($blueprintId, [ref]$parsedBlueprint) -or
    -not [guid]::TryParse($actorId, [ref]$parsedActor)) {
    throw 'Foundry has not returned both the blueprint and agent identity client IDs.'
}
$authUri = "https://management.azure.com/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.Web/sites/$($env:MCP_FUNCTION_APP_NAME)/config/authsettingsV2?api-version=2024-11-01"
$auth = Invoke-AzureRest GET $authUri 'https://management.azure.com/'
if ($auth.properties.platform.enabled -ne $true -or
    $auth.properties.identityProviders.azureActiveDirectory.registration.clientId -ne $env:MCP_API_APPLICATION_ID -or
    "api://$($env:MCP_API_APPLICATION_ID)" -notin @($auth.properties.identityProviders.azureActiveDirectory.validation.allowedAudiences)) {
    throw 'App Service Authentication on the Function App does not match the sample MCP application.'
}
$policy = $auth.properties.identityProviders.azureActiveDirectory.validation.defaultAuthorizationPolicy
$allowed = @($policy.allowedApplications)
if ($allowed.Count -ne 1 -or $allowed[0] -notin @('00000000-0000-0000-0000-000000000000', $actorId)) {
    throw 'The App Service Authentication caller allowlist on the Function App is unexpected; no authorization was changed.'
}
if ($allowed[0] -ne $actorId) {
    $policy.allowedApplications = @($actorId)
    Invoke-AzureRest PUT $authUri 'https://management.azure.com/' @{ properties = $auth.properties } | Out-Null
}
$auth = Invoke-AzureRest GET $authUri 'https://management.azure.com/'
if ((@($auth.properties.identityProviders.azureActiveDirectory.validation.defaultAuthorizationPolicy.allowedApplications) -join ',') -ne $actorId) {
    throw 'The generated agent identity was not confirmed in the Function App authentication allowlist.'
}

azd -C $root env set GREETING_BLUEPRINT_ID $blueprintId
if ($LASTEXITCODE -ne 0) { throw 'Unable to record the blueprint client ID.' }
azd -C $root env set GREETING_AGENT_ID $actorId
if ($LASTEXITCODE -ne 0) { throw 'Unable to record the agent identity client ID.' }
azd -C $root env set GREETING_AGENT_ENDPOINT "$endpoint/agents/$($request.name)/endpoint/protocols/openai?api-version=v1"
if ($LASTEXITCODE -ne 0) { throw 'Unable to record the agent endpoint.' }
Write-Host 'Agent and MCP identity configuration are ready. Run Configure-Authorization.ps1 before calling the agent.'
