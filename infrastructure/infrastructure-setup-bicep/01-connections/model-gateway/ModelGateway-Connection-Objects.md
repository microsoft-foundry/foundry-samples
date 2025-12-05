# ModelGateway Connection JSON Examples

## Overview

ModelGateway connections provide a unified interface for connecting to various AI model providers through the Azure ML workspace connection framework. These connections support both static model configuration (predefined models) and dynamic model discovery (runtime model detection).

### Key Features

- **Unified API**: Single connection interface for multiple AI providers (Azure AI, OpenAI, MuleSoft, etc.)
- **Authentication**: Support for API key authentication with workspace credential management
- **Discovery Patterns**: Choose between static model lists or dynamic discovery endpoints
- **Provider Abstraction**: Consistent model format regardless of underlying provider
- **Enterprise Integration**: Support for enterprise gateways like MuleSoft for multi-provider scenarios

### Connection Categories

All ModelGateway connections use the `"category": "ModelGateway"` to ensure proper routing through the ModelGateway service infrastructure.

### Discovery Methods

**Static Discovery**: Models are predefined in the connection metadata using the `models` array. Best for:
- Dynamic discovery not possible
- Fixed model deployments
- Known model configurations
- Enterprise scenarios with approved model lists

**Dynamic Discovery**: Models are discovered at runtime using API endpoints defined in `modelDiscovery`. Best for:
- Frequently changing model deployments
- Provider-managed model catalogs
- Development and testing scenarios

### Authentication

All examples use `"authType": "ApiKey"` with workspace-managed credentials. The actual API keys are stored securely and referenced through the credential system. We will expand to more auth methods in upcoming releases.

## Connection Schema Definitions

### 1. ModelDiscovery (Dynamic Discovery)

The `modelDiscovery` object enables runtime model detection through API endpoints. Azure Agents combines this configuration with the connection's `target` URL and `credentials` to make discovery calls.

```json
{
  "modelDiscovery": {
    "listModelsEndpoint": "/v1/models",
    "getModelEndpoint": "/v1/models/{deploymentName}",
    "deploymentProvider": "OpenAI"
  }
}
```

**Fields:**
- `listModelsEndpoint` - Endpoint to retrieve all available models (relative to target URL)
- `getModelEndpoint` - Endpoint to get specific model details with `{deploymentName}` placeholder
- `deploymentProvider` - Provider format for response parsing. **Supported values: `"OpenAI"` and `"AzureOpenAI"`** (exactly 2 formats)

**How Azure Agents Uses It:**
1. Constructs full URL: `{target}{listModelsEndpoint}`
2. Adds authentication headers from `credentials`
3. Makes HTTP request to discover available models
4. Parses response based on `deploymentProvider` format (OpenAI or AzureOpenAI)

**Supported DeploymentProvider Formats:**

We support exactly **2 deployment API formats** for model discovery:

**1. AzureOpenAI Format Responses:**

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

**2. OpenAI Format Responses:**

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

### 2. Static Discovery

