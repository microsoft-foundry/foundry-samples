# Example configuration for private network standard agent with UAI

# Azure region

# AI Foundry configuration
ai_services_name_prefix = "foundry"
project_name            = "private-uai-agent-project"

# User-Assigned Identity configuration
create_user_assigned_identity = true
user_assigned_identity_name   = "foundry-private-uai"
# user_assigned_identity_resource_group = "my-existing-rg"  # If using existing UAI

# Network configuration
vnet_address_space    = ["10.0.0.0/16"]
subnet_address_prefix = "10.0.1.0/24"

# Model configuration
model_name     = "gpt-4.1"
model_version  = "2025-04-14"
model_capacity = 40
