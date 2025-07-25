# Setup providers
provider "azapi" {
}

provider "azurerm" {
  features {}
  storage_use_azuread = true
  subscription_id = "562da9fc-fd6e-4f24-a6aa-99827a7f6f91"
}