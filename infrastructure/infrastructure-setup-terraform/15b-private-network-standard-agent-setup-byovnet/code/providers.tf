# Setup providers
provider "azapi" {
}

provider "azapi" {
  alias           = "workload_subscription"
  subscription_id = var.subscription_id_resources
}

provider "azapi" {
  alias           = "infra_subscription"
  subscription_id = var.subscription_id_infra
}

provider "azurerm" {
  features {}
  storage_use_azuread = true
}

provider "azurerm" {
  alias           = "workload_subscription"
  subscription_id = var.subscription_id_resources
  features {}
  storage_use_azuread = true
}

provider "azurerm" {
  alias           = "infra_subscription"
  subscription_id = var.subscription_id_infra
  features {}
  storage_use_azuread = true
}
