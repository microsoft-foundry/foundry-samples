terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }
  # >= 1.11 for write-only attributes and ephemeral values used by the connection.
  required_version = ">= 1.11.0, < 2.0.0"

  # Uncomment to store state in Azure Storage
  # backend "azurerm" {}
}
