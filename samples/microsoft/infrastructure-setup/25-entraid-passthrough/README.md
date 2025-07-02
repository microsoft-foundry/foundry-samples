# Azure AI Agent Service: Standard Agent Setup 1RP with Private E2E Networking 

> **NOTE:** This template is to set-up a connection to a storage account and assign entraID passthrough for your storage resource. This includes creating: 
* a Foundry resource
* A storage account (the one other resource to connect to)
* Azure storage connection with EntraID passthrough auth
* Storage Blob Data Owner role assignment for project MSI on storage

## Steps 

1. Create new (or use existing) resource group:

```bash
    az group create --name <new-rg-name> --location eastus
```

2. Deploy the main-create.bicep

```bash
    az deployment group create --resource-group <new-rg-name> --template-file main.bicep
```
