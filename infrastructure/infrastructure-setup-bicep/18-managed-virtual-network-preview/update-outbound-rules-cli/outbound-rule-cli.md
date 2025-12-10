
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