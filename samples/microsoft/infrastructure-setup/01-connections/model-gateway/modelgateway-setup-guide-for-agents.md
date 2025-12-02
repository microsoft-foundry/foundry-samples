# ModelGateway Setup Guide for Foundry Agents

> **🎯 Step-by-Step Configuration**  
> This guide shows you how to configure your self-hosted or third-party gateway to make it ready for use by Foundry Agents as a ModelGateway connection.

## 🏗️ Prerequisites: Gateway Instance Setup

Before configuring your gateway for Foundry Agents, ensure you have a working gateway instance. This guide supports various gateway types:

### Supported Gateway Types

| Gateway Type | Examples | Notes |
|--------------|----------|-------|
| **🔧 Self-Hosted Gateways** | Custom Node.js/Python APIs, Docker containers | Full control over configuration |
| **🌐 Third-Party Gateways** | Kong, MuleSoft, Ambassador, Istio | Enterprise API management solutions |
| **☁️ Cloud Gateways** | AWS API Gateway, Google Cloud Endpoints | Cloud-native gateway services |
| **🔀 Proxy Solutions** | Nginx, HAProxy, Envoy | Load balancers with API capabilities |

### Gateway Requirements

Your gateway must meet these minimum requirements:

| Requirement | Description | Required |
|-------------|-------------|----------|
| **💬 Chat Completions API** | Expose an endpoint that accepts OpenAI-compatible chat completion requests | ✅ Required |
| **🔐 Authentication** | Support API Key or OAuth2 authentication | ✅ Required |
| **🌐 Network Access** | Accessible from Azure (public internet or private network) | ✅ Required |
| **📋 Model Discovery** | Either static model list or dynamic discovery endpoint | 🔧 Choose One |

---

## 🚀 Configuration Steps

### Step 1: 🔧 Configure Chat Completions Endpoint

Foundry Agents require a **chat completions endpoint** that follows the OpenAI API specification. Your gateway must expose this endpoint and forward requests to your AI models.

#### 📝 Endpoint Requirements

Your chat completions endpoint should:

1. **📍 Accept POST Requests**: Handle `POST` requests to a chat completions endpoint
2. **📋 OpenAI-Compatible Format**: Accept requests in OpenAI chat completions format
3. **🔄 Proper Response Format**: Return responses in OpenAI chat completions format
4. **🛠️ Tool Support**: Support function/tool calling for agent interactions

#### 🔗 Example Endpoint Patterns

| Gateway Style | Endpoint Pattern | Example |
|---------------|------------------|---------|
| **Direct Chat** | `/chat/completions` | `https://my-gateway.com/chat/completions` |
| **Deployment Style** | `/deployments/{deployment}/chat/completions` | `https://my-gateway.com/deployments/gpt-4-deployment/chat/completions` |
| **API Versioned** | `/v1/chat/completions` | `https://my-gateway.com/v1/chat/completions` |

#### 🧪 Test Your Chat Completions

Before proceeding, test your chat completions endpoint:

```bash
# Example test request
curl -X POST "https://your-gateway.com/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, test message"}
    ],
    "max_tokens": 50
  }'
```

✅ **Expected Response**: Your endpoint should return a valid OpenAI-compatible chat completion response.

### Step 2: 🔐 Configure Authentication

Your gateway must support one of the following authentication methods:

#### Option 1: 🔑 API Key Authentication

**Implementation**: Your gateway should accept API keys via:
- **Authorization Header**: `Authorization: Bearer YOUR_API_KEY`
- **API Key Header**: `X-API-Key: YOUR_API_KEY` 
- **Custom Header Name**: Any custom auth config you configure via connection auth_config

#### Option 2: 🛡️ OAuth2 Client Credentials

**Implementation**: Your gateway should support OAuth2 client credentials flow:
- **Token Endpoint**: Provide a token endpoint for credential exchange
- **Scopes**: Define appropriate scopes for AI model access
- **Bearer Tokens**: Accept bearer tokens in Authorization header

**Example OAuth2 Flow**:
1. Foundry requests token from your token endpoint
2. Your gateway returns access token
3. Foundry uses token in subsequent requests

### Step 3: 🔍 Configure Model Discovery

You need to choose how Foundry Agents will discover available models through your gateway:

#### Option 1: 📋 Static Model List (Recommended)

**✅ Advantages:**
- **🚀 Better Performance**: No additional API calls needed
- **🔧 Simpler Setup**: No additional endpoints required
- **💰 Cost Effective**: Reduces load on your gateway

