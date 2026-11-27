terraform {
  # 1.11 or later: ephemeral variables and write-only attributes keep keys and secrets out of state.
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
  }
}
