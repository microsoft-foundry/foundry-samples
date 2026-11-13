########## Create private network infrastructure with UAI and standard agent
##########

## Get subscription data
data "azurerm_client_config" "current" {}

## Create a random string for unique naming
resource "random_string" "unique" {
  length      = 4
  min_numeric = 4
  numeric     = true
  special     = false
  lower       = true
  upper       = false
}

locals {
  account_name = lower("${var.ai_services_name_prefix}${random_string.unique.result}")
}

## Create a resource group
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Reference existing User-Assigned Identity (if not creating new)
data "azurerm_user_assigned_identity" "existing" {
  count               = var.create_user_assigned_identity ? 0 : 1
  name                = var.user_assigned_identity_name
  resource_group_name = var.user_assigned_identity_resource_group
}

## Create new User-Assigned Identity (if requested)
resource "azurerm_user_assigned_identity" "uai" {
  count               = var.create_user_assigned_identity ? 1 : 0
  name                = var.user_assigned_identity_name
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
}

locals {
  uai_id           = var.create_user_assigned_identity ? azurerm_user_assigned_identity.uai[0].id : data.azurerm_user_assigned_identity.existing[0].id
  uai_principal_id = var.create_user_assigned_identity ? azurerm_user_assigned_identity.uai[0].principal_id : data.azurerm_user_assigned_identity.existing[0].principal_id
}

## Create Virtual Network
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-aifoundry${random_string.unique.result}"
  address_space       = var.vnet_address_space
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
}

## Create Subnet for private endpoints
resource "azurerm_subnet" "subnet" {
  name                 = "subnet-private-endpoints"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.subnet_address_prefix]
}

## Create Private DNS Zones
resource "azurerm_private_dns_zone" "ai_foundry" {
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "storage" {
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "search" {
  name                = "privatelink.search.windows.net"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "cosmos" {
  name                = "privatelink.documents.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

## Link DNS zones to VNet
resource "azurerm_private_dns_zone_virtual_network_link" "ai_foundry" {
  name                  = "vnet-link-ai-foundry"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.ai_foundry.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "storage" {
  name                  = "vnet-link-storage"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.storage.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "search" {
  name                  = "vnet-link-search"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.search.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "cosmos" {
  name                  = "vnet-link-cosmos"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.cosmos.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
}

## Create Storage Account with private endpoint
resource "azurerm_storage_account" "storage" {
  name                     = "aifoundry${random_string.unique.result}stor"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "ZRS"

  shared_access_key_enabled       = false
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_private_endpoint" "storage" {
  name                = "pe-storage-${random_string.unique.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.subnet.id

  private_service_connection {
    name                           = "psc-storage"
    private_connection_resource_id = azurerm_storage_account.storage.id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "storage-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.storage.id]
  }
}

## Create AI Search with private endpoint
resource "azurerm_search_service" "search" {
  name                = replace("aifoundry-${random_string.unique.result}-search", "_", "-")
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "standard"

  local_authentication_enabled  = true
  authentication_failure_mode   = "http401WithBearerChallenge"
  public_network_access_enabled = false
}

resource "azurerm_private_endpoint" "search" {
  name                = "pe-search-${random_string.unique.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.subnet.id

  private_service_connection {
    name                           = "psc-search"
    private_connection_resource_id = azurerm_search_service.search.id
    is_manual_connection           = false
    subresource_names              = ["searchService"]
  }

  private_dns_zone_group {
    name                 = "search-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.search.id]
  }
}

## Create Cosmos DB with private endpoint
resource "azurerm_cosmosdb_account" "cosmos" {
  name                              = "aifoundry${random_string.unique.result}cosmos"
  location                          = var.location
  resource_group_name               = azurerm_resource_group.rg.name
  offer_type                        = "Standard"
  kind                              = "GlobalDocumentDB"
  public_network_access_enabled     = false
  is_virtual_network_filter_enabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }
}

resource "azurerm_private_endpoint" "cosmos" {
  name                = "pe-cosmos-${random_string.unique.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.subnet.id

  private_service_connection {
    name                           = "psc-cosmos"
    private_connection_resource_id = azurerm_cosmosdb_account.cosmos.id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "cosmos-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.cosmos.id]
  }
}

## Create AI Foundry account with UAI and private endpoint
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.account_name
  location  = azurerm_resource_group.rg.location
  parent_id = azurerm_resource_group.rg.id

  identity {
    type         = "UserAssigned"
    identity_ids = [local.uai_id]
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.account_name
      publicNetworkAccess    = "Disabled"
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Deny"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }
}

resource "azurerm_private_endpoint" "ai_foundry" {
  name                = "pe-ai-foundry-${random_string.unique.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.subnet.id

  private_service_connection {
    name                           = "psc-ai-foundry"
    private_connection_resource_id = azapi_resource.ai_foundry.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name                 = "ai-foundry-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.ai_foundry.id]
  }
}

## Grant UAI access to Storage
resource "azurerm_role_assignment" "storage_blob_data_contributor" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = local.uai_principal_id
}

## Grant UAI access to AI Search
resource "azurerm_role_assignment" "search_index_data_contributor" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = local.uai_principal_id
}

resource "azurerm_role_assignment" "search_service_contributor" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = local.uai_principal_id
}

## Grant UAI access to Cosmos DB
resource "azurerm_cosmosdb_sql_role_assignment" "cosmos_contributor" {
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  role_definition_id  = "${azurerm_cosmosdb_account.cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = local.uai_principal_id
  scope               = azurerm_cosmosdb_account.cosmos.id
}

## Wait for role assignments to propagate
resource "time_sleep" "wait_for_rbac" {
  depends_on = [
    azurerm_role_assignment.storage_blob_data_contributor,
    azurerm_role_assignment.search_index_data_contributor,
    azurerm_role_assignment.search_service_contributor,
    azurerm_cosmosdb_sql_role_assignment.cosmos_contributor,
    azurerm_private_endpoint.ai_foundry,
    azurerm_private_endpoint.storage,
    azurerm_private_endpoint.search,
    azurerm_private_endpoint.cosmos
  ]
  create_duration = "90s"
}

## Create AI Foundry project with UAI
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = var.project_name
  location  = var.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type         = "UserAssigned"
    identity_ids = [local.uai_id]
  }

  body = {
    properties = {}
  }

  depends_on = [time_sleep.wait_for_rbac]
}

## Create connections
resource "azapi_resource" "storage_connection" {
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name      = "storage-connection"
  parent_id = azapi_resource.ai_foundry.id

  body = {
    properties = {
      category      = "AzureBlob"
      target        = azurerm_storage_account.storage.primary_blob_endpoint
      authType      = "AccessKey"
      isSharedToAll = true
      metadata = {
        ResourceId = azurerm_storage_account.storage.id
      }
    }
  }

  depends_on = [azapi_resource.ai_project]
}

resource "azapi_resource" "search_connection" {
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name      = "search-connection"
  parent_id = azapi_resource.ai_foundry.id

  body = {
    properties = {
      category      = "CognitiveSearch"
      target        = "https://${azurerm_search_service.search.name}.search.windows.net"
      authType      = "AAD"
      isSharedToAll = true
      metadata = {
        ResourceId = azurerm_search_service.search.id
      }
    }
  }

  depends_on = [azapi_resource.ai_project]
}

## Deploy model
resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.model_name
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      capacity = var.model_capacity
      name     = "GlobalStandard"
    }
    properties = {
      model = {
        name    = var.model_name
        format  = "OpenAI"
        version = var.model_version
      }
    }
  }

  depends_on = [azapi_resource.ai_project]
}
