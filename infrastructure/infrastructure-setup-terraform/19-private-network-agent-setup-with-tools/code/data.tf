########## Data sources for BYO (Bring Your Own) resources
########## These are only instantiated when using existing resources (count = 0 by default).
##########

data "azurerm_resource_group" "existing" {
  count = local.create_rg ? 0 : 1
  name  = var.existing_resource_group_name
}

## Existing Storage Account — needed for primary_blob_endpoint
data "azurerm_storage_account" "existing" {
  count               = local.create_storage ? 0 : 1
  name                = split("/", var.existing_storage_account_id)[8]
  resource_group_name = split("/", var.existing_storage_account_id)[4]
}

## Existing Cosmos DB — needed for endpoint
data "azurerm_cosmosdb_account" "existing" {
  count               = local.create_cosmos ? 0 : 1
  name                = split("/", var.existing_cosmosdb_account_id)[8]
  resource_group_name = split("/", var.existing_cosmosdb_account_id)[4]
}

## Existing AI Search — needed for location metadata in connections
data "azapi_resource" "existing_search" {
  count                  = local.create_search ? 0 : 1
  type                   = "Microsoft.Search/searchServices@2024-06-01-preview"
  resource_id            = var.existing_ai_search_id
  response_export_values = ["location"]
}
