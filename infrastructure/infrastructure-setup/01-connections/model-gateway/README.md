# ModelGateway Connection Examples

This folder contains Azure Bicep templates for creating ModelGateway connections to Azure AI Foundry projects.

## Prerequisites

1. **Azure CLI** installed and configured
2. **AI Foundry account and project** already created

## How to Deploy

### Basic ModelGateway Connection
```bash
# 1. Edit parameters-basic.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway-basic.bicep \
  --parameters @parameters-basic.json
```

### Dynamic Discovery ModelGateway Connection
```bash
# 1. Edit parameters-dynamic.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway-dynamic.bicep \
  --parameters @parameters-dynamic.json
```

### Static Models ModelGateway Connection
```bash
# 1. Edit parameters-static.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway-static.bicep \
  --parameters @parameters-static.json
```

### Comprehensive ModelGateway Connection (All Features)
```bash
# 1. Edit parameters-comprehensive.json with your resource IDs
# 2. Deploy using the parameters file (API key will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway-comprehensive.bicep \
  --parameters @parameters-comprehensive.json
```

### OAuth2 ModelGateway Connection
```bash
# 1. Edit parameters-oauth2.json with your resource IDs and OAuth2 credentials
# 2. Deploy using the parameters file (OAuth2 credentials will be prompted)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-modelgateway-oauth2.bicep \
  --parameters @parameters-oauth2.json
```

## Parameter Files

- `parameters-basic.json`: For basic ModelGateway connections with ApiKey authentication
- `parameters-dynamic.json`: For dynamic discovery connections with ApiKey authentication
- `parameters-static.json`: For static model list connections with ApiKey authentication
- `parameters-comprehensive.json`: For connections with all possible metadata parameters and ApiKey authentication
- `parameters-oauth2.json`: For OAuth2 authentication connections with all metadata features

Edit these files to update the resource IDs and target URLs for your environment. API keys or OAuth2 credentials will be prompted securely during deployment.

## Comprehensive Template Features

The `connection-modelgateway-comprehensive.bicep` and `connection-modelgateway-oauth2.bicep` templates support all ModelGateway connection scenarios:

1. **Basic Configuration**: Required deploymentInPath and inferenceAPIVersion
2. **Deployment API Version**: Optional deploymentAPIVersion for deployment management
3. **Dynamic Discovery**: Automatic model discovery using API endpoints (listModelsEndpoint, getModelEndpoint, deploymentProvider)
4. **Static Model List**: Predefined list of available models in staticModels array
5. **Custom Headers**: Custom HTTP headers as key-value pairs in customHeaders object
6. **Authentication Options**: 
   - **ApiKey Authentication**: Traditional API key-based authentication (comprehensive template)
   - **OAuth2 Authentication**: OAuth2 client credentials flow with configurable scopes (oauth2 template)

**Important**: Both templates include validation to prevent configuring both static models and dynamic discovery simultaneously, as these are mutually exclusive approaches.

Both templates use conditional logic to include only non-empty parameters, making them clean and flexible for any ModelGateway scenario.