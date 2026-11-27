########## AI Gateway layer
##########
## A private hub Foundry account (public access off) that hosts the model, an AI
## Gateway that reaches it privately through a dedicated VNet subnet, and the
## connection that lets the agent's project use the model.
##
## AI Gateway networking today: OUTBOUND can be private (backend.subnet); INBOUND
## is always public (no gateway private endpoint yet). The agent's model calls are
## made by the project's data proxy in the agent subnet and reach the gateway's
## public endpoint with the runtime key; the gateway then reaches the hub privately.

## Subnet dedicated to the gateway's outbound routing. Must be delegated to
## Microsoft.App/environments and have an NSG allowing outbound 443 to Storage
## and AzureKeyVault (the gateway's subnet checks require both rules).
##
resource "azurerm_network_security_group" "gateway" {
  name                = "nsg-${local.gateway_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
}

# Standalone rules (not inline blocks), so Terraform manages only these two and
# doesn't fight rules that Azure Policy or the platform adds to the NSG.
resource "azurerm_network_security_rule" "gateway_storage_outbound" {
  name                        = "AllowStorageOutbound"
  resource_group_name         = azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.gateway.name
  priority                    = 100
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "Storage"
}

resource "azurerm_network_security_rule" "gateway_keyvault_outbound" {
  name                        = "AllowKeyVaultOutbound"
  resource_group_name         = azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.gateway.name
  priority                    = 110
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "AzureKeyVault"
}

resource "azurerm_subnet" "gateway" {
  name                 = "snet-aigw"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.gateway_subnet_address_prefix]

  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }

  # Serialize VNet writes after the foundation's private endpoints.
  depends_on = [azurerm_private_endpoint.foundry]
}

resource "azurerm_subnet_network_security_group_association" "gateway" {
  subnet_id                 = azurerm_subnet.gateway.id
  network_security_group_id = azurerm_network_security_group.gateway.id

  # The gateway's subnet checks require both outbound rules before it joins the subnet.
  depends_on = [
    azurerm_network_security_rule.gateway_storage_outbound,
    azurerm_network_security_rule.gateway_keyvault_outbound,
  ]
}

## On destroy, give the platform time to release the subnet after the gateway is deleted.
resource "time_sleep" "gateway_subnet_release" {
  destroy_duration = "300s"
  depends_on       = [azurerm_subnet_network_security_group_association.gateway]
}

## Private hub Foundry account + model: reachable only through its private endpoint.
##
resource "azapi_resource" "hub_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.hub_account_name
  parent_id = azurerm_resource_group.rg.id
  location  = var.location

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = false
      customSubDomainName    = local.hub_account_name
      publicNetworkAccess    = "Disabled"
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Deny"
        bypass              = "AzureServices"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }

  response_export_values = ["properties.endpoint"]

  depends_on = [azapi_resource_action.purge_hub]
}

resource "azapi_resource" "hub_model" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.model_name
  parent_id = azapi_resource.hub_account.id

  body = {
    sku = {
      name     = var.model_sku_name
      capacity = var.model_capacity
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

## The hub's private endpoint reuses the Foundry DNS zones linked to the VNet, so the
## integrated gateway resolves the hub's normal host name to a private IP.
resource "azurerm_private_endpoint" "hub" {
  name                = "${local.hub_account_name}-pe"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "${local.hub_account_name}-psc"
    private_connection_resource_id = azapi_resource.hub_account.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = local.foundry_dns_zone_ids
  }

  # After the model deployment (a deployment PUT briefly leaves the account in a
  # non-terminal state) and after the other VNet writes.
  depends_on = [
    azapi_resource.hub_model,
    azurerm_subnet_network_security_group_association.gateway,
  ]
}

## The AI Gateway: same shared module as the public hub, plus backend_subnet_id.
##
module "ai_gateway" {
  source = "../../../../01-connections/ai-gateway-tier/modules/ai-gateway"

  name              = local.gateway_name
  location          = var.location
  resource_group_id = azurerm_resource_group.rg.id
  backend_subnet_id = azurerm_subnet.gateway.id

  foundry_account_id       = azapi_resource.hub_account.id
  foundry_account_endpoint = azapi_resource.hub_account.output.properties.endpoint
  model_deployment_id      = azapi_resource.hub_model.id
  model_deployment_name    = azapi_resource.hub_model.name
  model_version            = var.model_version
  tokens_per_minute        = var.tokens_per_minute
  assign_foundry_user_role = var.assign_foundry_user_role

  depends_on = [
    azurerm_private_endpoint.hub,
    time_sleep.gateway_subnet_release,
  ]
}

## Read the gateway key at apply time (ephemeral: never stored in state) and connect
## the agent's project to the gateway.
##
ephemeral "azapi_resource_action" "gateway_key" {
  type                   = "Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview"
  resource_id            = module.ai_gateway.api_key_id
  action                 = "listSecrets"
  method                 = "POST"
  response_export_values = ["primaryKey"]
}

module "connection" {
  source = "../../../../01-connections/ai-gateway-tier/modules/ai-gateway-connection"

  project_id         = azapi_resource.project.id
  connection_name    = var.connection_name
  base_url           = module.ai_gateway.models_base_url
  api_key            = ephemeral.azapi_resource_action.gateway_key.output.primaryKey
  credential_version = var.credential_version
  model_name         = module.ai_gateway.alias_name
  model_version      = var.model_version
  auth_header_name   = var.auth_header_name
  auth_header_format = var.auth_header_format

  depends_on = [azapi_resource.capability_host]
}
