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
    'AZURE_AI_PROJECT_ENDPOINT', 'AZURE_TENANT_ID',
    'AZURE_SUBSCRIPTION_ID', 'AZURE_RESOURCE_GROUP', 'AZURE_AI_ACCOUNT_NAME',
    'AZURE_AI_PROJECT_NAME', 'MCP_ENDPOINT', 'MCP_RESOURCE_URI',
    'MCP_API_APPLICATION_ID', 'MCP_API_APPLICATION_OBJECT_ID', 'MCP_FUNCTION_APP_NAME')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing azd provision output: $name"
    }
}
$account = az account show -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $account.tenantId -ne $env:AZURE_TENANT_ID -or
    $account.id -ne $env:AZURE_SUBSCRIPTION_ID) {
    throw 'Azure CLI must be signed into the hosted sample tenant and subscription.'
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

$endpoint = $env:AZURE_AI_PROJECT_ENDPOINT.TrimEnd('/')
$agentUri = "$endpoint/agents/hosted-blueprint-greeting?api-version=v1"
$agent = Invoke-AzureRest GET $agentUri 'https://ai.azure.com' -AllowMissing
if ($null -eq $agent) {
    throw 'Deploy the hosted agent before configuring its endpoint and MCP caller allowlist.'
}

$expectedSchemes = @('AgentBlueprint', 'AzureRbac')
function Test-AuthorizationSchemes {
    param([object] $Agent)
    $schemes = @($Agent.agent_endpoint.authorization_schemes)
    $types = @($schemes | ForEach-Object { $_.type } | Sort-Object)
    if (($types -join ',') -ne ($expectedSchemes -join ',')) { return $false }
    foreach ($scheme in $schemes) {
        if ($scheme.isolation_key_source.kind -ne 'Entra' -or
            $null -ne $scheme.PSObject.Properties['audience_types']) {
            return $false
        }
        if ($scheme.type -eq 'AgentBlueprint' -and
            ($null -ne $scheme.token_validation_rules.allowed_clients -or
             $null -ne $scheme.token_validation_rules.allowed_principals)) {
            return $false
        }
    }
    return $true
}
if (-not (Test-AuthorizationSchemes $agent)) {
    Invoke-AzureRest PATCH $agentUri 'https://ai.azure.com' @{
        agent_endpoint = @{ authorization_schemes = @(
            @{ type = 'AzureRbac'; isolation_key_source = @{ kind = 'Entra' } }
            @{ type = 'AgentBlueprint'; isolation_key_source = @{ kind = 'Entra' } }
        ) }
    } -ContentType 'application/merge-patch+json' | Out-Null
    $agent = Invoke-AzureRest GET $agentUri 'https://ai.azure.com'
}
if (-not (Test-AuthorizationSchemes $agent)) {
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
azd -C $root env set GREETING_AGENT_ENDPOINT "$endpoint/agents/hosted-blueprint-greeting/endpoint/protocols/openai?api-version=v1"
if ($LASTEXITCODE -ne 0) { throw 'Unable to record the agent endpoint.' }
Write-Host 'Hosted agent endpoint and MCP caller access are ready. Run Configure-Authorization.ps1 before calling the agent.'
