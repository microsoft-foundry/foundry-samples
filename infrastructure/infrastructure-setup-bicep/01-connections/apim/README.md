# APIM Connection Examples

This folder contains Azure Bicep templates for creating APIM (API Management) connections to Azure AI Foundry projects.

> **⚠️ IMPORTANT**: Before running any deployment, follow the [Setup Guide](./apim-setup-guide-for-agents.md) guide to properly configure your APIM service and obtain all applicable parameters. If you encounter issues, see the [Troubleshooting Guide](./troubleshooting-guide.md). Make sure to collect these parameters to avoid 404/400/ResourceNotFound/DeploymentNotFound errors during Agent API execution:
> 1. **inferenceApiVersion** - The API version for chat completions calls if api-version is required.
> 2. **deploymentApiVersion** - The API version for deployment operations (list and get deployment operations) if using dynamic discovery and api-version is required. 
> 3. **apiName** - The name of your API in APIM (e.g., "foundry", "openai")
> 4. **deploymentInPath** - Whether deployment ID is in the URL path or in body as model field in chat completions API call.
>
> These parameters must match your actual APIM configuration to ensure successful deployments.

## 📚 Documentation

- **[Setup Guide](./apim-setup-guide-for-agents.md)** - Complete configuration guide for APIM connections
- **[Troubleshooting Guide](./troubleshooting-guide.md)** - Common issues and solutions with validation script usage

## Prerequisites

1. **Azure CLI** installed and configured
2. **Existing APIM service** with APIs configured
3. **AI Foundry account and project** already created

## How to Deploy

### Static Models APIM Connection
```bash
# 1. Edit samples/parameters-static-models.json with your resource IDs
# 2. Deploy (API key automatically retrieved from APIM service)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-static-models.json
```

### Dynamic Discovery APIM Connection
```bash
# 1. Follow the apim-setup-guide-for-agents.md to configure both list and get endpoints in APIM
# 2. Edit samples/parameters-dynamic-discovery.json with your resource IDs
# 3. Deploy (API key automatically retrieved from APIM service)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-dynamic-discovery.json
```

### Custom Headers APIM Connection
```bash
# 1. Edit samples/parameters-custom-headers.json with your resource IDs
# 2. Deploy (API key automatically retrieved from APIM service)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-custom-headers.json
```

### Custom Auth APIM Connection
```bash
# 1. Edit samples/parameters-custom-auth-config.json with your resource IDs
# 2. Deploy (API key automatically retrieved from APIM service)
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-custom-auth-config.json
```

## Validation Features

The template includes built-in validation:
- **Invalid Configuration**: Fails with "ERROR: Cannot configure both static models and dynamic discovery."
- **Missing Configuration**: Fails with "ERROR: Must configure either static models (staticModels array) OR dynamic discovery (listModelsEndpoint, getModelEndpoint, deploymentProvider). Cannot have neither."

## Parameter Files

- `samples/parameters-static-models.json`: For APIM connections with predefined static model lists
- `samples/parameters-dynamic-discovery.json`: For APIM connections with dynamic model discovery (includes endpoint configurations)
- `samples/parameters-custom-headers.json`: For APIM connections with custom request headers
- `samples/parameters-custom-auth-config.json`: For APIM connections with custom authentication configuration

Edit these files to update the resource IDs and configuration for your environment.