Static discovery uses a predefined `models` array in metadata. Models are defined using the `ModelInfo` structure:

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
    }
  ]
}
```

**Structure:**
- `name` - Deployment name (how you reference the model in API calls)
- `properties.model.name` - Actual model name from provider
- `properties.model.version` - Model version identifier
- `properties.model.format` - Provider format (OpenAI, DeepSeek etc)

### 3. InferenceAPIVersion

Specifies the API version for model inference calls (chat completions, etc.).

```json
{
  "inferenceAPIVersion": "2025-03-01"
}
```

**Usage by Azure Agents:**
- Appended as query parameter: `?api-version=2025-03-01`
- Used for all inference requests (chat completions, not discovery or management calls)

### 4. DeploymentInPath

Controls how deployment names are passed to the provider API.

```json
{
  "deploymentInPath": "true"  // or "false"
}
```

**When `true` (Path-based routing):**
```
URL: {target}/deployments/{deploymentName}/chat/completions
```

**When `false`:**
```
URL: {target}/chat/completions
Body: {"model": "{deploymentName}"}
```

**Azure Agents Behavior:**
- `true`: Injects deployment name into URL path
- `false`: Passes deployment name via model parameter

### 5. DeploymentAPIVersion

Specifies the API version for deployment management calls (listing deployments, getting deployment details).

```json
{
  "deploymentAPIVersion": "2025-03-01"
}
```

**Usage by Azure Agents:**
- Used only for `modelDiscovery` endpoint calls
- Separate from `inferenceAPIVersion` to allow different versioning
- Appended as query parameter to discovery endpoints

**Complete Example with All Schema Elements:**

```json
{
  "metadata": {
    "modelDiscovery": {
      "listModelsEndpoint": "/openai/deployments",
      "getModelEndpoint": "/openai/deployments/{deploymentName}",
      "deploymentProvider": "AzureOpenAI"
    },
    "deploymentInPath": "true",
    "inferenceAPIVersion": "2025-03-01",
    "deploymentAPIVersion": "2025-03-01"
  }
}
```

### 6. CustomHeaders - **OPTIONAL**

Specifies custom headers to be passed to ModelGateway for chat completion and inference calls. This allows you to include additional headers required by your gateway policies or routing logic.

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
- **Usage**: Headers are added to all chat completion and inference requests

**Usage by Azure Agents:**
- Headers are included in all `/chat/completions` requests to ModelGateway
- Applied alongside authentication headers
- Useful for gateway policy routing, rate limiting, or custom logic

**Example Custom Headers:**
```json
"customHeaders": {
  "X-API-Version": "2024-02-01",
  "X-Environment": "production",
  "X-Route-Policy": "premium",
  "X-Client-App": "foundry-agents"
}
```

## Basic ModelGateway Connection with Dynamic Discovery

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/basic-gateway-connection",
  "name": "basic-gateway-connection",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ModelGateway",
    "target": "https://api.openai.com",
    "authType": "ApiKey",
    "credentials": {
      "key": "{api-key-reference}"
    },
    "metadata": {
      "modelDiscovery": {
        "listModelsEndpoint": "/v1/models",
        "getModelEndpoint": "/v1/models/{deploymentName}",
        "deploymentProvider": "OpenAI"
      }
    }
  }
}
```

## OpenAI Connection with Static Models

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/openai-static-connection",
  "name": "openai-static-connection",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ModelGateway",
    "target": "https://api.openai.com",
    "authType": "ApiKey",
    "credentials": {
      "key": "{openai-api-key-reference}"
    },
    "metadata": {
      "models": [
        {
          "name": "gpt-4o",
          "properties": {
            "model": {
              "name": "gpt-4o",
              "version": "2024-11-20",
              "format": "OpenAI"
            }
          }
        },
        {
          "name": "gpt-5",
          "properties": {
            "model": {
              "name": "gpt-5",
              "version": "",
              "format": "OpenAI"
            }
          }
        },
        {
          "name": "text-embedding-ada-002",
          "properties": {
            "model": {
              "name": "text-embedding-ada-002",
              "version": "2",
              "format": "OpenAI"
            }
          }
        }
      ]
    }
  }
}
```

## Azure OpenAI Connection with Dynamic Discovery

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/azure-openai-dynamic",
  "name": "azure-openai-dynamic",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ModelGateway",
    "target": "https://your-resource.openai.azure.com/openai",
    "authType": "ApiKey",
    "credentials": {
      "key": "{azure-openai-key-reference}"
    },
    "metadata": {
      "modelDiscovery": {
        "listModelsEndpoint": "/deployments",
        "getModelEndpoint": "/deployments/{deploymentName}",
        "deploymentProvider": "AzureOpenAI"
      },
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2024-02-01",
      "deploymentAPIVersion": "2024-02-01"
    }
  }
}
```

