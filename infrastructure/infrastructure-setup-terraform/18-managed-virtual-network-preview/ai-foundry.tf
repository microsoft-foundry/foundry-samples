# AI Foundry / Cognitive Services Account using AzAPI for preview features
resource "azapi_resource" "cognitive_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-10-01-preview"
  name      = local.foundry_name
  location  = azurerm_resource_group.main.location
  parent_id = azurerm_resource_group.main.id

  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    sku = {
      name = "S0"
    }
    kind = "AIServices"
    properties = merge(
      {
        allowProjectManagement = true
        apiProperties        = {}
        customSubDomainName  = local.foundry_name
        disableLocalAuth     = true
        networkAcls = {
          defaultAction         = "Deny"
          virtualNetworkRules   = []
          ipRules               = []
        }
        networkInjections = [
          {
            scenario                   = "agent"
            subnetArmId                = ""
            useMicrosoftManagedNetwork = true
          }
        ]
        publicNetworkAccess = "Disabled"
      },
      var.enable_storage ? {
        userOwnedStorage = [
          {
            resourceId = azurerm_storage_account.main[0].id
          }
        ]
      } : {},
      var.enable_cosmos ? {
        userOwnedCosmosDB = [
          {
            resourceId = azurerm_cosmosdb_account.main[0].id
          }
        ]
      } : {},
      var.enable_aisearch ? {
        userOwnedSearch = [
          {
            resourceId = azurerm_search_service.main[0].id
          }
        ]
      } : {}
    )
  }

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )

  lifecycle {
    ignore_changes = [
      body["properties"]["restore"],
      output
    ]
  }

  depends_on = [
    azurerm_storage_account.main,
    azurerm_cosmosdb_account.main,
    azurerm_search_service.main
  ]
}

# Role Assignment: Network Connection Approver for AI Foundry Account Identity
# This role is required for the AI Foundry account to approve managed network private endpoint connections
resource "azurerm_role_assignment" "foundry_network_connection_approver" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Azure AI Enterprise Network Connection Approver"
  principal_id         = azapi_resource.cognitive_account.identity[0].principal_id
}

# Role Assignment: Storage Blob Data Contributor
resource "azurerm_role_assignment" "foundry_storage_blob" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.cognitive_account.identity[0].principal_id
}

# Role Assignment: Contributor on Storage Account
resource "azurerm_role_assignment" "foundry_storage_contributor" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Contributor"
  principal_id         = azapi_resource.cognitive_account.identity[0].principal_id
}

# Private Endpoint for AI Foundry
resource "azurerm_private_endpoint" "cognitive_services" {
  count               = var.enable_networking ? 1 : 0
  name                = "${local.foundry_name}-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${local.foundry_name}-psc"
    private_connection_resource_id = azapi_resource.cognitive_account.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  dynamic "private_dns_zone_group" {
    for_each = var.enable_dns ? [1] : []
    content {
      name = "cognitive-services-dns-zone-group"
      private_dns_zone_ids = [
        azurerm_private_dns_zone.cognitive_services[0].id,
        azurerm_private_dns_zone.openai[0].id,
        azurerm_private_dns_zone.aifoundry_api[0].id,
        azurerm_private_dns_zone.aifoundry_notebooks[0].id,
        azurerm_private_dns_zone.aifoundry_services[0].id
      ]
    }
  }
}

# Managed Network Configuration
resource "azapi_resource" "managed_network" {
  type      = "Microsoft.CognitiveServices/accounts/managedNetworks@2025-10-01-preview"
  name      = "default"
  parent_id = azapi_resource.cognitive_account.id

  schema_validation_enabled = false

  body = {
    properties = {
      managedNetwork = {
        isolationMode      = "AllowInternetOutbound"
        managedNetworkKind = "V2"
      }
    }
  }
}

# Wait for Storage Account to be fully created before creating outbound rule
resource "time_sleep" "wait_storage" {
  count           = var.enable_storage ? 1 : 0
  create_duration = "10m"

  depends_on = [
    azurerm_storage_account.main,
    azurerm_private_endpoint.storage_blob
  ]
}

