
## Outbound Rules CLI

### Outbound Rule for Storage account 

Below is the CLI command to create an outbound rule from the managed VNET to your storage account. In the sample template we create the managed VNET PE for storage, but you will need two more for your CosmosDB resource and your Search resource. 

az rest --method PUT --url 'https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{foundry-account}/managedNetworks/default/outboundRules/test-rule?api-version=2025-10-01-preview' \
--body '{
  "id": "/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{foundry-account}/managedNetworks/default/outboundRules/test-rule-str",
  "name": "test-rule-str",
  "type": "Microsoft.CognitiveServices/accounts/managedNetworks/outboundRules",
  "properties": {
    "type": "PrivateEndpoint",
    "destination": {
      "serviceResourceId": "/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.Storage/storageAccounts/{storage-account}",
      "subresourceTarget": "blob"
    },
    "category": "UserDefined"
  }
}'

### Outbound Rule for CDB account 

Below is the CLI command to create an outbound rule from the managed VNET to your CDB account. 

az rest --method PUT --url 'https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{foundry-account}/managedNetworks/default/outboundRules/test-rule?api-version=2025-10-01-preview' \
--body '{
  "id": "/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{foundry-account}/managedNetworks/default/outboundRules/test-rule-cdb",
  "name": "test-rule-cdb",
  "type": "Microsoft.CognitiveServices/accounts/managedNetworks/outboundRules",
  "properties": {
    "type": "PrivateEndpoint",
    "destination": {
      "serviceResourceId": "/subscriptions/${cosmosDBSubscriptionId}/resourceGroups/${cosmosDBResourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/${cosmosDBName}",
      "subresourceTarget": "Sql"
    },
    "category": "UserDefined"
  }
}'

### Outbound Rule for Search account 

Below is the CLI command to create an outbound rule from the managed VNET to your Search account. 

az rest --method PUT --url 'https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{foundry-account}/managedNetworks/default/outboundRules/test-rule?api-version=2025-10-01-preview' \
--body '{
  "id": "/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{foundry-account}/managedNetworks/default/outboundRules/test-rule-search",
  "name": "test-rule-search",
  "type": "Microsoft.CognitiveServices/accounts/managedNetworks/outboundRules",
  "properties": {
    "type": "PrivateEndpoint",
    "destination": {
      "serviceResourceId": "/subscriptions/${aiSearchSubscriptionId}/resourceGroups/${aiSearchResourceGroupName}/providers/Microsoft.Search/searchServices/${aiSearchName}",
      "subresourceTarget": "searchService"
    },
    "category": "UserDefined"
  }
}'

# Batch Outbound Rules CLI

This folder contains the JSON payload for creating batch outbound rules via Azure REST API. This allows youto create all the outbound PE rules in one go instead of the individual PE rules one at a time. 

## Usage

Replace the placeholders in `batch-outbound-rules.json` with your actual values:
- `{subscriptionId}` - Your Azure subscription ID
- `{resourceGroupName}` - Your resource group name
- `{accountName}` - Your AI Services account name
- `{storageSubscriptionId}` - Storage account subscription ID
- `{storageResourceGroupName}` - Storage account resource group
- `{storageName}` - Storage account name
- `{aiSearchSubscriptionId}` - AI Search subscription ID
- `{aiSearchResourceGroupName}` - AI Search resource group
- `{aiSearchName}` - AI Search service name
- `{cosmosDBSubscriptionId}` - Cosmos DB subscription ID
- `{cosmosDBResourceGroupName}` - Cosmos DB resource group
- `{cosmosDBName}` - Cosmos DB account name

## REST API Call

```bash
az rest --method POST \
  --uri "https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.CognitiveServices/accounts/{accountName}/managedNetworks/default/batchOutboundRules?api-version=2025-10-01-preview" \
  --body @batch-outbound-rules.json
```

## PowerShell Example

```powershell
$body = Get-Content -Path "batch-outbound-rules.json" -Raw
$uri = "https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.CognitiveServices/accounts/{accountName}/managedNetworks/default/batchOutboundRules?api-version=2025-10-01-preview"

az rest --method POST --uri $uri --body $body
```

## Notes

- This is a POST action, not supported directly in Bicep
- Run this after the main Bicep deployment completes
- The managed network must already exist before running this command

