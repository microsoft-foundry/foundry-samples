# APIM Connection JSON Examples

## Overview

APIM (API Management) connections are specialized ModelGateway connections designed for Azure API Management scenarios. These connections provide intelligent defaults and follow APIM standard conventions while integrating with the broader ModelGateway ecosystem.

### Key Features

- **APIM Category**: Uses `"category": "ApiManagement"` for proper APIM-specific handling
- **Intelligent Defaults**: Provides standard APIM endpoints when metadata is not specified
- **Convention-Based**: Follows Azure API Management naming and routing patterns
- **Flexible Override**: Supports metadata overrides for custom APIM configurations
- **Enterprise Ready**: Designed for production APIM gateway scenarios

### APIM-Specific Behavior

**Default Endpoints**: When metadata is not provided, APIM connections use these defaults:
- List Deployments: `/deployments`
- Get Deployment: `/deployments/{deploymentName}`
- Provider: `AzureOpenAI`

**Configuration Priority**:
1. Explicit metadata values (highest priority)
2. APIM standard defaults (fallback)

### Authentication Patterns

APIM connections support various authentication methods:
- **API Key**: Standard subscription key authentication
- **AAD (Azure Active Directory)**: Enterprise identity integration


## Connection Schema Definitions

### 1. DeploymentInPath - **REQUIRED**

Controls how deployment names are passed to the APIM gateway. **This field is required** and must be specified in all APIM connections.

```json
{
  "deploymentInPath": "true"  // or "false"
}
```

**When `"true"` (Path-based routing):**
```
URL: {target}/deployments/{deploymentName}/chat/completions
```

**When `"false"`:**
```
URL: {target}/chat/completions
Body: {"model": "{deploymentName}"}
```

**Azure Agents Behavior:**
- `"true"`: Injects deployment name into URL path for APIM routing
- `"false"`: Passes deployment name via model parameter in request body
- **If not specified**: Connection will fail validation

### 2. InferenceAPIVersion - **OPTIONAL**

Specifies the API version for model inference calls (chat completions, embeddings, etc.) through APIM.

```json
{
  "inferenceAPIVersion": "2024-02-01"
}
```

**Usage by Azure Agents:**
- Appended as query parameter: `?api-version=2024-02-01`
- Used for all inference requests through APIM gateway
- **If not specified**: Azure Agents will use a default API version

### 3. DeploymentAPIVersion - **OPTIONAL**

Specifies the API version for deployment management calls through APIM.

```json
{
  "deploymentAPIVersion": "2024-02-01"
}
```

**Usage by Azure Agents:**
- Used only for `modelDiscovery` endpoint calls through APIM
- Separate from `inferenceAPIVersion` to allow different versioning
- Appended as query parameter to discovery endpoints
- **If not specified**: Azure Agents will not append any query param to the deployments API.

### 4. ModelDiscovery (Dynamic Discovery) - **OPTIONAL**

The `modelDiscovery` object is **optional** and only needed when customers expose different endpoints than the APIM defaults (`/deployments`, `/deployments/{deploymentName}`). Azure Agents will automatically use APIM standard conventions if `modelDiscovery` is not provided in the metadata.

**When to include `modelDiscovery`:**
- Customer APIM exposes custom endpoints (not `/deployments`)
- Different API routing or endpoint naming conventions
- Need to specify OpenAI format instead of default AzureOpenAI

**When to omit `modelDiscovery`:**
- Standard APIM setup with default `/deployments` endpoints
- Following Azure OpenAI /deployments API conventions through APIM
- Using APIM defaults is sufficient

```json
{
  "modelDiscovery": {
    "listModelsEndpoint": "/custom/models",
    "getModelEndpoint": "/custom/models/{deploymentName}",
    "deploymentProvider": "OpenAI"
  }
}
```

**Fields:**
- `listModelsEndpoint` - Endpoint to retrieve all available models (relative to target URL)
- `getModelEndpoint` - Endpoint to get specific model details with `{deploymentName}` placeholder
- `deploymentProvider` - Provider format for response parsing. **Supported values: `"OpenAI"` and `"AzureOpenAI"`** (exactly 2 formats)

**APIM Default Values (when `modelDiscovery` is omitted):**
- `listModelsEndpoint`: `/deployments`
- `getModelEndpoint`: `/deployments/{deploymentName}`
- `deploymentProvider`: `AzureOpenAI`

**How Azure Agents Uses It:**
1. Constructs full URL: `{target}{listModelsEndpoint}`
2. Adds authentication headers from `credentials`
3. Makes HTTP request to discover available models
4. Parses response based on `deploymentProvider` format (OpenAI or AzureOpenAI)
5. Caches model list for connection lifecycle

**Supported DeploymentProvider Formats:**

We support exactly **2 deployment API formats** for model discovery through APIM:

