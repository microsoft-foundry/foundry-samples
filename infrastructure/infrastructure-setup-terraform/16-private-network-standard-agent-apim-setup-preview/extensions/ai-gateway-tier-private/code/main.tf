data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  suffix               = random_string.suffix.result
  account_name         = "${var.name_prefix}${local.suffix}"
  hub_account_name     = "${var.name_prefix}hub${local.suffix}"
  gateway_name         = "${var.name_prefix}-${local.suffix}"
  storage_account_name = "${var.name_prefix}${local.suffix}st"
  allow_client_ips     = length(var.foundry_allowed_ip_ranges) > 0
  public_access        = var.foundry_public_network_access_enabled || local.allow_client_ips

  # The project's internal ID formatted as a GUID, used by the Storage Blob Data Owner condition.
  project_internal_id = azapi_resource.project.output.properties.internalId
  project_id_guid     = "${substr(local.project_internal_id, 0, 8)}-${substr(local.project_internal_id, 8, 4)}-${substr(local.project_internal_id, 12, 4)}-${substr(local.project_internal_id, 16, 4)}-${substr(local.project_internal_id, 20, 12)}"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.name_prefix}-${local.suffix}"
  location = var.location
}
