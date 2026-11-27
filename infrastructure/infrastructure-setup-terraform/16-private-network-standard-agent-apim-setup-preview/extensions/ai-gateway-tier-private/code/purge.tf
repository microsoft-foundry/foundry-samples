## Foundry accounts are soft-deleted. These actions run only during destroy, after
## each account is deleted (the accounts depend on them), and purge them.
##
## The agent account also needs a cooldown before purge: the platform takes
## 10-15 minutes to remove the agent subnet's service association link, and the
## subnet can't be deleted until it's gone (InUseSubnetCannotBeDeleted).

resource "time_sleep" "purge_foundry_cooldown" {
  destroy_duration = "900s"
  depends_on       = [azurerm_subnet.agent]
}

resource "azapi_resource_action" "purge_foundry" {
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  resource_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.CognitiveServices/locations/${var.location}/resourceGroups/${azurerm_resource_group.rg.name}/deletedAccounts/${local.account_name}"
  method      = "DELETE"
  when        = "destroy"

  depends_on = [time_sleep.purge_foundry_cooldown]
}

resource "azapi_resource_action" "purge_hub" {
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  resource_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.CognitiveServices/locations/${var.location}/resourceGroups/${azurerm_resource_group.rg.name}/deletedAccounts/${local.hub_account_name}"
  method      = "DELETE"
  when        = "destroy"
}
