#Requires -Version 7.3
# Create a ModelGateway connection on a Microsoft Foundry project with azd.
# The connection reaches a model gateway or provider with an API key.
# Agents then use the model as <CONNECTION_NAME>/<MODEL_DEPLOYMENT_NAME>.
$ErrorActionPreference = 'Stop'

foreach ($name in 'FOUNDRY_PROJECT_ENDPOINT', 'CONNECTION_NAME', 'GATEWAY_URL', 'GATEWAY_API_KEY', 'MODEL_DEPLOYMENT_NAME') {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Set the $name environment variable." }
}

$model = [ordered]@{ name = $env:MODEL_NAME ? $env:MODEL_NAME : $env:MODEL_DEPLOYMENT_NAME }
if ($env:MODEL_VERSION) { $model.version = $env:MODEL_VERSION }
$model.format = $env:MODEL_FORMAT ? $env:MODEL_FORMAT : 'OpenAI'
$models = ConvertTo-Json -InputObject @([ordered]@{ name = $env:MODEL_DEPLOYMENT_NAME; properties = @{ model = $model } }) -Depth 5 -Compress
$deploymentInPath = $env:DEPLOYMENT_IN_PATH ? $env:DEPLOYMENT_IN_PATH : 'false'

azd ai connection create $env:CONNECTION_NAME `
    --kind ModelGateway `
    --target $env:GATEWAY_URL `
    --auth-type api-key `
    --key $env:GATEWAY_API_KEY `
    --metadata "deploymentInPath=$deploymentInPath" `
    --metadata "inferenceAPIVersion=$env:INFERENCE_API_VERSION" `
    --metadata "models=$models" `
    --project-endpoint $env:FOUNDRY_PROJECT_ENDPOINT `
    --no-prompt
exit $LASTEXITCODE
