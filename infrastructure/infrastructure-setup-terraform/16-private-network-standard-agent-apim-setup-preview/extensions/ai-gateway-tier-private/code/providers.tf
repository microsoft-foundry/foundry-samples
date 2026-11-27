provider "azapi" {
  subscription_id = var.subscription_id
}

provider "azurerm" {
  subscription_id = var.subscription_id

  features {
    # The Storage account has no public endpoint. Skip the provider's optional data-plane
    # reads (queue properties, static website), which this sample doesn't use, so plan and
    # apply work from outside the VNet.
    storage {
      data_plane_available = false
    }
  }

  storage_use_azuread = true
}
