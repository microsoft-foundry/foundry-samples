# Setup providers
provider "azapi" {
}

provider "azurerm" {
  features {}
  storage_use_azuread = true

  resource_providers_to_register = [
    "Microsoft.KeyVault",
    "Microsoft.CognitiveServices",
    "Microsoft.Storage",
    "Microsoft.Search",
    "Microsoft.Network",
    "Microsoft.App",
    "Microsoft.ContainerService",
  ]
}
