provider "azurerm" {
  features {}
  subscription_id = var.subscription_id

  # Assigning policies doesn't need new resource providers. Skipping automatic
  # registration lets a Resource Policy Contributor run this without extra rights.
  resource_provider_registrations = "none"
}
