# BYO Azure OpenAI AI Foundry Deployment (Private Networking)

This directory contains a single Bicep template (`main.bicep`) that provisions an Azure AI Foundry account with public access disabled, wires it to a private virtual network, and links the account to an existing Azure OpenAI resource using a connection and capability hosts.

## What the template deploys
- **AI Foundry account** (`Microsoft.CognitiveServices/accounts`) with `AIServices` kind, system-assigned identity, and public network access disabled.
- **Virtual network and subnet** sized for private endpoints with network policies disabled to allow Private Link.
- **Private endpoint** to the AI Foundry account plus private DNS zones (`privatelink.services.ai.azure.com`, `privatelink.openai.azure.com`, `privatelink.cognitiveservices.azure.com`) and links to the VNet.
- **Project** inside the Foundry account with a BYO Azure OpenAI connection (`connections@2025-04-01-preview`).
- **Capability hosts** at both account and project scope so the project can use the BYO connection.
- **Sample model deployment** (`gpt-4o-mini`) inside the AI Foundry account for validation.

## Required inputs
Provide the ID of an existing Azure OpenAI resource that resides in a private network-capable region:
```
/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<aoai-account>
```

You may optionally override defaults such as the base account name, project metadata, or VNet address space through parameters.

## Deploy
1. Create or select a resource group in a supported region:
   ```bash
   az group create --name <rg-name> --location <region>
   ```
2. Deploy the Bicep file, providing the existing Azure OpenAI resource ID. You can use the provided `main.parameters.json` as an example and update the parameter values, or pass them inline:
   ```bash
   az deployment group create \
     --resource-group <rg-name> \
     --template-file main.bicep \
     --parameters existingAoaiResourceId="/subscriptions/<...>/accounts/<...>"
   ```

## Outputs
The deployment surfaces the Foundry account ID, name, endpoint, project name, and the fully qualified resource ID of the project connection (`projectConnectionName`).

## Notes
- Ensure the private subnet range does not overlap with on-premises or other VNets linked to your environment.
- Deployments from machines outside the private network will not be able to reach the Foundry endpoint unless routed through VPN, ExpressRoute, or a jump host in the VNet.