## MuleSoft Multi-Provider Connection with Static Models

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/mulesoft-multi-provider",
  "name": "mulesoft-multi-provider",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ModelGateway",
    "target": "https://api.mulesoft.enterprise.com/llm-gateway",
    "authType": "ApiKey",
    "credentials": {
      "key": "{mulesoft-api-key-reference}"
    },
    "metadata": {
      "models": [
        {
          "name": "openai-gpt-4o",
          "properties": {
            "model": {
              "name": "gpt-4o",
              "version": "2024-11-20",
              "format": "OpenAI"
            }
          }
        },
        {
          "name": "openai-gpt-5",
          "properties": {
            "model": {
              "name": "gpt-5",
              "version": "",
              "format": "OpenAI"
            }
          }
        },
        {
          "name": "deepseek-v1-deploy",
          "properties": {
            "model": {
              "name": "deepseek-v1",
              "format": "Deepseek"
            }
          }
        }
      ],
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2025-03-01"
    }
  }
}
```

## MuleSoft Dynamic Discovery Connection

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/mulesoft-dynamic-discovery",
  "name": "mulesoft-dynamic-discovery",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ModelGateway",
    "target": "https://enterprise-ai-gateway.mulesoft.com/api",
    "authType": "ApiKey",
    "credentials": {
      "key": "{mulesoft-enterprise-key-reference}"
    },
    "metadata": {
      "modelDiscovery": {
        "listModelsEndpoint": "/v2/models",
        "getModelEndpoint": "/v2/models/{deploymentName}",
        "deploymentProvider": "AzureOpenAI"
      },
      "deploymentInPath": "true",
      "inferenceAPIVersion": "2025-03-01",
      "deploymentAPIVersion": "2025-03-01"
    }
  }
}
```

## ModelGateway Connection with Custom Headers

ModelGateway connection with custom headers for gateway policy routing and client identification.

```json
{
  "id": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.MachineLearningServices/workspaces/{workspaceName}/connections/gateway-custom-headers",
  "name": "gateway-custom-headers",
  "type": "Microsoft.MachineLearningServices/workspaces/connections",
  "properties": {
    "category": "ModelGateway",
    "target": "https://enterprise-gateway.company.com/api",
    "authType": "ApiKey",
    "credentials": {
      "key": "{api-key-reference}"
    },
    "metadata": {
      "modelDiscovery": {
        "listModelsEndpoint": "/v1/models",
        "getModelEndpoint": "/v1/models/{deploymentName}",
        "deploymentProvider": "OpenAI"
      },
      "deploymentInPath": "false",
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
```

## AuthConfig (Optional)

The `authConfig` metadata field allows customization of authentication headers sent to the model provider. This is useful for providers that require specific header formats or additional authentication information.

### AuthConfig Fields

- `type`: Must be "api_key" for API key authentication
- `name`: Custom header name for the API key
- `format`: Template for the header value (defaults to "{api_key}" if not provided)

### AuthConfig Examples

#### Custom Header Name and Template
```json
{
  "metadata": {
    "authConfig": "serialized({
      "type": "api_key",
      "name": "x-api-key",
      "format": "Key {api_key}"
    })"
  }
}
```

#### OpenAI Bearer Format (Default)
```json
{
  "metadata": {
    "authConfig": "serialized({
      "type": "api_key",
      "name": "Authorization",
      "format": "Bearer {api_key}"
    })"
  }
}
```

#### Custom Provider Format
```json
{
  "metadata": {
    "authConfig": "serialized({
      "type": "api_key",
      "name": "X-Custom-Auth",
      "format": "Custom-Token {api_key}"
    })"
  }
}
```

### Important Notes

- All complex metadata values (objects and arrays) must be stored as JSON strings.
- Simple string values like "true", "false", or API versions can remain as regular strings
- The `{api_key}` placeholder in the format field will be replaced with the actual API key at runtime
- If `authConfig` is not provided, the default api-key format will be used