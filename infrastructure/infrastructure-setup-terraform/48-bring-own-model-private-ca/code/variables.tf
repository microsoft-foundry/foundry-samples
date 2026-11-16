# ============================================================================
# Subscription, tenant, location
# ============================================================================

variable "subscription_id" {
  description = "Subscription ID that hosts both the hub and spoke VNets and all resources in this sample."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant ID. Required explicitly because the azapi provider does not infer it from the subscription."
  type        = string
}

variable "location" {
  description = "Azure region for all resources. Avoid uksouth for this sample: the account trustedCertificates property has a known silent-discard bug there. eastus2 and swedencentral are validated."
  type        = string
  default     = "eastus2"
}

variable "existing_resource_group_name" {
  description = "Existing resource group in the selected subscription. Leave empty to create a new group. An existing group is read-only to Terraform and is not deleted during destroy."
  type        = string
  default     = ""
  nullable    = false
}

variable "name_prefix" {
  description = "Short prefix for resource names. Kept short because APIM, Key Vault, and Foundry account names have length limits."
  type        = string
  default     = "byomca"
}

variable "foundry_public_network_access_enabled" {
  description = "Testing convenience: enable public network access to the Foundry agent account from all networks (Entra ID auth still required). Prefer foundry_allowed_ip_ranges. The data proxy, gateway, APIM, model, and private DNS stay private either way."
  type        = bool
  default     = false
}

variable "foundry_allowed_ip_ranges" {
  description = "Public IPv4 addresses or CIDR ranges (for example your client egress IP) allowed to reach the Foundry agent account. A non-empty list enables public network access restricted to these ranges; all other networks are denied."
  type        = list(string)
  default     = []
  nullable    = false
}

# ============================================================================
# Foundry model backend (the real model behind the gateway)
# ============================================================================

variable "foundry_model_name" {
  description = "OpenAI model deployed on the Foundry model account and exposed through the gateway alias."
  type        = string
  default     = "gpt-4.1"
}

variable "foundry_model_version" {
  description = "Version of the Foundry model deployment."
  type        = string
  default     = "2025-04-14"
}

variable "foundry_model_capacity" {
  description = "Capacity (thousands of tokens per minute) for the Foundry model deployment."
  type        = number
  default     = 40
}

# ============================================================================
# Networking: workload spoke (Foundry) and platform hub (gateway, model)
# ============================================================================

variable "spoke_vnet_address_space" {
  description = "Address space for the workload spoke VNet that hosts the VNet-injected Foundry account."
  type        = string
  default     = "172.24.0.0/16"
}

variable "agent_subnet_prefix" {
  description = "Spoke subnet delegated to Microsoft.App/environments. Injecting the Foundry account here provisions the agent runtime + single-tenant data proxy."
  type        = string
  default     = "172.24.1.0/24"
}

variable "spoke_pe_subnet_prefix" {
  description = "Spoke private-endpoint subnet (Foundry account, Storage, Cosmos, Search)."
  type        = string
  default     = "172.24.2.0/24"
}

variable "hub_vnet_address_space" {
  description = "Address space for the platform hub VNet that hosts the gateway, APIM, and model backend."
  type        = string
  default     = "172.25.0.0/16"
}

variable "hub_pe_subnet_prefix" {
  description = "Hub private-endpoint subnet (APIM gateway, Foundry model account)."
  type        = string
  default     = "172.25.1.0/24"
}

variable "appgw_subnet_prefix" {
  description = "Hub subnet dedicated to Application Gateway."
  type        = string
  default     = "172.25.2.0/24"
}

variable "appgw_private_ip" {
  description = "Static private frontend IP of the Application Gateway. Must be inside appgw_subnet_prefix. The gateway hostname resolves to this address from both VNets."
  type        = string
  default     = "172.25.2.10"
}

variable "apim_integration_subnet_prefix" {
  description = "Hub subnet for APIM Standard v2 outbound VNet integration (delegated to Microsoft.Web/serverFarms; /27 minimum). APIM reaches the private model endpoint through it."
  type        = string
  default     = "172.25.3.0/24"
}

# ============================================================================
# Gateway hostname behind private DNS
# ============================================================================

variable "custom_domain_zone" {
  description = "Private DNS zone for the gateway hostname. Internal-only (not publicly resolvable), owned by the hub and linked to both VNets. The gateway certificate's SAN must match <custom_domain_host>.<custom_domain_zone>."
  type        = string
  default     = "byomca.internal"
}

variable "custom_domain_host" {
  description = "Host label of the gateway hostname, prepended to custom_domain_zone."
  type        = string
  default     = "gateway"
}

# ============================================================================
# Private CA (generated for the sample; bring your own PKI in production)
# ============================================================================

variable "root_ca_common_name" {
  description = "Common name of the generated private root CA that signs the gateway certificate."
  type        = string
  default     = "Contoso Internal Root CA"
}

variable "root_ca_validity_hours" {
  description = "Validity of the generated private root CA, in hours."
  type        = number
  default     = 87600
}

variable "gateway_cert_validity_hours" {
  description = "Validity of the gateway TLS certificate issued by the private root CA, in hours."
  type        = number
  default     = 8760
}

# ============================================================================
# APIM
# ============================================================================

variable "apim_sku" {
  description = "APIM SKU. StandardV2 supports both the inbound private endpoint (Application Gateway -> APIM) and outbound VNet integration (APIM -> private model)."
  type        = string
  default     = "StandardV2_1"
}

variable "apim_publisher_name" {
  description = "APIM publisher organization name (required at create time)."
  type        = string
  default     = "Contoso Platform Team"
}

variable "apim_publisher_email" {
  description = "APIM publisher email (required at create time)."
  type        = string
  default     = "admin@contoso.example"
}

variable "apim_public_network_access_enabled" {
  description = "Whether APIM's gateway accepts public network access. The private test works either way because Application Gateway reaches APIM through its private endpoint; set false for a stricter private-only posture (requires the private endpoint to exist first)."
  type        = bool
  default     = true
}

variable "inference_api_version" {
  description = "Inference API version the Foundry ApiManagement connection sends to the gateway. Reasoning models (for example gpt-5.x) need 2025-04-01-preview or later."
  type        = string
  default     = "2024-10-21"
}
