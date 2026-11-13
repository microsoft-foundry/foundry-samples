# Example configuration for customer-managed keys with user-assigned identity

# Azure region

# AI Foundry configuration
ai_foundry_name = "foundry-cmk-uai"
ai_project_name = null # Will default to {ai_foundry_name}-proj

# User-Assigned Identity configuration
create_user_assigned_identity = true
user_assigned_identity_name   = "foundry-cmk-uai"
# user_assigned_identity_resource_group = "my-existing-rg"  # If using existing UAI

# Model configuration
model_name     = "gpt-4o"
model_version  = "2024-08-06"
model_capacity = 40
# For CMK with agents, use System-Assigned Identity (example 31).
