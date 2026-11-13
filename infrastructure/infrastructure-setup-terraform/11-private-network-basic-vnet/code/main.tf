########## Create infrastructure resources
##########

## Get subscription data
##
data "azurerm_client_config" "current" {}

## Create a random string
##
resource "random_string" "unique" {
  length      = 4
  min_numeric = 4
  numeric     = true
  special     = false
  lower       = true
  upper       = false
}

## Create a resource group for the resources to be stored in
##
resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name != "" ? var.resource_group_name : "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

########## Create Virtual Network and Subnets
##########

## Create a virtual network for the AI Foundry resource
##
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-agents${random_string.unique.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space = [
    var.virtual_network_address_space
  ]
}

## Create the agent subnet delegated to Microsoft.App/environments for VNet injection
##
resource "azurerm_subnet" "subnet_agent" {
  name                 = "snet-agent"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes = [
    var.agent_subnet_address_prefix
  ]
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

## Create the private endpoint subnet
##
resource "azurerm_subnet" "subnet_pe" {
  name                 = "snet-pe"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes = [
    var.private_endpoint_subnet_address_prefix
  ]
}

########## Create AI Foundry resource
##########

## Create the AI Foundry resource with VNet injection
##
resource "azapi_resource" "ai_foundry" {
  depends_on = [
    azurerm_subnet.subnet_agent,
    azapi_resource_action.purge_ai_foundry
  ]

  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = "aifoundry${random_string.unique.result}"
  parent_id                 = azurerm_resource_group.rg.id
  location                  = azurerm_resource_group.rg.location
  schema_validation_enabled = false

  body = {
    kind = "AIServices",
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }

    properties = {
      # Support both Entra ID and API Key authentication
      disableLocalAuth = false

      # Specifies that this is an AI Foundry resource
      allowProjectManagement = true

      # Set custom subdomain name for DNS
      customSubDomainName = "aifoundry${random_string.unique.result}"

      # Network-related controls
      # Disable public access but allow Trusted Azure Services exception
      publicNetworkAccess = "Disabled"
      networkAcls = {
        defaultAction = "Allow"
      }

      # Enable VNet injection for Agents
      networkInjections = [
        {
          scenario                   = "agent"
          subnetArmId                = azurerm_subnet.subnet_agent.id
          useMicrosoftManagedNetwork = false
        }
      ]
    }
  }
}

## Create a deployment for the model in the AI Foundry resource
##
resource "azurerm_cognitive_deployment" "aifoundry_deployment_gpt_4o" {
  depends_on = [
    azapi_resource.ai_foundry
  ]

  name                 = var.model_name
  cognitive_account_id = azapi_resource.ai_foundry.id

  sku {
    name     = var.model_sku_name
    capacity = var.model_capacity
  }

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }
}

########## Create Private DNS Zones, Links, and Private Endpoints
##########

## Create required Private DNS Zones
##
resource "azurerm_private_dns_zone" "plz_cognitive_services" {
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "plz_ai_services" {
  name                = "privatelink.services.ai.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "plz_openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

## Create Private DNS Zone Links to link the Private DNS Zones to the virtual network
##
resource "azurerm_private_dns_zone_virtual_network_link" "plz_cognitive_services_link" {
  depends_on = [
    azurerm_private_dns_zone.plz_cognitive_services,
    azurerm_virtual_network.vnet
  ]
  name                  = "cogsvc-${random_string.unique.result}-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.plz_cognitive_services.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_ai_services_link" {
  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_cognitive_services_link,
    azurerm_private_dns_zone.plz_ai_services,
    azurerm_virtual_network.vnet
  ]
  name                  = "aiservices-${random_string.unique.result}-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.plz_ai_services.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_openai_link" {
  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_ai_services_link,
    azurerm_private_dns_zone.plz_openai,
    azurerm_virtual_network.vnet
  ]
  name                  = "openai-${random_string.unique.result}-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.plz_openai.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

## Create Private Endpoint for AI Foundry
##
resource "azurerm_private_endpoint" "pe_aifoundry" {
  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_cognitive_services_link,
    azurerm_private_dns_zone_virtual_network_link.plz_ai_services_link,
    azurerm_private_dns_zone_virtual_network_link.plz_openai_link,
    azapi_resource.ai_foundry,
    azurerm_virtual_network.vnet
  ]

  name                = "${azapi_resource.ai_foundry.name}-private-endpoint"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.subnet_pe.id

  private_service_connection {
    name                           = "${azapi_resource.ai_foundry.name}-private-link-service-connection"
    private_connection_resource_id = azapi_resource.ai_foundry.id
    subresource_names = [
      "account"
    ]
    is_manual_connection = false
  }

  private_dns_zone_group {
    name = "${azapi_resource.ai_foundry.name}-dns-config"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.plz_cognitive_services.id,
      azurerm_private_dns_zone.plz_ai_services.id,
      azurerm_private_dns_zone.plz_openai.id
    ]
  }
}

########## Create the AI Foundry project and capability host
##########

## Create AI Foundry project
##
resource "azapi_resource" "ai_foundry_project" {
  depends_on = [
    azapi_resource.ai_foundry,
    azurerm_private_endpoint.pe_aifoundry
  ]

  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = "project${random_string.unique.result}"
  parent_id                 = azapi_resource.ai_foundry.id
  location                  = var.location
  schema_validation_enabled = false

  body = {
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }

    properties = {
      displayName = "project"
      description = "A project for the AI Foundry account with network secured basic Agent"
    }
  }

  response_export_values = [
    "identity.principalId",
    "properties.internalId"
  ]
}

