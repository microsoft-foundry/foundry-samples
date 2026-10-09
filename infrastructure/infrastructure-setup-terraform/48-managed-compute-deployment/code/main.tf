locals {
  foundry_account_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/${var.foundry_account_name}"
  deployment_name    = "${var.deployment_name_prefix}-${random_string.deployment_suffix.result}"
}

resource "random_string" "deployment_suffix" {
  length  = 6
  upper   = false
  lower   = true
  numeric = true
  special = false
}

resource "azapi_resource" "managed_compute_deployment" {
  type                      = "Microsoft.CognitiveServices/accounts/managedComputeDeployments@2026-07-15-preview"
  name                      = local.deployment_name
  parent_id                 = local.foundry_account_id
  schema_validation_enabled = false

  body = {
    sku = {
      name     = "GlobalManagedCompute"
      capacity = var.capacity
    }
    properties = {
      model                = var.model_id
      deploymentTemplate   = var.deployment_template_id
      acceleratorType      = var.accelerator_type
      versionUpgradeOption = var.version_upgrade_option
    }
  }

  timeouts {
    create = "60m"
    update = "60m"
    delete = "30m"
  }
}
