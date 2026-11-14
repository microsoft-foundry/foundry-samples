########## Create private network infrastructure for AI Foundry with agent tools
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

## Create a resource group
resource "azurerm_resource_group" "rg" {
  count    = local.create_rg ? 1 : 0
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Create Virtual Network (always needed for private endpoints)
resource "azurerm_virtual_network" "vnet" {
  count               = local.create_vnet ? 1 : 0
  name                = "vnet-aifoundry${random_string.unique.result}"
  address_space       = var.vnet_address_space
  location            = var.location
  resource_group_name = local.rg_name
}

## Create Subnet for agent compute (used by networkInjections)
resource "azurerm_subnet" "subnet_agent" {
  count                = var.existing_agent_subnet_id == "" ? 1 : 0
  name                 = "agent-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = local.vnet_name
  address_prefixes     = [local.subnet_agent_address_prefix]

  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }
}

## Create Subnet for private endpoints
resource "azurerm_subnet" "subnet_pe" {
  count                = var.existing_pe_subnet_id == "" ? 1 : 0
  name                 = "pe-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = local.vnet_name
  address_prefixes     = [local.subnet_pe_address_prefix]

  depends_on = [azurerm_subnet.subnet_agent]
}

## Create Subnet for MCP/OpenAPI/A2A tool servers
resource "azurerm_subnet" "subnet_mcp" {
  count                = var.existing_mcp_subnet_id == "" ? 1 : 0
  name                 = "mcp-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = local.vnet_name
  address_prefixes     = [local.subnet_mcp_address_prefix]

  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }

  depends_on = [azurerm_subnet.subnet_pe]
}

########## Create resources required to store agent data
##########

## Create a storage account for agent data
##
resource "azurerm_storage_account" "storage_account" {
  count               = local.create_storage ? 1 : 0
  name                = "aifoundry${random_string.unique.result}storage"
  resource_group_name = local.rg_name
  location            = var.location

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "ZRS"

  ## Identity configuration
  shared_access_key_enabled = false

  ## Network access configuration
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }
}

## Create the Cosmos DB account to store agent threads
##
resource "azurerm_cosmosdb_account" "cosmosdb" {
  count               = local.create_cosmos ? 1 : 0
  name                = "aifoundry${random_string.unique.result}cosmosdb"
  location            = var.location
  resource_group_name = local.rg_name

  # General settings
  offer_type        = "Standard"
  kind              = "GlobalDocumentDB"
  free_tier_enabled = false

  # Set security-related settings
  local_authentication_disabled = true
  public_network_access_enabled = false

  # Set high availability and failover settings
  automatic_failover_enabled       = false
  multiple_write_locations_enabled = false

  # Configure consistency settings
  consistency_policy {
    consistency_level = "Session"
  }

  # Configure single location with no zone redundancy to reduce costs
  geo_location {
    location          = var.location
    failover_priority = 0
    zone_redundant    = false
  }
}

## Create an AI Search instance that will be used to store vector embeddings
##
resource "azapi_resource" "ai_search" {
  count                     = local.create_search ? 1 : 0
  type                      = "Microsoft.Search/searchServices@2024-06-01-preview"
  name                      = "aifoundry${random_string.unique.result}search"
  parent_id                 = local.rg_id
  location                  = var.location
  schema_validation_enabled = false

  body = {
    sku = {
      name = "standard"
    }

    identity = {
      type = "SystemAssigned"
    }

    properties = {

      # Search-specific properties
      replicaCount   = 1
      partitionCount = 1
      hostingMode    = "Default"
      semanticSearch = "disabled"

      # Identity-related controls
      disableLocalAuth = false
      authOptions = {
        aadOrApiKey = {
          aadAuthFailureMode = "http401WithBearerChallenge"
        }
      }

      # Networking-related controls
      publicNetworkAccess = "Disabled"
      networkRuleSet = {
        bypass = "None"
      }
    }
  }
}

########## Create AI Foundry resource
##########

## Wait for VNet/subnet propagation before creating AI Foundry.
## The Cognitive Services RP validates the VNet via ARM, which has eventual consistency.
## Without this delay, networkInjections can fail with "virtual network could not be found".
resource "time_sleep" "wait_for_subnet_propagation" {
  depends_on      = [azurerm_subnet.subnet_agent]
  create_duration = "60s"
}