# Managed Network Outbound Rule for Storage Account
resource "azapi_resource" "storage_outbound_rule" {
  count     = var.enable_storage ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/managedNetworks/outboundRules@2025-10-01-preview"
  name      = "storage-blob-rule"
  parent_id = azapi_resource.managed_network.id

  schema_validation_enabled = false

  body = {
    properties = {
      type = "PrivateEndpoint"
      destination = {
        serviceResourceId = azurerm_storage_account.main[0].id
        subresourceTarget = "blob"
      }
      category = "UserDefined"
    }
  }

  depends_on = [
    time_sleep.wait_storage,
    azurerm_role_assignment.foundry_network_connection_approver,
    azurerm_role_assignment.foundry_storage_blob,
    azurerm_role_assignment.foundry_storage_contributor
  ]
}

# AI Foundry Project
resource "azapi_resource" "ai_foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = "firstProject"
  location  = var.location
  parent_id = azapi_resource.cognitive_account.id

  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = "AI Foundry Project"
    }
  }

  depends_on = [
    azapi_resource.cognitive_account
  ]
}

# Wait for RBAC propagation
resource "time_sleep" "wait_rbac" {
  create_duration = "60s"

  depends_on = [
    azurerm_role_assignment.foundry_storage_blob,
    azurerm_role_assignment.foundry_storage_contributor
  ]
}

# Role Assignment: Project Identity - Storage Blob Data Contributor
resource "azurerm_role_assignment" "project_storage_blob" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.ai_foundry_project.identity[0].principal_id
}

# Role Assignment: Project Identity - AI Search Index Data Contributor
resource "azurerm_role_assignment" "project_search_index" {
  count                = var.enable_aisearch ? 1 : 0
  scope                = azurerm_search_service.main[0].id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.ai_foundry_project.identity[0].principal_id
}

# Role Assignment: Project Identity - AI Search Service Contributor
resource "azurerm_role_assignment" "project_search_contributor" {
  count                = var.enable_aisearch ? 1 : 0
  scope                = azurerm_search_service.main[0].id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.ai_foundry_project.identity[0].principal_id
}

# Role Assignment: Project Identity - Cosmos DB Account Reader
resource "azurerm_role_assignment" "project_cosmos_reader" {
  count                = var.enable_cosmos ? 1 : 0
  scope                = azurerm_cosmosdb_account.main[0].id
  role_definition_name = "Cosmos DB Account Reader Role"
  principal_id         = azapi_resource.ai_foundry_project.identity[0].principal_id
}

# Role Assignment: Project Identity - Cosmos DB Operator (required before capability host)
resource "azurerm_role_assignment" "project_cosmos_operator" {
  count                = var.enable_cosmos ? 1 : 0
  scope                = azurerm_cosmosdb_account.main[0].id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.ai_foundry_project.identity[0].principal_id
}

# Wait for project-level RBAC propagation before creating capability host
# This prevents capability host creation failures due to permissions not being ready
resource "time_sleep" "wait_project_rbac" {
  create_duration = "90s"

  depends_on = [
    azurerm_role_assignment.project_storage_blob,
    azurerm_role_assignment.project_search_index,
    azurerm_role_assignment.project_search_contributor,
    azurerm_role_assignment.project_cosmos_reader,
    azurerm_role_assignment.project_cosmos_operator
  ]
}

# Wait for managed network outbound rules to fully provision
# Outbound rules need additional time beyond creation to be in Succeeded state
# Azure managed network provisioning can take several minutes
resource "time_sleep" "wait_outbound_rules" {
  create_duration = "600s"

  depends_on = [
    azapi_resource.storage_outbound_rule,
    azapi_resource.cosmos_outbound_rule,
    azapi_resource.aisearch_outbound_rule
  ]
}

# AI Foundry Project Capability Host (matches Bicep implementation)
# This configures the capability host at the project level with connection references
resource "azapi_resource" "project_capability_host" {
  count = var.enable_storage && var.enable_cosmos && var.enable_aisearch ? 1 : 0

  type      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name      = "caphostproj"
  parent_id = azapi_resource.ai_foundry_project.id

  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind       = "Agents"
      vectorStoreConnections   = [azurerm_search_service.main[0].name]
      storageConnections       = [azurerm_storage_account.main[0].name]
      threadStorageConnections = [azurerm_cosmosdb_account.main[0].name]
    }
  }

  depends_on = [
    # Core resources must exist
    azapi_resource.ai_foundry_project,
    azapi_resource.conn_aisearch,
    azapi_resource.conn_cosmosdb,
    azapi_resource.conn_storage,
    # Project role assignments must be complete (matching Bicep dependencies)
    azurerm_role_assignment.project_cosmos_reader,
    azurerm_role_assignment.project_cosmos_operator,
    azurerm_role_assignment.project_storage_blob,
    azurerm_role_assignment.project_search_index,
    azurerm_role_assignment.project_search_contributor,
    # Wait for RBAC propagation
    time_sleep.wait_project_rbac,
    # CRITICAL: All outbound rules must be created AND provisioned before capability host
    # The capability host validates that outbound rules exist and are in Succeeded state
    azapi_resource.storage_outbound_rule,
    azapi_resource.cosmos_outbound_rule,
    azapi_resource.aisearch_outbound_rule,
    time_sleep.wait_outbound_rules
  ]
}