## Create the AI Foundry project capability host (basic agent - no BYO connections)
##
resource "azapi_resource" "ai_foundry_project_capability_host" {
  depends_on = [
    azapi_resource.ai_foundry_project
  ]
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "caphostproj"
  parent_id                 = azapi_resource.ai_foundry_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind = "Agents"
    }
  }
}

########## Optional: Azure Container Registry with Private Endpoint
##########

resource "azurerm_container_registry" "acr" {
  count = var.enable_container_registry ? 1 : 0

  name                          = "acr${random_string.unique.result}"
  resource_group_name           = azurerm_resource_group.rg.name
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
  count = var.enable_container_registry ? 1 : 0

  name                = "privatelink.azurecr.io"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_acr_link" {
  count = var.enable_container_registry ? 1 : 0

  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_openai_link
  ]

  name                  = "acr-${random_string.unique.result}-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.plz_acr[0].name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

resource "azurerm_private_endpoint" "pe_acr" {
  count = var.enable_container_registry ? 1 : 0

  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.plz_acr_link
  ]

  name                = "acr${random_string.unique.result}-private-endpoint"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.subnet_pe.id

  private_service_connection {
    name                           = "acr${random_string.unique.result}-private-link-service-connection"
    private_connection_resource_id = azurerm_container_registry.acr[0].id
    subresource_names = [
      "registry"
    ]
    is_manual_connection = false
  }

  private_dns_zone_group {
    name = "acr${random_string.unique.result}-dns-config"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.plz_acr[0].id
    ]
  }
}

## Grant the project identity AcrPull on the container registry
##
resource "azurerm_role_assignment" "acr_pull_project" {
  count = var.enable_container_registry ? 1 : 0

  depends_on = [
    azapi_resource.ai_foundry_project,
    azurerm_container_registry.acr
  ]

  scope                = azurerm_container_registry.acr[0].id
  role_definition_name = "AcrPull"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId
}

########## Destroy-time resources
##########

## AI Foundry account purger to avoid InUseSubnetCannotBeDeleted-lock caused by the agent subnet delegation.
## The purge action (only executed during destroy) purges the AI Foundry account removing
## /subnets/snet-agent/serviceAssociationLinks/legionservicelink so the agent subnet can be properly removed.

resource "azapi_resource_action" "purge_ai_foundry" {
  method      = "DELETE"
  resource_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.CognitiveServices/locations/${azurerm_resource_group.rg.location}/resourceGroups/${azurerm_resource_group.rg.name}/deletedAccounts/aifoundry${random_string.unique.result}"
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  when        = "destroy"

  depends_on = [time_sleep.purge_ai_foundry_cooldown]
}

resource "time_sleep" "purge_ai_foundry_cooldown" {
  destroy_duration = "900s" # 10-15m is enough time to let the backend remove the serviceAssociationLinks

  depends_on = [azurerm_subnet.subnet_agent]
}
