terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
  }
  # >= 1.11 for the ephemeral key read and the write-only connection credential.
  required_version = ">= 1.11.0, < 2.0.0"

  # Uncomment to store state in Azure Storage
  # backend "azurerm" {}
}
