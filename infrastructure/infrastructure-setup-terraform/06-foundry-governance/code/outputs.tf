output "scope" {
  description = "Scope the policies were assigned to."
  value       = var.resource_group_name == null ? data.azurerm_subscription.current.id : data.azurerm_resource_group.target[0].id
}

output "assignments" {
  description = "Policy assignments created, keyed by control."
  value = merge(
    { for k, a in azurerm_subscription_policy_assignment.this : k => { id = a.id, display_name = a.display_name } },
    { for k, a in azurerm_resource_group_policy_assignment.this : k => { id = a.id, display_name = a.display_name } },
  )
}
