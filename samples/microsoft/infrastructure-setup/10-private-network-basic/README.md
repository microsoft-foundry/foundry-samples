# Deploy AI Foundry with a private network configuration

> **NOTE:** This examples shows how to disable public network access for Azure AI Foundry. This template includes: 
* PNA disabled Foundry resource (account) with private endpoint 


## Steps 

1. Create new (or use existing) resource group:

```bash
    az group create --name <new-rg-name> --location <your-selected-region>
```

2. Deploy the main.bicep

```bash
    az deployment group create --resource-group <new-rg-name> --template-file main.bicep
```

**NOTE:** To access your Foundry resource securely, please using either a VM, VPN, or ExpressRoute.