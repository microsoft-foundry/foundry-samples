########## Create infrastructure resources
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
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Create a virtual network
resource "azurerm_virtual_network" "vnet" {
  name                = var.virtual_network_name
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = [var.virtual_network_address_space]
}

## Create a subnet for private endpoints
resource "azurerm_subnet" "pe_subnet" {
  name                 = var.pe_subnet_name
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.pe_subnet_address_prefix]
}

## Create AI Foundry account with public network access disabled
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = var.ai_foundry_name
  location  = coalesce(var.foundry_location, azurerm_resource_group.rg.location)
  parent_id = azurerm_resource_group.rg.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = format("%s%s", var.ai_foundry_name, random_string.unique.result)
      disableLocalAuth       = false
      publicNetworkAccess    = "Disabled"
    }
  }
}

## Create private DNS zones
resource "azurerm_private_dns_zone" "ai_services" {
  name                = "privatelink.services.ai.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone" "cognitive_services" {
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

## Link DNS zones to VNet
resource "azurerm_private_dns_zone_virtual_network_link" "ai_services_link" {
  name                  = "aiServices-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.ai_services.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "openai_link" {
  name                  = "aiServicesOpenAI-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "cognitive_services_link" {
  name                  = "aiServicesCognitiveServices-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.cognitive_services.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

## Create private endpoint for AI Foundry
resource "azurerm_private_endpoint" "ai_foundry_pe" {
  name                = "${var.ai_foundry_name}-pe"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.pe_subnet.id

  private_service_connection {
    name                           = "${var.ai_foundry_name}-psc"
    private_connection_resource_id = azapi_resource.ai_foundry.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name = "${var.ai_foundry_name}-dns-group"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.ai_services.id,
      azurerm_private_dns_zone.openai.id,
      azurerm_private_dns_zone.cognitive_services.id
    ]
  }

  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.ai_services_link,
    azurerm_private_dns_zone_virtual_network_link.openai_link,
    azurerm_private_dns_zone_virtual_network_link.cognitive_services_link
  ]
}

## Create AI Foundry project
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = coalesce(var.ai_project_name, "${var.ai_foundry_name}-proj")
  location  = azapi_resource.ai_foundry.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {}
  }

  depends_on = [azurerm_private_endpoint.ai_foundry_pe]
}

## Deploy model
resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.model_name
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      capacity = 1
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
