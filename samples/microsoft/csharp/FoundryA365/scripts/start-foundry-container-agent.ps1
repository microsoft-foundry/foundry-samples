param(
    [string]$AgentName,
    [string]$AgentVersion
)

$ErrorActionPreference = "Stop"


# Helper: call REST API
function Invoke-FoundryApi {
    param(
        [string]$Method,
        [string]$Url,
        [object]$Body = $null
    )

    $aiAzureToken = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv
    $Headers = @{ 
        "Authorization" = "Bearer $aiAzureToken"
        "Content-Type"  = "application/json"
    }
    if ($Body) {
        Invoke-RestMethod -Method $Method -Uri $Url -Headers $Headers -Body ($Body | ConvertTo-Json -Depth 100)
    } else {
        Invoke-RestMethod -Method $Method -Uri $Url -Headers $Headers
    }
}

# 1. Start container
$startUrl = "$($env:AZURE_AI_PROJECT_ENDPOINT)/agents/$AgentName/versions/$AgentVersion/containers/default:start?api-version=2025-11-15-preview"
$body = @{
    minReplicas  = 1
    maxReplicas  = 1
}
$operation = Invoke-FoundryApi -Method POST -Url $startUrl -Body $body
Write-Host "Starting container (operation id: $($operation.id), status: $($operation.status))"

# 2. Poll until operation is complete
while ($operation.status -in @("NotStarted", "InProgress")) {
    Start-Sleep -Seconds 5
    $opUrl = "$($env:AZURE_AI_PROJECT_ENDPOINT)/agents/$AgentName/operations/$($operation.id)?api-version=2025-11-15-preview"
    $operation = Invoke-FoundryApi -Method GET -Url $opUrl
    Write-Host "    Operation status: $($operation.status)"

    # 3. Check operation result
    switch ($operation.status) {
        "Succeeded" {
            $containerUrl = "$($env:AZURE_AI_PROJECT_ENDPOINT)/agents/$AgentName/versions/$AgentVersion/containers/default?api-version=2025-11-15-preview"
            $container = Invoke-FoundryApi -Method GET -Url $containerUrl
            Write-Host "Container status: $($container.status), created at: $($container.createdAt)"
            break
        }
        "Failed" {
            Write-Host "Operation failed. Error message: $($operation.error)"
            break
        }
    }
}

