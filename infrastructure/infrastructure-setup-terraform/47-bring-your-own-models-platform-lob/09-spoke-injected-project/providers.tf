provider "azurerm" {
  features {}
  subscription_id     = var.spoke_subscription_id
  tenant_id           = var.tenant_id
  storage_use_azuread = true
}

provider "azapi" {
  subscription_id = var.spoke_subscription_id
  tenant_id       = var.tenant_id
  use_cli         = true
}
