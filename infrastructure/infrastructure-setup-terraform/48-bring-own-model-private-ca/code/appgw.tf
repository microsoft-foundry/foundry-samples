# ============================================================================
# Application Gateway (platform hub): the TLS front door on the gateway
# hostname behind private DNS.
#
# The private frontend serves the private-CA gateway certificate (leaf + root
# chain from Key Vault) on local.custom_domain_fqdn - the certificate the
# spoke data proxy validates - and forwards to APIM's default *.azure-api.net
# hostname, which resolves to the APIM private endpoint through the
# hub-linked privatelink.azure-api.net zone.
#
# Application Gateway v2 requires a public frontend IP unless the
# subscription opts into EnableApplicationGatewayNetworkIsolation. This sample
# avoids that subscription-wide registration: the public IP exists but has NO
# listener, so only the private frontend accepts traffic.
# ============================================================================

resource "azurerm_user_assigned_identity" "appgw" {
  name                = "id-${local.appgw_name}"
  location            = var.location
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

# Application Gateway reads the certificate (with private key) as a KV secret.
resource "azurerm_role_assignment" "kv_appgw_secrets_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.appgw.principal_id
}

resource "time_sleep" "wait_appgw_kv_rbac" {
  create_duration = "60s"
  depends_on      = [azurerm_role_assignment.kv_appgw_secrets_user]
}

resource "azurerm_public_ip" "appgw" {
  name                = "pip-${local.appgw_name}"
  location            = var.location
  resource_group_name = local.rg_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags
}

locals {
  appgw_apim_backend_fqdn = trimprefix(azurerm_api_management.apim.gateway_url, "https://")
}

resource "azurerm_application_gateway" "gateway" {
  name                = local.appgw_name
  location            = var.location
  resource_group_name = local.rg_name

  # Application Gateway otherwise polls Key Vault for new certificate versions
  # only every few hours. Tagging the version forces an update on rotation so
  # the new leaf is served promptly after a gateway certificate rotation.
  tags = merge(local.common_tags, {
    gatewayCertificateVersion = azurerm_key_vault_certificate.gateway.version
  })

  sku {
    name     = "Standard_v2"
    tier     = "Standard_v2"
    capacity = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.appgw.id]
  }

  ssl_policy {
    policy_type = "Predefined"
    policy_name = "AppGwSslPolicy20220101"
  }

  gateway_ip_configuration {
    name      = "gateway-ip"
    subnet_id = azurerm_subnet.appgw.id
  }

  frontend_ip_configuration {
    name                 = "public"
    public_ip_address_id = azurerm_public_ip.appgw.id
  }

  frontend_ip_configuration {
    name                          = "private"
    subnet_id                     = azurerm_subnet.appgw.id
    private_ip_address_allocation = "Static"
    private_ip_address            = var.appgw_private_ip
  }

  frontend_port {
    name = "https"
    port = 443
  }

  ssl_certificate {
    name                = local.gateway_cert_name
    key_vault_secret_id = azurerm_key_vault_certificate.gateway.versionless_secret_id
  }

  http_listener {
    name                           = "gateway-https"
    frontend_ip_configuration_name = "private"
    frontend_port_name             = "https"
    protocol                       = "Https"
    ssl_certificate_name           = local.gateway_cert_name
  }

  backend_address_pool {
    name  = "apim"
    fqdns = [local.appgw_apim_backend_fqdn]
  }

  # APIM returns 404 for paths without an API; any response up to 404 proves
  # the gateway is reachable.
  probe {
    name                                      = "apim"
    protocol                                  = "Https"
    path                                      = "/status-0123456789abcdef"
    interval                                  = 30
    timeout                                   = 30
    unhealthy_threshold                       = 3
    pick_host_name_from_backend_http_settings = true

    match {
      status_code = ["200-404"]
    }
  }

  backend_http_settings {
    name                                = "apim-https"
    cookie_based_affinity               = "Disabled"
    port                                = 443
    protocol                            = "Https"
    request_timeout                     = 120
    pick_host_name_from_backend_address = true
    probe_name                          = "apim"
  }

  request_routing_rule {
    name                       = "gateway-to-apim"
    priority                   = 100
    rule_type                  = "Basic"
    http_listener_name         = "gateway-https"
    backend_address_pool_name  = "apim"
    backend_http_settings_name = "apim-https"
  }

  depends_on = [
    time_sleep.wait_appgw_kv_rbac,
    azurerm_private_endpoint.apim,
    azurerm_private_dns_zone_virtual_network_link.hub,
  ]
}