**1. AzureOpenAI Format Responses (`deploymentProvider: "AzureOpenAI"`) - DEFAULT:**

*List Deployments Response (`listModelsEndpoint`):`*
```json
{
  "value": [
    {
      "name": "gpt-4o-deployment",
      "properties": {
        "model": {
          "format": "OpenAI",
          "name": "gpt-4o",
          "version": "2024-11-20"
        }
      }
    },
    {
      "name": "gpt-5-deployment", 
      "properties": {
        "model": {
          "format": "OpenAI",
          "name": "gpt-5",
          "version": ""
        }
      }
    }
  ]
}
```

*Get Deployment by Name Response (`getModelEndpoint`):`*
```json
{
  "name": "gpt-4o-deployment",
  "properties": {
    "model": {
      "format": "OpenAI",
      "name": "gpt-4o",
      "version": "2024-11-20"
    }
  }
}
```

- Uses `value` array for list, single object for get-by-name
- Follows Azure ARM resource structure
- Separate deployment `name` and model details in `properties.model`
- Includes model `name`, `version`, and `format`

**2. OpenAI Format Responses (`deploymentProvider: "OpenAI"`):**

*List Models Response (`listModelsEndpoint`):`*
```json
{
  "data": [
    {
      "id": "gpt-4o",
      "object": "model",
      "created": 1687882411,
      "owned_by": "openai"
    },
    {
      "id": "gpt-5",
      "object": "model", 
      "created": 1677610602,
      "owned_by": "openai"
    }
  ]
}
```

*Get Model by Name Response (`getModelEndpoint`):`*
```json
{
  "id": "gpt-4o",
  "object": "model",
  "created": 1687882411,
  "owned_by": "openai"
}
```

- Uses `data` array for list, single object for get-by-name
- `id` serves as both deployment name and model name
- No version information provided in API responses

### 5. Static Discovery - **OPTIONAL**

Static discovery uses a predefined `models` array in metadata. Models are defined using the `ModelInfo` structure. **Either static discovery OR dynamic discovery can be used, not both.**

```json
{
  "models": [
    {
      "name": "gpt-4o-deployment",
      "properties": {
        "model": {
          "name": "gpt-4o",
          "version": "2024-11-20",
          "format": "OpenAI"
        }
      }
    },
    {
      "name": "gpt-5-deployment",
      "properties": {
        "model": {
          "name": "gpt-5",
          "version": "",
          "format": "OpenAI"
        }
      }
    }
  ]
}
```

**Structure:**
- `name` - Deployment name (how you reference the model in APIM API calls)
- `properties.model.name` - Actual model name from provider
- `properties.model.version` - Model version identifier
- `properties.model.format` - Provider format (OpenAI, DeepSeek, etc.)

**When to use static discovery:**
- Fixed set of known models through APIM
- No need for runtime model discovery
- Predefined model configurations

**If not specified**: Azure Agents will attempt dynamic discovery using `modelDiscovery` settings or APIM defaults

### 6. AuthConfig - **OPTIONAL**

The `authConfig` metadata field allows customization of the API key header name and format sent to the APIM gateway. This lets you send the API key using different header names (like `x-api-key` instead of `api-key`) or different value formats (like `Bearer {api_key}` instead of just the key).

```json
{
  "authConfig": {
    "type": "api_key",
    "name": "x-api-key",
    "format": "Key {api_key}"
  }
}
```

**Structure:**
- **Type**: Must be stored as a JSON string (serialized)
- **Fields**:
  - `type`: Must be "api_key" for API key authentication
  - `name`: Custom header name for the API key (instead of default `api-key`)
  - `format`: Template for the header value with `{api_key}` placeholder

**Usage by Azure Agents:**
- Customizes how the APIM subscription key is sent in headers
- The `{api_key}` placeholder is replaced with the actual APIM subscription key
- Applied to all requests to APIM (chat completions, model discovery)

**Common AuthConfig Examples:**

*Custom Header Name:*
```json
"authConfig": "{\"type\":\"api_key\",\"name\":\"x-api-key\",\"format\":\"{api_key}\"}"
```

*Bearer Token Format:*
```json
"authConfig": "{\"type\":\"api_key\",\"name\":\"Authorization\",\"format\":\"Bearer {api_key}\"}"
```

*Custom Format:*
```json
"authConfig": "{\"type\":\"api_key\",\"name\":\"X-API-Token\",\"format\":\"Token {api_key}\"}"
```

*Default APIM Format (when authConfig not specified):*
```
api-key: {api_key}
```

**When to use authConfig:**
- Your APIM policies expect a different header name than `api-key`
- Need Bearer token format: `Authorization: Bearer {api_key}`
- Custom header formats required by APIM configuration
- Integration with specific APIM policy configurations

