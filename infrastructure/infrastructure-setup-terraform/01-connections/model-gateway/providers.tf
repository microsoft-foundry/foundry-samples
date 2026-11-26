provider "azapi" {
  # The connection is created in the project's subscription.
  subscription_id = split("/", var.project_resource_id)[2]
}
