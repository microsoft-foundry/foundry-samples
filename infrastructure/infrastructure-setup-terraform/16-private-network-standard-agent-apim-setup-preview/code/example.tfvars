# Example configuration for private network standard agent with API Management

# Azure region
location = "eastus"

# AI Foundry configuration
ai_services_name_prefix = "foundry"
project_name            = "private-apim-agent-project"

# Network configuration
vnet_address_space              = ["10.0.0.0/16"]
subnet_private_endpoints_prefix = "10.0.1.0/24"
subnet_apim_prefix              = "10.0.2.0/24"

# API Management configuration
apim_sku             = "Developer" # Use Developer for testing, Premium for production
apim_publisher_name  = "AI Foundry Publisher"
apim_publisher_email = "admin@example.com"

# Model configuration
model_name     = "gpt-4.1"
model_version  = "2025-04-14"
model_capacity = 40

# IMPORTANT NOTES:
# 1. API Management deployment can take 30-45 minutes
# 2. APIM with Internal VNet requires additional DNS configuration
# 3. Additional APIM policies and configurations need to be set up manually or with additional Terraform resources
# 4. Consider using Application Gateway if you need external access to internal APIM
