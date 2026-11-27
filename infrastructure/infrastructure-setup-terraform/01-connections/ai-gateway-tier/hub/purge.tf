## Foundry accounts are soft-deleted. This action runs only during destroy, after
## the account is deleted (the account depends on it), and purges it so the name
## and model quota are released immediately.
##
resource "azapi_resource_action" "purge_account" {
  count = var.purge_on_destroy ? 1 : 0

  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  resource_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.CognitiveServices/locations/${var.location}/resourceGroups/${local.resource_group_name}/deletedAccounts/${local.account_name}"
  method      = "DELETE"
  when        = "destroy"
}
