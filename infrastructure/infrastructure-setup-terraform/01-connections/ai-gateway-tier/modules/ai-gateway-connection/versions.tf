terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
  }
  required_version = ">= 1.11.0, < 2.0.0"
}
