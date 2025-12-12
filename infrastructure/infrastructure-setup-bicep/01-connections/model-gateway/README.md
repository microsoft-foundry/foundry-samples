# ModelGateway Connection Examples

This folder contains Azure Bicep templates for creating ModelGateway connections to Azure AI Foundry projects.

## Prerequisites

1. **Azure CLI** installed and configured
2. **AI Foundry account and project** already created

## How to Deploy

All scenarios now use a single unified template: `connection-modelgateway.bicep`

### OpenAI ModelGateway Connection
```bash
# 1. Edit samples/parameters-openai.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-openai.json
```

### Dynamic Discovery ModelGateway Connection
```bash
# 1. Edit samples/parameters-dynamic.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-dynamic.json
```

### Static Models ModelGateway Connection
```bash
# 1. Edit samples/parameters-static.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-static.json
```

### Custom Auth Config ModelGateway Connection
```bash
# 1. Edit samples/parameters-custom-auth-config.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-custom-auth-config.json
```

### OAuth2 ModelGateway Connection
```bash
# 1. Edit samples/parameters-oauth2.json with your resource IDs and OAuth2 credentials
# 2. Deploy using the parameters file (OAuth2 credentials will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway.bicep \
  --parameters @samples/parameters-oauth2.json
```
  --parameters @parameters-gemini-modelgateway.json
```

## Parameter Files

- `samples/parameters-openai.json`: For OpenAI connections with Bearer token authentication
- `samples/parameters-dynamic.json`: For dynamic discovery connections with API key authentication
- `samples/parameters-static.json`: For static model list connections with placeholder models
- `samples/parameters-custom-auth-config.json`: For custom authentication and headers configuration
- `samples/parameters-oauth2.json`: For OAuth2 authentication connections

Edit these files to update the resource IDs and target URLs for your environment. API keys or OAuth2 credentials will be prompted securely during deployment.

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

**Important**: The template includes validation to prevent configuring both static models and dynamic discovery simultaneously, as these are mutually exclusive approaches.

The template uses conditional logic to include only non-empty parameters, making it clean and flexible for any ModelGateway scenario.