**📝 Implementation**: You'll configure the static model list directly in the Foundry connection metadata. No additional gateway setup needed.

**Example Static Model Configuration**:
```json
{
  "staticModels": [
    {
      "name": "my-gpt-4o-deployment-name",
      "properties": {
        "model": {
          "name": "gpt-4o",
          "version": "2024-11-20",
          "format": "OpenAI"
        }
      }
    },
    {
      "name": "my-gpt-5-deployment-name",
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

#### Option 2: 🌐 Dynamic Model Discovery

**📋 When to Use:**
- Models change frequently
- You want real-time model availability
- Static configuration is not practical

**🔧 Implementation**: Add model discovery endpoints to your gateway.

##### 📝 Required Discovery Endpoints

If you choose dynamic discovery, make these endpoints available on your gateway:

1. **📋 List Models Endpoint** - Returns all available models
2. **🎯 Get Model Endpoint** - Returns details for a specific model

##### 🛠️ List Models Endpoint

**Endpoint**: `GET /models` (or your preferred path like `/deployments`, `/v1/models`)

**AzureOpenAI Format Response (Recommended)**:
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

**OpenAI Format Response**:
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

##### 🛠️ Get Model Endpoint

**Endpoint**: `GET /models/{deploymentName}` (or your preferred path like `/deployments/{deploymentName}`, `/v1/models/{deploymentName}`). Ensure presence of `{deploymentName}` placeholder which will be replaced by actual deployment name during the agents runtime.

**AzureOpenAI Format Response (Recommended)**:
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

**OpenAI Format Response**:
```json
{
  "id": "gpt-4o",
  "object": "model",
  "created": 1687882411,
  "owned_by": "openai"
}
```

**Configuration in Connection Metadata**:

**Recommended - AzureOpenAI format**:
```json
{
  "modelDiscovery": {
    "listModelsEndpoint": "/deployments",
    "getModelEndpoint": "/deployments/{deploymentName}",
    "deploymentProvider": "AzureOpenAI"
  }
}
```

**Alternative - OpenAI format**:
```json
{
  "modelDiscovery": {
    "listModelsEndpoint": "/v1/models",
    "getModelEndpoint": "/v1/models/{deploymentName}",
    "deploymentProvider": "OpenAI"
  }
}
```

**Supported DeploymentProvider Values:**
- `"AzureOpenAI"`: **Recommended** - For Azure OpenAI ARM resource response format with detailed model information
- `"OpenAI"`: For OpenAI-compatible response format

### Step 4: 🔧 Optional: Configure Custom Headers

If your gateway requires custom headers for routing, or other purposes, you can configure them:

**Example Custom Headers**:
```json
{
  "customHeaders": {
    "X-Environment": "production",
    "X-Route-Policy": "premium", 
    "X-Client-App": "foundry-agents",
    "X-Tenant-ID": "your-tenant"
  }
}
```

These headers will be included in all requests from Foundry to your gateway.

### Step 5: 📋 Gather Connection Details

Once your gateway is configured, collect these details for creating your Foundry connection:

#### 🎯 1. Target URL

The base URL of your gateway where Foundry should send requests.

**Examples**:
- `https://my-gateway.company.com`
- `https://api-gateway.example.org/v1`
- `https://my-custom-ai-proxy.net/models`

#### 🔧 2. Gateway Name

A friendly name for your gateway (used in connection naming).

**Examples**: `company-gateway`, `production-ai-gateway`, `custom-proxy`

#### 🛤️ 3. Deployment in Path

Determine how your chat completions endpoint handles deployment specification:

- **✅ Set to "true"**: If model is in the URL path (e.g., `/deployments/my-gpt-4o-deployment/chat/completions`)
- **❌ Set to "false"**: If model is passed as a parameter (e.g., `/chat/completions` with model in request body)

#### 🔧 4. API Versions

Note any API versions query param (api-version) your endpoints require:

- **Inference API Version**: Version for chat completions (e.g., `v1`, `2024-02-01`)
- **Deployment API Version**: Version for model discovery (if using dynamic discovery)

#### 🔍 5. Model Discovery Configuration

Based on your choice in Step 3:

**For Static Models**: Prepare your model list
**For Dynamic Discovery**: Note your discovery endpoint paths

---

## 📚 Additional Resources

- **🔗 [ModelGateway Connection Objects Documentation](ModelGateway-Connection-Objects.md)** - Read up on more configurations available for ModelGateway connections
- **📖 [ModelGateway README](README.md)** - Next steps for deploying your ModelGateway connections