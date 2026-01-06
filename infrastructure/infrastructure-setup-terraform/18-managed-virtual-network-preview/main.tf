resource "random_id" "suffix" {
  byte_length = 4
}

data "azurerm_client_config" "current" {}

locals {
  resource_suffix = random_id.suffix.hex
  rg_name         = "${var.resource_group_name}-${local.resource_suffix}"
  foundry_name    = "${var.foundry_identifier}-${local.resource_suffix}"
  storage_name    = "st${local.resource_suffix}"
  aisearch_name   = "srch-${local.resource_suffix}"
  cosmos_name     = "cosmos-${local.resource_suffix}"
  keyvault_name   = "kv-${local.resource_suffix}"
}

resource "azurerm_resource_group" "main" {
  name     = local.rg_name
  location = var.location

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}
