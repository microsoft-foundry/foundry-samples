variable "subscription_id" {
  description = "Subscription of the spoke project."
  type        = string
}

variable "project_resource_id" {
  description = "Resource ID of the EXISTING spoke project (.../accounts/<account>/projects/<project>), for example the ai_project_id output of ../../../41-standard-agent-setup."
  type        = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.CognitiveServices/accounts/[^/]+/projects/[^/]+$", var.project_resource_id))
    error_message = "project_resource_id must be a Foundry project resource ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>."
  }
}

variable "gateway_id" {
  description = "Resource ID of the hub AI Gateway: the hub's gateway_id output."
  type        = string

  validation {
    condition     = can(regex("(?i)/providers/Microsoft\\.ApiManagement/aigateways/[^/]+$", var.gateway_id))
    error_message = "gateway_id must be a Microsoft.ApiManagement/aigateways resource ID."
  }
}

variable "api_key_name" {
  description = "Runtime API key on the gateway to use: the hub's api_key_name output. Read with listSecrets at apply time; never stored in state."
  type        = string
  default     = "foundry-connection"
}

variable "credential_version" {
  description = "Bump after rotating the gateway key to recreate the connection with the new key."
  type        = string
  default     = "1"
}

variable "model_name" {
  description = "Callable model name on the gateway: the hub's model_name output."
  type        = string
  default     = "gpt-5.4"
}

variable "model_version" {
  description = "Model version: the hub's model_version output."
  type        = string
  default     = "2026-03-05"
}

variable "connection_name" {
  description = "Connection name. Agents reference the model as <connection_name>/<model_name>."
  type        = string
  default     = "ai-gateway"
}

variable "is_shared_to_all" {
  description = "Surface the connection in the Foundry portal \"Admin-connected models\" picker for every project on the account."
  type        = bool
  default     = true
}

variable "auth_header_name" {
  description = "Header the connection uses to send the gateway key. Authorization (Bearer format) is the form the AI Gateway migration guide documents; never also send api-key (the gateway returns 400 when both are present)."
  type        = string
  default     = "Authorization"
}

variable "auth_header_format" {
  description = "Header value template; {api_key} is replaced with the gateway key."
  type        = string
  default     = "Bearer {api_key}"
}
