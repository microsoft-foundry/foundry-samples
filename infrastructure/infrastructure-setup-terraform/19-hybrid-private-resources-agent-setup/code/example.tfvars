# Example configuration for hybrid private resources agent setup

# Azure region

# AI Foundry configuration
ai_services_name_prefix = "foundry"
project_name            = "hybrid-agent-project"

# Network configuration
vnet_address_space    = ["10.0.0.0/16"]
subnet_address_prefix = "10.0.1.0/24"

# Hybrid configuration - mix of public and private
# Scenario: Development setup with some public access for easier testing
ai_foundry_public_access = "Enabled" # Public for easy access
storage_public_access    = false     # Private for data security
search_public_access     = true      # Public for development
cosmos_public_access     = true      # Public for development

# For production, you might flip these:
# ai_foundry_public_access = "Disabled"
# storage_public_access    = false
# search_public_access     = false
# cosmos_public_access     = false

# Model configuration
model_name     = "gpt-4.1"
model_version  = "2025-04-14"
model_capacity = 40
