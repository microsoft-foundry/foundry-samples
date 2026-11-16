# ============================================================================
# Key Vault: gateway TLS certificate + private root CA trust anchor.
#
# * gateway_cert_name   - certificate imported from the private PKI (pki.tf):
#                         leaf + private key + root chain as PFX. Application
#                         Gateway serves it on the gateway hostname.
# * root_ca_secret_name - SECRET holding the root CA PUBLIC PEM. The Foundry
#                         account's trustedCertificateSources references it;
#                         trusted certificates resolve via the KV *secrets* API.
#
# Key Vault keeps public network access so the deploying client and Application
# Gateway can reach it; access is governed by Entra ID RBAC.
# ============================================================================

resource "azurerm_key_vault" "kv" {
  name                       = local.keyvault_name
  location                   = var.location
  resource_group_name        = local.rg_name
  tenant_id                  = local.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = local.common_tags
}

# The deploying identity needs data-plane rights to import the certificate.
resource "azurerm_role_assignment" "kv_admin_deployer" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Let RBAC propagate before data-plane calls.
resource "time_sleep" "wait_kv_rbac" {
  create_duration = "60s"
  depends_on      = [azurerm_role_assignment.kv_admin_deployer]
}

# ---- Gateway TLS certificate (leaf + chain), served by Application Gateway ----
resource "azurerm_key_vault_certificate" "gateway" {
  name         = local.gateway_cert_name
  key_vault_id = azurerm_key_vault.kv.id

  certificate {
    contents = pkcs12_from_pem.gateway.result
    password = random_password.gateway_pfx.result
  }

  depends_on = [time_sleep.wait_kv_rbac]
}

# ---- Private root CA PUBLIC PEM: the Foundry trust anchor ----
resource "azurerm_key_vault_secret" "root_ca_pem" {
  name         = local.root_ca_secret_name
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "application/x-pem-file"
  value        = tls_self_signed_cert.root_ca.cert_pem

  depends_on = [time_sleep.wait_kv_rbac]
}

# ---- Foundry account MI reads the trust-anchor PEM SECRET ----
# The trust bundle is resolved through the Key Vault secrets API using the
# account MI (getSecret) when the capability host is created.
resource "azurerm_role_assignment" "kv_foundry_secrets_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azapi_resource.foundry_agent_account.identity[0].principal_id
}

resource "time_sleep" "wait_foundry_kv_rbac" {
  create_duration = "60s"
  depends_on      = [azurerm_role_assignment.kv_foundry_secrets_user]
}