# Connection: AI Search
resource "azapi_resource" "conn_aisearch" {
  count     = var.enable_aisearch ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name      = azurerm_search_service.main[0].name
  parent_id = azapi_resource.ai_foundry_project.id

  schema_validation_enabled = false

  body = {
    properties = {
      category = "CognitiveSearch"
      target   = "https://${azurerm_search_service.main[0].name}.search.windows.net"
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_search_service.main[0].id
        location   = azurerm_search_service.main[0].location
      }
    }
  }
}

# Connection: Cosmos DB
resource "azapi_resource" "conn_cosmosdb" {
  count     = var.enable_cosmos ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name      = azurerm_cosmosdb_account.main[0].name
  parent_id = azapi_resource.ai_foundry_project.id

  schema_validation_enabled = false

  body = {
    properties = {
      category = "CosmosDb"
      target   = azurerm_cosmosdb_account.main[0].endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_cosmosdb_account.main[0].id
        location   = azurerm_cosmosdb_account.main[0].location
      }
    }
  }
}

# Connection: Storage Account
resource "azapi_resource" "conn_storage" {
  count     = var.enable_storage ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name      = azurerm_storage_account.main[0].name
  parent_id = azapi_resource.ai_foundry_project.id

  schema_validation_enabled = false

  body = {
    properties = {
      category = "AzureStorageAccount"
      target   = azurerm_storage_account.main[0].primary_blob_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_storage_account.main[0].id
        location   = azurerm_storage_account.main[0].location
      }
    }
  }
}

# Local variable to format project workspace ID as GUID
# The project.properties.internalId comes back as a 32-char hex string
# We need to format it as 8-4-4-4-12 GUID format
locals {
  # Extract the workspace ID from the project output
  project_workspace_id_raw = try(jsondecode(azapi_resource.ai_foundry_project.output).properties.internalId, "")
  
  # Format as GUID if we have a valid 32-character string
  project_workspace_id_guid = length(local.project_workspace_id_raw) == 32 ? format(
    "%s-%s-%s-%s-%s",
    substr(local.project_workspace_id_raw, 0, 8),
    substr(local.project_workspace_id_raw, 8, 4),
    substr(local.project_workspace_id_raw, 12, 4),
    substr(local.project_workspace_id_raw, 16, 4),
    substr(local.project_workspace_id_raw, 20, 12)
  ) : ""
}

# Role Assignment: Storage Blob Data Owner with ABAC condition
# This must be assigned AFTER the capability host is created
# The condition restricts access to containers starting with workspace ID and ending with -azureml-agent
resource "azurerm_role_assignment" "project_storage_blob_owner_containers" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.ai_foundry_project.identity[0].principal_id
  
  # ABAC condition matching Bicep template
  condition         = "((!(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read'}) AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action'}) AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write'})) OR (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase '${local.project_workspace_id_guid}' AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase '*-azureml-agent'))"
  condition_version = "2.0"

  depends_on = [
    azapi_resource.project_capability_host
  ]
}

# Role Assignment: Cosmos DB Built-in Data Contributor
# This must be assigned AFTER the capability host is created
resource "azurerm_cosmosdb_sql_role_assignment" "project_cosmos_builtin_contributor" {
  count               = var.enable_cosmos ? 1 : 0
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main[0].name
  
  # Cosmos DB Built-in Data Contributor role
  role_definition_id = "${azurerm_cosmosdb_account.main[0].id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  
  principal_id = azapi_resource.ai_foundry_project.identity[0].principal_id
  scope        = azurerm_cosmosdb_account.main[0].id

  depends_on = [
    azapi_resource.project_capability_host
  ]
}
