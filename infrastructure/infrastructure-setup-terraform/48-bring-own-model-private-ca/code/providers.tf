# Single subscription for the whole sample. The hub and spoke are separate VNets
# connected by peering; sample 47 shows the cross-subscription variant of the
# platform/workload split.
#
# The azapi provider does not auto-detect the tenant from the subscription the
# way azurerm does, so tenant_id is supplied explicitly.

provider "azurerm" {
  subscription_id = var.subscription_id

  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }

  storage_use_azuread = true
}

provider "azapi" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  use_cli         = true
}