## Create the AI Foundry resource
##
resource "azapi_resource" "ai_foundry" {
  depends_on = [
    azurerm_subnet.subnet_agent,
    time_sleep.wait_for_subnet_propagation,
    azapi_resource_action.purge_ai_foundry
  ]

  type                      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name                      = local.account_name
  parent_id                 = local.rg_id
  location                  = coalesce(var.foundry_location, local.rg_location)

  lifecycle {
    precondition {
      condition     = coalesce(var.foundry_location, local.rg_location) == var.location
      error_message = "The Foundry account must be in the same region as the VNet (var.location). Set foundry_location to var.location when the resource group is in a different region."
    }
  }
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      # Support both Entra ID and API Key authentication for underlying Cognitive Services account
      disableLocalAuth = false

      # Specifies that this is an AI Foundry resource
      allowProjectManagement = true

      # Set custom subdomain name for DNS names created for this Foundry resource
      customSubDomainName = local.account_name

      # Network-related controls
      # Disable public access but allow Trusted Azure Services exception
      publicNetworkAccess = "Disabled"
      networkAcls = {
        defaultAction       = "Deny"
        bypass              = "AzureServices"
        virtualNetworkRules = []
        ipRules             = []
      }

      # Enable VNet injection for Standard Agents
      networkInjections = [
        {
          scenario                   = "agent"
          subnetArmId                = local.subnet_agent_id
          useMicrosoftManagedNetwork = false
        }
      ]
    }
  }
}

## Deploy a model in the AI Foundry resource
##
resource "azapi_resource" "model_deployment" {
  depends_on = [
    azapi_resource.ai_foundry
  ]

  type                      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name                      = var.model_name
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

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
}

########## Create Private DNS Zones, Links, and Private Endpoints
##########

## Create required Private DNS Zones
##
resource "azurerm_private_dns_zone" "plz_cosmos_db" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.documents.azure.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_ai_search" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.search.windows.net"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_storage_blob" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_cognitive_services" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_ai_services" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.services.ai.azure.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_openai" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.openai.azure.com"
  resource_group_name = local.rg_name
}

