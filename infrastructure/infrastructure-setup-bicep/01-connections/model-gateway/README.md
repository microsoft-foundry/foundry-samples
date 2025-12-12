# ModelGateway Connection Examples

This folder contains Azure Bicep templates for creating ModelGateway connections to Azure AI Foundry projects.

> **⚠️ IMPORTANT**: Before running any deployment, follow the [Setup Guide](./modelgateway-setup-guide-for-agents.md) guide to properly configure your ModelGateway service and obtain all required parameters. Make sure to collect these critical parameters to avoid 404/deploymentNotFound errors during Agent API execution:
> 1. **inferenceApiVersion** - The API version for chat completions calls if api-version query param is required
> 2. **deploymentApiVersion** - The API version for deployment operations if using dynamic discovery and api-version is reqiuired
> 3. **deploymentInPath** - Whether deployment ID is in the URL path or body in chat completions call
> These parameters must match your actual ModelGateway configuration to ensure successful deployments.

## Prerequisites

1. **Azure CLI** installed and configured
2. **AI Foundry account and project** already created

## How to Deploy

All scenarios now use a single unified template: `connection-modelgateway.bicep`

### OpenAI ModelGateway Connection
```bash
# 1. Edit samples/parameters-openai.json with your resource IDs
# 2. Deploy with your API key
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-openai.json \
  --parameters apiKey=<your-api-key>
```

### Foundry AzureOpenAI ModelGateway Connection
```bash
# 1. Edit samples/parameters-foundryopenai.json with your resource IDs
# 2. Deploy with your API key
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-foundryopenai.json \
  --parameters apiKey=<your-api-key>
```


### Dynamic Discovery ModelGateway Connection
```bash
# 1. Edit samples/parameters-dynamic.json with your resource IDs
# 2. Deploy with your API key
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-dynamic.json \
  --parameters apiKey=<your-api-key>
```

### Static Models ModelGateway Connection
```bash
# 1. Edit samples/parameters-static.json with your resource IDs
# 2. Deploy with your API key
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-static.json \
  --parameters apiKey=<your-api-key>
```

### Custom Auth Config ModelGateway Connection
```bash
# 1. Edit samples/parameters-custom-auth-config.json with your resource IDs
# 2. Deploy with your API key
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-custom-auth-config.json \
  --parameters apiKey=<your-api-key>
```

### OAuth2 ModelGateway Connection
```bash
# 1. Edit samples/parameters-oauth2.json with your parameters
# 2. Deploy with your client secret
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-oauth2.json \
  --parameters clientSecret=<your-client-secret>
```

## Validation Features

The template includes built-in validation:
- **Missing API Key**: Fails with "ERROR: apiKey is required when authType is ApiKey."
- **Missing OAuth2 Credentials**: Fails with "ERROR: clientId, clientSecret, and tokenUrl are required when authType is OAuth2."
- **Invalid Configuration**: Fails with "ERROR: Cannot configure both static models and dynamic discovery."

## Parameter Files

- `samples/parameters-openai.json`: For OpenAI connections with Bearer token authentication
- `samples/parameters-foundryopenai.json`: For Foundry AzureOpenAI connection
- `samples/parameters-dynamic.json`: For dynamic discovery connections with API key authentication
- `samples/parameters-static.json`: For static model list connections with placeholder models
- `samples/parameters-custom-auth-config.json`: For custom authentication and headers configuration
- `samples/parameters-oauth2.json`: For OAuth2 authentication connections

Edit these files to update the resource IDs and target URLs for your environment. API keys will be prompted securely during deployment. For OAuth2 connections, the client secret must be passed as a parameter.

## Unified Template Features

The `connection-modelgateway.bicep` template supports all ModelGateway connection scenarios:

1. **Basic Configuration**: Required deploymentInPath and inferenceAPIVersion
2. **Deployment API Version**: Optional deploymentAPIVersion for deployment management  
3. **Dynamic Discovery**: Automatic model discovery using API endpoints (listModelsEndpoint, getModelEndpoint, deploymentProvider)
4. **Static Model List**: Predefined list of available models in staticModels array
5. **Custom Headers**: Custom HTTP headers as key-value pairs in customHeaders object
6. **Custom Auth Config**: Flexible authentication configuration with authConfig object
7. **Authentication Options**: 
   - **ApiKey Authentication**: Traditional API key-based authentication
   - **OAuth2 Authentication**: OAuth2 client credentials flow with configurable scopes

The template uses conditional logic to include only non-empty parameters, making it clean and flexible for any ModelGateway scenario.