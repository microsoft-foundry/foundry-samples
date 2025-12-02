# PowerShell script to help you get the names of your existing resources
# Run this after your initial deployment to get the resource names for the add-project parameters

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$false)]
    [string]$SubscriptionId
)

if ($SubscriptionId) {
    az account set --subscription $SubscriptionId
}

Write-Host "Getting existing AI Foundry resources from Resource Group: $ResourceGroupName" -ForegroundColor Green

# Get AI Services account
Write-Host "`n=== AI Services Account ===" -ForegroundColor Yellow
$aiAccount = az cognitiveservices account list --resource-group $ResourceGroupName --query "[?kind=='AIServices'].[name]" -o tsv
if ($aiAccount) {
    Write-Host "AI Services Account Name: $aiAccount"
} else {
    Write-Host "No AI Services account found" -ForegroundColor Red
}

# Get Storage Account
Write-Host "`n=== Storage Account ===" -ForegroundColor Yellow
$storageAccount = az storage account list --resource-group $ResourceGroupName --query "[].name" -o tsv
if ($storageAccount) {
    Write-Host "Storage Account Name: $storageAccount"
} else {
    Write-Host "No Storage account found" -ForegroundColor Red
}

# Get AI Search Service
Write-Host "`n=== AI Search Service ===" -ForegroundColor Yellow
$searchService = az search service list --resource-group $ResourceGroupName --query "[].name" -o tsv
if ($searchService) {
    Write-Host "AI Search Service Name: $searchService"
} else {
    Write-Host "No AI Search service found" -ForegroundColor Red
}

# Get Cosmos DB Account
Write-Host "`n=== Cosmos DB Account ===" -ForegroundColor Yellow
$cosmosAccount = az cosmosdb list --resource-group $ResourceGroupName --query "[].name" -o tsv
if ($cosmosAccount) {
    Write-Host "Cosmos DB Account Name: $cosmosAccount"
} else {
    Write-Host "No Cosmos DB account found" -ForegroundColor Red
}

Write-Host "`n=== Summary for add-project.bicepparam ===" -ForegroundColor Green
Write-Host "param existingAccountName = '$aiAccount'"
Write-Host "param existingAiSearchName = '$searchService'"
Write-Host "param existingStorageName = '$storageAccount'"
Write-Host "param existingCosmosDBName = '$cosmosAccount'"
Write-Host "param accountResourceGroupName = '$ResourceGroupName'"
Write-Host "param aiSearchResourceGroupName = '$ResourceGroupName'"
Write-Host "param storageResourceGroupName = '$ResourceGroupName'"
Write-Host "param cosmosDBResourceGroupName = '$ResourceGroupName'"
