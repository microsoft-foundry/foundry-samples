<#
.SYNOPSIS
  Recreates the sample's project capability host with its existing BYO
  connections so the Data Proxy receives the account's current trusted CA bundle.

.DESCRIPTION
  Deleting a capability host can hide data associated with its active stores.
  This helper is intended only for the disposable test environment created by
  this sample and requires -Force.
#>
param(
  [Parameter(Mandatory = $true)][string]$Subscription,
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$AccountName,
  [Parameter(Mandatory = $true)][string]$ProjectName,
  [string]$HostName = 'agents',
  [string]$ApiVersion = '2026-05-15-preview',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

if (-not $Force) {
  throw "Recreating a capability host can hide existing data. Rerun with -Force only for this sample's disposable environment."
}

az account set --subscription $Subscription
if ($LASTEXITCODE -ne 0) { throw "Could not select subscription '$Subscription'." }

$baseUrl = "https://management.azure.com/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName/projects/$ProjectName/capabilityHosts"
$hostUrl = "${baseUrl}/${HostName}?api-version=$ApiVersion"
$listUrl = "${baseUrl}?api-version=$ApiVersion"
$connectionsUrl = "https://management.azure.com/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName/projects/$ProjectName/connections?api-version=2025-04-01-preview"

$hostNames = @(az rest --method get --url $listUrl --query "value[].name" -o tsv)
if ($LASTEXITCODE -ne 0) { throw "Could not list capability hosts." }

$hostExists = $hostNames -contains $HostName
if ($hostExists) {
  $existingJson = az rest --method get --url $hostUrl -o json
  if ($LASTEXITCODE -ne 0) { throw "Could not read capability host '$HostName'." }
  $existing = $existingJson | ConvertFrom-Json
  $properties = @{
    aiServicesConnections = @($existing.properties.aiServicesConnections)
    storageConnections = @($existing.properties.storageConnections)
    threadStorageConnections = @($existing.properties.threadStorageConnections)
    vectorStoreConnections = @($existing.properties.vectorStoreConnections)
  }
}
else {
  Write-Host "Capability host '$HostName' is already absent; discovering the sample's project connections."
  $connectionsJson = az rest --method get --url $connectionsUrl -o json
  if ($LASTEXITCODE -ne 0) { throw "Could not list project connections." }
  $connections = ($connectionsJson | ConvertFrom-Json).value
  $properties = @{
    aiServicesConnections = @($connections | Where-Object { $_.properties.category -in @('AzureOpenAI', 'AIServices') } | ForEach-Object { $_.name })
    storageConnections = @($connections | Where-Object { $_.properties.category -eq 'AzureStorageAccount' } | ForEach-Object { $_.name })
    threadStorageConnections = @($connections | Where-Object { $_.properties.category -eq 'CosmosDb' } | ForEach-Object { $_.name })
    vectorStoreConnections = @($connections | Where-Object { $_.properties.category -eq 'CognitiveSearch' } | ForEach-Object { $_.name })
  }
  if ($properties.storageConnections.Count -ne 1 -or
      $properties.threadStorageConnections.Count -ne 1 -or
      $properties.vectorStoreConnections.Count -ne 1) {
    throw "Expected exactly one Azure Storage, Cosmos DB, and Cognitive Search project connection."
  }
}

$body = @{ properties = $properties } | ConvertTo-Json -Depth 5
$bodyPath = Join-Path ([IO.Path]::GetTempPath()) "recreate-capability-host-$([Guid]::NewGuid().ToString('N')).json"
Set-Content -LiteralPath $bodyPath -Value $body -Encoding utf8

try {
  if ($hostExists) {
    Write-Host "Deleting capability host '$HostName'..."
    az rest --method delete --url $hostUrl | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Capability-host deletion request failed." }

    $deleted = $false
    for ($attempt = 1; $attempt -le 80; $attempt++) {
      $names = @(az rest --method get --url $listUrl --query "value[].name" -o tsv)
      if ($LASTEXITCODE -ne 0) { throw "Could not poll capability-host deletion." }
      if ($names -notcontains $HostName) {
        $deleted = $true
        break
      }
      Start-Sleep -Seconds 15
    }
    if (-not $deleted) { throw "Capability host '$HostName' was not deleted within 20 minutes." }
  }

  Write-Host "Recreating capability host '$HostName' with its existing BYO connections..."
  az rest --method put --url $hostUrl --headers "Content-Type=application/json" --body "@$bodyPath" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Capability-host recreation request failed." }

  for ($attempt = 1; $attempt -le 80; $attempt++) {
    $state = az rest --method get --url $hostUrl --query "properties.provisioningState" -o tsv
    if ($LASTEXITCODE -ne 0) { throw "Could not poll capability-host recreation." }
    Write-Host "Capability-host state: $state"
    if ($state -eq 'Succeeded') {
      Write-Host "Capability host recreated successfully."
      exit 0
    }
    if ($state -eq 'Failed') {
      az rest --method get --url $hostUrl -o json
      throw "Capability-host recreation failed."
    }
    Start-Sleep -Seconds 15
  }
}
finally {
  Remove-Item -LiteralPath $bodyPath -Force -ErrorAction SilentlyContinue
}

throw "Capability host '$HostName' did not reach Succeeded within 20 minutes."
