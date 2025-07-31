# Configure the AzApi and AzureRM providers
terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.3.0"
    }

    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.26.0"
    }
  }
  required_version = ">= 1.8.3"
  # Uncomment to store state in Azure Storage
  # backend "azurerm" {}
}