## Create Private DNS Zone Links to link the Private DNS Zones to the virtual network
##
resource "azurerm_private_dns_zone_virtual_network_link" "plz_cosmos_db_link" {
  count                 = local.create_dns_zones ? 1 : 0
  name                  = "privatelink-documents-azure-com-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_cosmos_db[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_ai_search_link" {
  count                 = local.create_dns_zones ? 1 : 0
  depends_on            = [azurerm_private_dns_zone_virtual_network_link.plz_cosmos_db_link]
  name                  = "privatelink-search-windows-net-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_ai_search[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_storage_blob_link" {
  count                 = local.create_dns_zones ? 1 : 0
  depends_on            = [azurerm_private_dns_zone_virtual_network_link.plz_ai_search_link]
  name                  = "privatelink-blob-core-windows-net-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_storage_blob[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_cognitive_services_link" {
  count                 = local.create_dns_zones ? 1 : 0
  depends_on            = [azurerm_private_dns_zone_virtual_network_link.plz_storage_blob_link]
  name                  = "privatelink-cognitiveservices-azure-com-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_cognitive_services[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_ai_services_link" {
  count                 = local.create_dns_zones ? 1 : 0
  depends_on            = [azurerm_private_dns_zone_virtual_network_link.plz_cognitive_services_link]
  name                  = "privatelink-services-ai-azure-com-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_ai_services[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_openai_link" {
  count                 = local.create_dns_zones ? 1 : 0
  depends_on            = [azurerm_private_dns_zone_virtual_network_link.plz_ai_services_link]
  name                  = "privatelink-openai-azure-com-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_openai[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

## Fabric DNS Zone and VNet Link (only when Fabric workspace is provided)
resource "azurerm_private_dns_zone" "plz_fabric" {
  count               = local.create_dns_zones && local.create_fabric ? 1 : 0
  name                = "privatelink.fabric.microsoft.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_fabric_link" {
  count                 = local.create_dns_zones && local.create_fabric ? 1 : 0
  depends_on            = [azurerm_private_dns_zone_virtual_network_link.plz_openai_link]
  name                  = "privatelink-fabric-microsoft-com-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_fabric[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

## Create Private Endpoints for resources
##
resource "azurerm_private_endpoint" "pe_storage" {
  depends_on = [azurerm_private_dns_zone_virtual_network_link.plz_openai_link]

  name                = "${local.storage_name}-${random_string.unique.result}-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "${local.storage_name}-${random_string.unique.result}-private-link-service-connection"
    private_connection_resource_id = local.storage_id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "${local.storage_name}-${random_string.unique.result}-dns-group"
    private_dns_zone_ids = [local.dns_zone_storage_blob_id]
  }
}

resource "azurerm_private_endpoint" "pe_cosmos" {
  depends_on = [azurerm_private_endpoint.pe_storage]

  name                = "${local.cosmos_name}-${random_string.unique.result}-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "${local.cosmos_name}-${random_string.unique.result}-private-link-service-connection"
    private_connection_resource_id = local.cosmos_id
    subresource_names              = ["Sql"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "${local.cosmos_name}-${random_string.unique.result}-dns-group"
    private_dns_zone_ids = [local.dns_zone_cosmos_db_id]
  }
}

resource "azurerm_private_endpoint" "pe_search" {
  depends_on = [azurerm_private_endpoint.pe_cosmos]

  name                = "${local.search_name}-${random_string.unique.result}-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "${local.search_name}-${random_string.unique.result}-private-link-service-connection"
    private_connection_resource_id = local.search_id
    subresource_names              = ["searchService"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "${local.search_name}-${random_string.unique.result}-dns-group"
    private_dns_zone_ids = [local.dns_zone_search_id]
  }
}

resource "azurerm_private_endpoint" "pe_ai_foundry" {
  depends_on = [azurerm_private_endpoint.pe_search]

  name                = "${azapi_resource.ai_foundry.name}-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "${azapi_resource.ai_foundry.name}-private-link-service-connection"
    private_connection_resource_id = azapi_resource.ai_foundry.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name = "${azapi_resource.ai_foundry.name}-dns-group"
    private_dns_zone_ids = [
      local.dns_zone_cognitive_services_id,
      local.dns_zone_ai_services_id,
      local.dns_zone_openai_id
    ]
  }
}

## Create Fabric Private Endpoint (only when Fabric workspace is provided)
resource "azurerm_private_endpoint" "pe_fabric" {
  count      = local.create_fabric ? 1 : 0
  depends_on = [azurerm_private_endpoint.pe_ai_foundry]

  name                = "${local.fabric_name}-fabric-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "${local.fabric_name}-private-link-service-connection"
    private_connection_resource_id = var.existing_fabric_workspace_id
    subresource_names              = ["Fabric"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "${local.fabric_name}-dns-group"
    private_dns_zone_ids = [local.dns_zone_fabric_id]
  }
}

## Create AI Foundry project
resource "azapi_resource" "ai_project" {
  depends_on = [
    azurerm_private_endpoint.pe_storage,
    azurerm_private_endpoint.pe_search,
    azurerm_private_endpoint.pe_cosmos,
    azurerm_private_endpoint.pe_ai_foundry
  ]
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name                      = var.project_name
  location                  = azapi_resource.ai_foundry.location
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    sku = {
      name = "S0"
    }
    properties = {
      description = "AI Foundry project with private network agent tools"
      displayName = var.project_name
    }
  }

  response_export_values = [
    "identity.principalId",
    "properties.internalId"
  ]
}

## Wait 10 seconds for the AI Foundry project system-assigned managed identity to replicate through Entra ID
resource "time_sleep" "wait_project_identities" {
  depends_on = [
    azapi_resource.ai_project
  ]
  create_duration = "10s"
}

## Create project-level connections (AAD auth)
resource "azapi_resource" "conn_cosmosdb" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.cosmos_name
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  depends_on = [azapi_resource.ai_project]

  body = {
    name = local.cosmos_name
    properties = {
      category = "CosmosDb"
      target   = local.cosmos_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.cosmos_id
        location   = local.cosmos_location
      }
    }
  }
}

resource "azapi_resource" "conn_storage" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.storage_name
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  depends_on = [azapi_resource.ai_project]

  body = {
    name = local.storage_name
    properties = {
      category = "AzureStorageAccount"
      target   = local.storage_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.storage_id
        location   = local.storage_location
      }
    }
  }
}

resource "azapi_resource" "conn_aisearch" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.search_name
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  depends_on = [azapi_resource.ai_project]

  body = {
    name = local.search_name
    properties = {
      category = "CognitiveSearch"
      target   = "https://${local.search_name}.search.windows.net"
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.search_id
        location   = local.search_location
      }
    }
  }
}

## Create the necessary role assignments for the AI Foundry project over the resources used to store agent data
resource "azurerm_role_assignment" "cosmosdb_operator_ai_foundry_project" {
  depends_on = [
    time_sleep.wait_project_identities
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.rg_name}cosmosdboperator")
  scope                = local.cosmos_id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}

resource "azurerm_role_assignment" "storage_blob_data_contributor_ai_foundry_project" {
  depends_on = [
    time_sleep.wait_project_identities
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.storage_name}storageblobdatacontributor")
  scope                = local.storage_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}

resource "azurerm_role_assignment" "search_index_data_contributor_ai_foundry_project" {
  depends_on = [
    time_sleep.wait_project_identities
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.search_name}searchindexdatacontributor")
  scope                = local.search_id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}

resource "azurerm_role_assignment" "search_service_contributor_ai_foundry_project" {
  depends_on = [
    time_sleep.wait_project_identities
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.search_name}searchservicecontributor")
  scope                = local.search_id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}

## Pause 60 seconds to allow for role assignments to propagate
resource "time_sleep" "wait_rbac" {
  depends_on = [
    azurerm_role_assignment.cosmosdb_operator_ai_foundry_project,
    azurerm_role_assignment.storage_blob_data_contributor_ai_foundry_project,
    azurerm_role_assignment.search_index_data_contributor_ai_foundry_project,
    azurerm_role_assignment.search_service_contributor_ai_foundry_project
  ]
  create_duration = "60s"
}

