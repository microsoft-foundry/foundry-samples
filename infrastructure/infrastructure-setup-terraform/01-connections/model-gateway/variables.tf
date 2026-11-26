variable "project_resource_id" {
  description = "Resource ID of the Foundry project that gets the connection: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>."
  type        = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.CognitiveServices/accounts/[^/]+/projects/[^/]+$", var.project_resource_id))
    error_message = "project_resource_id must be a Foundry project resource ID: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>."
  }
}

variable "target_url" {
  description = "Base URL of the model gateway or provider, for example https://api.openai.com or https://<resource>.openai.azure.com/openai/v1."
  type        = string
}

variable "gateway_name" {
  description = "Gateway name used to generate the connection name when connection_name is empty."
  type        = string
  default     = "example-gateway"
}

variable "connection_name" {
  description = "Connection name. Agents reference a model as <connection_name>/<model-name>. Leave empty to use modelgateway-<gateway_name>-comprehensive."
  type        = string
  default     = ""
}

variable "auth_type" {
  description = "How the connection authenticates to the gateway: ApiKey, or OAuth2 with client credentials."
  type        = string
  default     = "ApiKey"

  validation {
    condition     = contains(["ApiKey", "OAuth2"], var.auth_type)
    error_message = "auth_type must be ApiKey or OAuth2."
  }
}

variable "is_shared_to_all" {
  description = "Share the connection with all users of the project. The service stores false on a project connection, whatever value is sent."
  type        = bool
  default     = false
}

variable "api_key" {
  description = "Gateway API key, for ApiKey authentication. Set it with the TF_VAR_api_key environment variable. It's sent as a write-only value and isn't stored in state or plan files."
  type        = string
  default     = null
  sensitive   = true
  ephemeral   = true

  validation {
    condition     = var.auth_type != "ApiKey" || try(length(var.api_key) > 0, false)
    error_message = "api_key is required when auth_type is ApiKey."
  }
}

variable "client_id" {
  description = "Client ID, for OAuth2 authentication."
  type        = string
  default     = ""
}

variable "client_secret" {
  description = "Client secret, for OAuth2 authentication. Set it with the TF_VAR_client_secret environment variable. It's sent as a write-only value and isn't stored in state or plan files."
  type        = string
  default     = null
  sensitive   = true
  ephemeral   = true

  validation {
    condition     = var.auth_type != "OAuth2" || try(length(var.client_secret) > 0, false)
    error_message = "client_secret is required when auth_type is OAuth2."
  }
}

variable "token_url" {
  description = "Token endpoint, for OAuth2 authentication."
  type        = string
  default     = ""
}

variable "scopes" {
  description = "Scopes to request, for OAuth2 authentication."
  type        = list(string)
  default     = []
}

variable "credential_version" {
  description = "Change this value after you rotate the API key or client secret, then apply to send the new value. Terraform can't detect the change because the value isn't stored, so it replaces the connection."
  type        = string
  default     = "1"
}

variable "deployment_in_path" {
  description = "true if the gateway expects the deployment name in the URL path; false if it expects the model name in the request body."
  type        = bool
  default     = false
}

variable "inference_api_version" {
  description = "api-version query value for inference calls, such as chat completions. Leave empty if the gateway doesn't need one."
  type        = string
  default     = ""
}

variable "upstream_surface" {
  description = "Set to responses to send Responses API requests upstream. Leave empty to keep the existing routing."
  type        = string
  default     = ""

  validation {
    condition     = contains(["", "responses"], var.upstream_surface)
    error_message = "upstream_surface must be empty or responses."
  }
}

variable "deployment_api_version" {
  description = "api-version query value for the list and get calls that dynamic discovery makes. Leave empty if the gateway doesn't need one."
  type        = string
  default     = ""
}

variable "model_discovery" {
  description = "Endpoints for listing and getting models, to discover models dynamically. Set this or static_models, not both."
  type = object({
    list_models_endpoint = string
    get_model_endpoint   = string
    deployment_provider  = string
  })
  default = null

  validation {
    condition     = var.model_discovery == null || try(alltrue([for v in values(var.model_discovery) : v != ""]), false)
    error_message = "model_discovery needs list_models_endpoint, get_model_endpoint, and deployment_provider."
  }
}

variable "static_models" {
  description = "Models that the connection exposes. Set this or model_discovery, not both."
  type = list(object({
    name = string
    properties = object({
      model = object({
        name    = string
        version = optional(string)
        format  = string
      })
    })
  }))
  default = []
}

variable "custom_headers" {
  description = "Extra HTTP headers to send with every request. Don't put secrets here: the values are stored in the connection's metadata."
  type        = map(string)
  default     = {}
}

variable "auth_config" {
  description = "How to send the key, for example { type = \"api_key\", name = \"Authorization\", format = \"Bearer {api_key}\" }."
  type        = map(string)
  default     = {}
}