**If not specified**: Azure Agents will use the standard `api-key` header with the raw subscription key value

### 7. CustomHeaders - **OPTIONAL**

Specifies custom headers to be passed to APIM gateway for chat completion and inference calls. This allows you to include additional headers required by your APIM policies or routing logic.

```json
{
  "customHeaders": {
    "X-Custom-Policy": "production",
    "X-Route-Version": "v2", 
    "X-Client-ID": "foundry-agents"
  }
}
```

**Structure:**
- **Type**: Dictionary/object with string keys and string values
- **Storage Format**: Must be stored as a JSON string (serialized)
- **Usage**: Headers are added to all chat completion and inference requests

**Usage by Azure Agents:**
- Headers are included in all `/chat/completions` requests to APIM
- Applied alongside authentication headers
- Useful for APIM policy routing, rate limiting, or custom logic

**Example Custom Headers:**
```json
"customHeaders": {
  "X-API-Version": "2024-02-01",
  "X-Environment": "production",
  "X-Route-Policy": "premium",
  "X-Client-App": "foundry-agents"
}
```

## Examples

Uses all APIM defaults, but provides fields: `deploymentInPath`, `inferenceAPIVersion`.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/apim-defaults",
  "name": "apim-defaults",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ApiManagement",
    "target": "https://your-apim-gateway.azure-api.net/myapi",
    "authType": "ApiKey",
    "credentials": {
      "key": "{api-key-reference}"
    },
    "metadata": {
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2024-02-01"
    }
  }
}
```

## Example 2: APIM with Deployment API Version

Configuration with required `deploymentInPath` and inference version, deployment API Version.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/apim-minimal",
  "name": "apim-minimal",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ApiManagement",
    "target": "https://minimal-apim.azure-api.net/api",
    "authType": "AAD",
    "credentials": {},
    "metadata": {
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2024-02-01",
      "deploymentAPIVersion": "2025-01-01"
    }
  }
}
```

## Example 3: APIM with Dynamic Discovery

Dynamic model discovery using `/models` and `/models/{deploymentName}` endpoints with AzureOpenAI format deployments.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/apim-dynamic-azure",
  "name": "apim-dynamic-azure",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ApiManagement",
    "target": "https://dynamic-apim.azure-api.net/api",
    "authType": "ApiKey",
    "credentials": {
      "key": "{api-key-reference}"
    },
    "metadata": {
      "modelDiscovery": {
        "listModelsEndpoint": "v1/models",
        "getModelEndpoint": "/models/{deploymentName}",
        "deploymentProvider": "AzureOpenAI"
      },
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2024-02-01",
      "deploymentAPIVersion": "2024-02-01"
    }
  }
}
```

## Example 4: APIM with Dynamic Discovery - OpenAI

Same as Example 3 but using OpenAI format for model discovery.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/apim-dynamic-openai",
  "name": "apim-dynamic-openai",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ApiManagement",
    "target": "https://openai-apim.azure-api.net/api/",
    "authType": "ApiKey",
    "credentials": {
      "key": "{api-key-reference}"
    },
    "metadata": {
      "modelDiscovery": {
        "listModelsEndpoint": "/models",
        "getModelEndpoint": "/models/{deploymentName}",
        "deploymentProvider": "OpenAI"
      },
      "deploymentInPath": "false",
      "inferenceAPIVersion": "2024-02-01"
    }
  }
}
```

## Example 5: APIM with Static Model List

Predefined static list of models without dynamic discovery.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/apim-static-models",
  "name": "apim-static-models",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ApiManagement",
    "target": "https://static-apim.azure-api.net/api",
    "authType": "AAD",
    "credentials": {},
    "metadata": {
      "models": [
        {
          "name": "gpt-4o-deployment",
          "properties": {
            "model": {
              "name": "gpt-4o",
              "version": "2024-11-20",
              "format": "OpenAI"
            }
          }
        },
        {
          "name": "gpt-5-deployment",
          "properties": {
            "model": {
              "name": "gpt-5",
              "version": "",
              "format": "OpenAI"
            }
          }
        }
      ],
      "deploymentInPath": "false",
      "inferenceAPIVersion": "2024-02-01"
    }
  }
}
```

## Example 6: APIM with Custom Headers

APIM connection with custom headers for policy routing and client identification.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/apim-custom-headers",
  "name": "apim-custom-headers",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ApiManagement",
    "target": "https://enterprise-apim.azure-api.net/api",
    "authType": "ApiKey",
    "credentials": {
      "key": "{api-key-reference}"
    },
    "metadata": {
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2024-02-01",
      "customHeaders": {
        "X-Environment": "production",
        "X-Route-Policy": "premium",
        "X-Client-App": "foundry-agents",
        "X-API-Version": "2024-02-01"
      }
    }
  }
}