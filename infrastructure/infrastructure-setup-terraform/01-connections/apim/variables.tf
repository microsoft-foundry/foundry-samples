variable "project_resource_id" {
  description = "Resource ID of the Foundry project that gets the connection: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>."
  type        = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.CognitiveServices/accounts/[^/]+/projects/[^/]+$", var.project_resource_id))
    error_message = "project_resource_id must be a Foundry project resource ID: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>."
  }
}

variable "apim_resource_id" {
  description = "Resource ID of the API Management service: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/service/<name>. It can be in another subscription or resource group."
  type        = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.ApiManagement/service/[^/]+$", var.apim_resource_id))
    error_message = "apim_resource_id must be an API Management service resource ID: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/service/<name>."
  }
}

variable "api_name" {
  description = "Name of the API in API Management, for example foundry or openai. The connection target is the gateway URL plus this API's path."
  type        = string
}

variable "connection_name" {
  description = "Connection name. Agents reference a model as <connection_name>/<model-name>. Leave empty to use apim-<service-name>-<api_name>."
  type        = string
  default     = ""
}

variable "apim_subscription_name" {
  description = "API Management subscription whose primary key the connection uses, for ApiKey authentication."
  type        = string
  default     = "master"
}

variable "auth_type" {
  description = "How the connection authenticates to API Management: ApiKey (the subscription key) or ProjectManagedIdentity."
  type        = string
  default     = "ApiKey"

  validation {
    condition     = contains(["ApiKey", "ProjectManagedIdentity"], var.auth_type)
    error_message = "auth_type must be ApiKey or ProjectManagedIdentity."
  }
}

variable "is_shared_to_all" {
  description = "Share the connection with all users of the project. The service stores false on a project connection, whatever value is sent."
  type        = bool
  default     = false
}

variable "credential_version" {
  description = "Change this value after you rotate the API Management subscription key, then apply to send the new key. Terraform can't detect the change because the key isn't stored, so it replaces the connection."
  type        = string
  default     = "1"
}

variable "deployment_in_path" {
  description = "true if the API expects the deployment name in the URL path; false if it expects the model name in the request body."
  type        = bool
  default     = true
}

variable "inference_api_version" {
  description = "api-version query value for inference calls, such as chat completions. Leave empty if the API doesn't need one."
  type        = string
  default     = ""
}

variable "deployment_api_version" {
  description = "api-version query value for the list and get calls that dynamic discovery makes. Leave empty if the API doesn't need one."
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
  description = "How to send the key, for example { type = \"api_key\", name = \"api-key\", format = \"{api_key}\" }."
  type        = map(string)
  default     = {}
}
