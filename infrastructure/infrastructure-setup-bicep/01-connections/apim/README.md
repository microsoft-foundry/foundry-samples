# APIM Connection Examples

This folder contains Azure Bicep templates for creating APIM (API Management) connections to Azure AI Foundry projects.

## Prerequisites

1. **Azure CLI** installed and configured
2. **Existing APIM service** with APIs configured
3. **AI Foundry account and project** already created

## How to Deploy

### Static Models APIM Connection
```bash
# 1. Modify samples/parameters-static-models.json for your requirements
# 2. Deploy using the parameters file
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-static-models.json
```

### Dynamic Discovery APIM Connection
```bash
# 1. Modify samples/parameters-dynamic-discovery.json for your requirements
# 2. Deploy using the parameters file
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-dynamic-discovery.json
```

### Custom Headers APIM Connection
```bash
# 1. Modify samples/parameters-custom-headers.json for your requirements
# 2. Deploy using the parameters file
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-custom-headers.json
```

### Custom Auth APIM Connection
```bash
# 1. Modify samples/parameters-custom-auth-config.json for your requirements
# 2. Deploy using the parameters file
az deployment group create \
  --resource-group <your-resource-group> \
  --template-file connection-apim.bicep \
  --parameters @samples/parameters-custom-auth-config.json
```

## Parameter Files

- `samples/parameters-static-models.json`: For APIM connections with predefined static model lists
- `samples/parameters-dynamic-discovery.json`: For APIM connections with dynamic model discovery (includes endpoint configurations)
- `samples/parameters-custom-headers.json`: For APIM connections with custom request headers
- `samples/parameters-custom-auth.json`: For APIM connections with custom authentication configuration

Modify these parameter files for your requirements, or create a new parameter file with comprehensive parameters.