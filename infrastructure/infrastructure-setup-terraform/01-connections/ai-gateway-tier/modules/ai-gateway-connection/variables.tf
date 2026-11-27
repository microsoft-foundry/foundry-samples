variable "project_id" {
  description = "Resource ID of the Foundry project that gets the connection (.../accounts/<account>/projects/<project>)."
  type        = string
}

variable "connection_name" {
  description = "Connection name. Agents reference the model as <connection_name>/<model_name>."
  type        = string
  default     = "ai-gateway"
}

variable "base_url" {
  description = "Gateway OpenAI v1 base URL: https://<gateway-hostname>/default/models/openai/v1."
  type        = string
}

variable "api_key" {
  description = "Gateway runtime API key. Ephemeral and write-only: it is sent to Azure but never stored in Terraform state or plan files."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "credential_version" {
  description = "Change this value after rotating the gateway key to recreate the connection with the new key (the key itself is write-only, so Terraform can't detect the change)."
  type        = string
  default     = "1"
}

variable "model_name" {
  description = "Callable model name on the gateway (the alias)."
  type        = string
}

variable "model_version" {
  description = "Model version shown in the Foundry portal."
  type        = string
}

variable "model_format" {
  description = "Model format shown in the Foundry portal."
  type        = string
  default     = "OpenAI"
}

variable "auth_header_name" {
  description = "Header that carries the gateway key. Authorization (Bearer format) is the form the AI Gateway migration guide documents; never also send api-key (the gateway returns 400 when both are present)."
  type        = string
  default     = "Authorization"
}

variable "auth_header_format" {
  description = "Header value template. {api_key} is replaced with the key."
  type        = string
  default     = "Bearer {api_key}"
}

variable "is_shared_to_all" {
  description = "Share the connection with every project on the account, which surfaces it in the Foundry portal \"Admin-connected models\" picker."
  type        = bool
  default     = true
}
