$ErrorActionPreference = "Stop"

function Get-OptionalAzdEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [string]$DefaultValue = ""
    )

    $output = & azd env get-value $Key --no-prompt 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $DefaultValue
    }
    return ($output | Out-String).Trim()
}

$deployModelValue = Get-OptionalAzdEnvironmentValue `
    -Key "deployModel" `
    -DefaultValue "false"
$deployModel = $deployModelValue -eq "true"

if (-not $deployModel) {
    $endpoint = Get-OptionalAzdEnvironmentValue `
        -Key "existingModelResponsesEndpoint"
    $deployment = Get-OptionalAzdEnvironmentValue `
        -Key "modelDeploymentName"
    if (
        [string]::IsNullOrWhiteSpace($endpoint) -or
        [string]::IsNullOrWhiteSpace($deployment)
    ) {
        throw @"
existingModelResponsesEndpoint and modelDeploymentName are required when deployModel is false.
Set the existing model values before provisioning:
  azd env set deployModel false
  azd env set existingModelResponsesEndpoint "<YOUR_RESPONSES_ENDPOINT>"
  azd env set modelDeploymentName "<YOUR_MODEL_DEPLOYMENT>"
"@
    }
}

Write-Host "Model configuration is valid (deployModel=$deployModel)."
