#Requires -Version 7.3
# Create an ApiManagement connection on a Microsoft Foundry project with azd.
# The connection reaches an API in Azure API Management with either the APIM
# subscription key (AUTH_TYPE=api-key, the default) or the project's managed
# identity (AUTH_TYPE=project-managed-identity).
# Agents then use the model as <CONNECTION_NAME>/<MODEL_DEPLOYMENT_NAME>.
$ErrorActionPreference = 'Stop'

foreach ($name in 'FOUNDRY_PROJECT_ENDPOINT', 'CONNECTION_NAME', 'APIM_API_URL', 'MODEL_DEPLOYMENT_NAME') {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Set the $name environment variable." }
}

$model = [ordered]@{ name = $env:MODEL_NAME ? $env:MODEL_NAME : $env:MODEL_DEPLOYMENT_NAME }
if ($env:MODEL_VERSION) { $model.version = $env:MODEL_VERSION }
$model.format = $env:MODEL_FORMAT ? $env:MODEL_FORMAT : 'OpenAI'
$models = ConvertTo-Json -InputObject @([ordered]@{ name = $env:MODEL_DEPLOYMENT_NAME; properties = @{ model = $model } }) -Depth 5 -Compress
$deploymentInPath = $env:DEPLOYMENT_IN_PATH ? $env:DEPLOYMENT_IN_PATH : 'true'

$arguments = @(
    'ai', 'connection', 'create', $env:CONNECTION_NAME,
    '--kind', 'ApiManagement',
    '--target', $env:APIM_API_URL,
    '--metadata', "deploymentInPath=$deploymentInPath",
    '--metadata', "models=$models",
    '--project-endpoint', $env:FOUNDRY_PROJECT_ENDPOINT,
    '--no-prompt'
)

switch ($env:AUTH_TYPE ? $env:AUTH_TYPE : 'api-key') {
    'api-key' {
        if (-not $env:APIM_SUBSCRIPTION_KEY) { throw 'Set APIM_SUBSCRIPTION_KEY to an APIM subscription key for the API.' }
        $arguments += '--auth-type', 'api-key', '--key', $env:APIM_SUBSCRIPTION_KEY
    }
    'project-managed-identity' {
        $audience = $env:TOKEN_AUDIENCE ? $env:TOKEN_AUDIENCE : 'https://cognitiveservices.azure.com'
        $arguments += '--auth-type', 'project-managed-identity', '--audience', $audience
    }
    default { throw 'AUTH_TYPE must be api-key or project-managed-identity.' }
}

if ($env:INFERENCE_API_VERSION) { $arguments += '--metadata', "inferenceAPIVersion=$env:INFERENCE_API_VERSION" }

azd @arguments
exit $LASTEXITCODE
