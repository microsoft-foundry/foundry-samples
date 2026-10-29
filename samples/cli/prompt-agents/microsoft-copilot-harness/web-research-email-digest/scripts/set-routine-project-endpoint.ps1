Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectEndpoint = azd env get-value FOUNDRY_PROJECT_ENDPOINT
if (-not $projectEndpoint) {
  throw 'FOUNDRY_PROJECT_ENDPOINT is missing after provisioning.'
}

azd env set AZURE_AI_PROJECT_ENDPOINT $projectEndpoint
if ($LASTEXITCODE -ne 0) {
  throw 'Failed to set AZURE_AI_PROJECT_ENDPOINT for the Routines extension.'
}