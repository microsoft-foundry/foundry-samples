# Example terraform.tfvars file
# Copy this to terraform.tfvars and customize for your deployment

location                      = "westus3"
ai_foundry_name               = "foundrypnadisabled"
virtual_network_name          = "private-vnet"
virtual_network_address_space = "192.168.0.0/16"
pe_subnet_name                = "pe-subnet"
pe_subnet_address_prefix      = "192.168.0.0/24"
model_name                    = "gpt-4o"
model_version                 = "2024-08-06"
