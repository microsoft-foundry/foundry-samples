# An existing resource group stays outside this sample's destroy lifecycle.
data "azurerm_resource_group" "existing" {
  count = local.create_rg ? 0 : 1
  name  = var.existing_resource_group_name
}

resource "azurerm_resource_group" "rg" {
  count    = local.create_rg ? 1 : 0
  name     = "rg-${var.name_prefix}-${local.random_suffix}"
  location = var.location
  tags     = local.common_tags
}

moved {
  from = azurerm_resource_group.rg
  to   = azurerm_resource_group.rg[0]
}
