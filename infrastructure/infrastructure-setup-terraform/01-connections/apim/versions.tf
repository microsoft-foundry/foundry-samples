terraform {
  # 1.11 or later: ephemeral values and write-only attributes keep the APIM subscription key out of state.
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
  }
}
