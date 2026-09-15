$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([scriptblock] $Script, [string] $What)

    & $Script
    if ($LASTEXITCODE -ne 0) {
        throw "$What failed (exit $LASTEXITCODE)."
    }
}

$toolboxName = "foundry-autopilot-tools"
$projectEndpoint = $env:AZURE_AI_PROJECT_ENDPOINT
if (-not $projectEndpoint) {
    throw "AZURE_AI_PROJECT_ENDPOINT is required to create the Foundry Toolbox."
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Invoke-Checked {
        azd ai project set $projectEndpoint
    } "Selecting the Foundry project"

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    azd ai toolbox show $toolboxName *> $null
    $toolboxExists = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $previousErrorActionPreference

    if ($toolboxExists) {
        Write-Host "Toolbox '$toolboxName' already exists; keeping its default version."
    }
    else {
        Invoke-Checked {
            azd ai toolbox create $toolboxName --from-file ./toolbox.yaml --no-prompt
        } "Creating Toolbox '$toolboxName'"
    }

    $consumerEndpoint = (
        "$($projectEndpoint.TrimEnd('/'))/toolboxes/" +
        "$toolboxName/mcp?api-version=v1"
    )
    Invoke-Checked {
        azd env set TOOLBOX_ENDPOINT $consumerEndpoint
    } "Saving TOOLBOX_ENDPOINT"
    $env:TOOLBOX_ENDPOINT = $consumerEndpoint

    Write-Host "Toolbox consumer endpoint: $consumerEndpoint"
}
finally {
    Pop-Location
}