## Create the AI Foundry project capability host
##
resource "azapi_resource" "ai_foundry_project_capability_host" {
  depends_on = [
    azapi_resource.conn_cosmosdb,
    azapi_resource.conn_storage,
    azapi_resource.conn_aisearch,
    time_sleep.wait_rbac
  ]
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "caphostproj"
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind = "Agents"
      vectorStoreConnections = [
        local.search_name
      ]
      storageConnections = [
        local.storage_name
      ]
      threadStorageConnections = [
        local.cosmos_name
      ]
    }
  }
}

## Create the necessary data plane role assignments to the CosmosDb account created by the AI Foundry Project
##
resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_db_sql_role_aifp" {
  depends_on = [
    azapi_resource.ai_foundry_project_capability_host
  ]
  name                = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}cosmosdb_dbsqlrole")
  resource_group_name = local.cosmos_rg_name
  account_name        = local.cosmos_name
  scope               = local.cosmos_id
  role_definition_id  = "${local.cosmos_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.ai_project.output.identity.principalId
}

## Create the necessary data plane role assignments to the Azure Storage Account containers created by the AI Foundry Project
##
resource "azurerm_role_assignment" "storage_blob_data_owner_ai_foundry_project" {
  depends_on = [
    azapi_resource.ai_foundry_project_capability_host
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.storage_name}storageblobdataowner")
  scope                = local.storage_id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
  condition_version    = "2.0"
  condition            = <<-EOT
  (
    (
      !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read'})
      AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action'})
      AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write'})
    )
    OR
    (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase '${local.project_id_guid}'
    AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase '*-azureml-agent')
  )
  EOT
}

########## Optional: Azure Container Registry with Private Endpoint
##########

resource "azurerm_container_registry" "acr" {
  count = var.enable_container_registry ? 1 : 0

  name                          = "acr${random_string.unique.result}"
  resource_group_name           = local.rg_name
  location                      = var.location
  sku                           = "Premium"
  admin_enabled                 = false
  public_network_access_enabled = var.developer_ip_cidr != "" ? true : false

  dynamic "network_rule_set" {
    for_each = var.developer_ip_cidr != "" ? [1] : []
    content {
      default_action = "Deny"
      ip_rule {
        action   = "Allow"
        ip_range = var.developer_ip_cidr
      }
    }
  }
}

resource "azurerm_private_dns_zone" "plz_acr" {
  count               = var.enable_container_registry && local.create_dns_zones ? 1 : 0
  name                = "privatelink.azurecr.io"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_acr_link" {
  count = var.enable_container_registry && local.create_dns_zones ? 1 : 0

  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_openai_link
  ]

  name                  = "privatelink-azurecr-io-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_acr[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_endpoint" "pe_acr" {
  count = var.enable_container_registry ? 1 : 0

  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_acr_link,
    azurerm_private_endpoint.pe_ai_foundry
  ]

  name                = "acr${random_string.unique.result}-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "acr${random_string.unique.result}-private-link-service-connection"
    private_connection_resource_id = azurerm_container_registry.acr[0].id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "acr${random_string.unique.result}-dns-group"
    private_dns_zone_ids = [local.dns_zone_acr_id]
  }
}

## Grant the project identity AcrPull on the container registry
resource "azurerm_role_assignment" "acr_pull_project" {
  count = var.enable_container_registry ? 1 : 0

  depends_on = [
    azapi_resource.ai_project,
    azurerm_container_registry.acr
  ]

  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}acr${random_string.unique.result}acrpull")
  scope                = azurerm_container_registry.acr[0].id
  role_definition_name = "AcrPull"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}

########## Destroy-time resources
##########

## Added AI Foundry account purger to avoid running into InUseSubnetCannotBeDeleted-lock caused by the agent subnet delegation.
## The azapi_resource_action.purge_ai_foundry (only gets executed during destroy) purges the AI foundry account removing /subnets/snet-agent/serviceAssociationLinks/legionservicelink so the agent subnet can get properly removed.

resource "azapi_resource_action" "purge_ai_foundry" {
  method      = "DELETE"
  resource_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.CognitiveServices/locations/${var.location}/resourceGroups/${local.rg_name}/deletedAccounts/${local.account_name}"
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  when        = "destroy"

  depends_on = [time_sleep.purge_ai_foundry_cooldown]
}

resource "time_sleep" "purge_ai_foundry_cooldown" {
  destroy_duration = "900s" # 10-15m is enough time to let the backend remove the /subnets/snet-agent/serviceAssociationLinks/legionservicelink

  depends_on = [azurerm_subnet.subnet_agent]
}