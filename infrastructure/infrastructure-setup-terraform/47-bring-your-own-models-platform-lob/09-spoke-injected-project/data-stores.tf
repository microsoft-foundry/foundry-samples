# BYO agent-store resources required by Standard Agent Setup. The project's
# capability host binds to these for thread storage (Cosmos), file storage
# (Blob), and vector search (AI Search). All are private (PNA disabled) and
# reached over private endpoints (see dns.tf).

resource "azurerm_storage_account" "agent" {
  name                = local.storage_name
  resource_group_name = local.spoke_rg_name
  location            = local.location
  tags                = local.common_tags

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "ZRS"

  shared_access_key_enabled       = false
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_cosmosdb_account" "agent" {
  name                = local.cosmos_name
  location            = local.location
  resource_group_name = local.spoke_rg_name
  tags                = local.common_tags

  offer_type        = "Standard"
  kind              = "GlobalDocumentDB"
  free_tier_enabled = false

  local_authentication_enabled  = false
  public_network_access_enabled = false

  automatic_failover_enabled       = false
  multiple_write_locations_enabled = false

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = local.location
    failover_priority = 0
    zone_redundant    = false
  }
}

resource "azapi_resource" "agent_search" {
  type                      = "Microsoft.Search/searchServices@2025-05-01"
  name                      = local.search_name
  parent_id                 = local.spoke_rg_id
  location                  = local.location
  schema_validation_enabled = true
  tags                      = local.common_tags

  body = {
    sku = {
      name = "standard"
    }
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      replicaCount   = 1
      partitionCount = 1
      hostingMode    = "Default"
      semanticSearch = "disabled"

      disableLocalAuth = false
      authOptions = {
        aadOrApiKey = {
          aadAuthFailureMode = "http401WithBearerChallenge"
        }
      }

      publicNetworkAccess = "Disabled"
      networkRuleSet = {
        bypass = "None"
      }
    }
  }
}
