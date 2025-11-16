# ModelGateway Connection Examples

This folder contains Azure Bicep templates for creating ModelGateway connections to Azure AI Foundry projects.

## ⚠️ Important Notice

**ModelGateway connections are currently not supported in Azure AI Foundry.** These templates are provided as examples for future use when ModelGateway support becomes available.

## Prerequisites

1. **Azure CLI** installed and configured
2. **AI Foundry account and project** already created

## How to Deploy (When Supported)

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

## Parameter Files

- `parameters-basic.json`: For basic ModelGateway connections
- `parameters-dynamic.json`: For dynamic discovery connections
- `parameters-static.json`: For static model list connections
- `parameters-comprehensive.json`: For connections with all possible metadata parameters

Edit these files to update the resource IDs and target URLs for your environment. API keys will be prompted securely during deployment.

## Comprehensive Template Features

The `connection-modelgateway-comprehensive.bicep` template supports all ModelGateway connection scenarios:

1. **Basic Configuration**: Required deploymentInPath and inferenceAPIVersion
2. **Deployment API Version**: Optional deploymentAPIVersion for deployment management
3. **Dynamic Discovery**: Automatic model discovery using API endpoints (listModelsEndpoint, getModelEndpoint, deploymentProvider)
4. **Static Model List**: Predefined list of available models in staticModels array
5. **Custom Headers**: Custom HTTP headers as key-value pairs in customHeaders object

**Important**: The template includes validation to prevent configuring both static models and dynamic discovery simultaneously, as these are mutually exclusive approaches.

The template uses conditional logic to include only non-empty parameters, making it clean and flexible for any ModelGateway scenario.