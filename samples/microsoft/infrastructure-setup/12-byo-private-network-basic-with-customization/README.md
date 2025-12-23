# BYO Azure OpenAI AI Foundry Deployment (Existing VNet)

This directory contains a Bicep template (`main.bicep`) that deploys an Azure AI Foundry account with private networking while reusing an existing virtual network and private endpoint subnet. The template links the account to an existing Azure OpenAI resource through a project connection and configures capability hosts so the project can use that connection.

## What the template deploys
- **AI Foundry account** (`Microsoft.CognitiveServices/accounts`) with `AIServices` kind, system-assigned identity, and public network access disabled.
- **Private endpoint** to the AI Foundry account plus private DNS zones (`privatelink.services.ai.azure.com`, `privatelink.openai.azure.com`, `privatelink.cognitiveservices.azure.com`) linked to your existing VNet.
- **Project** inside the Foundry account with a BYO Azure OpenAI connection (`connections@2025-04-01-preview`).
- **Capability hosts** at both account and project scope so the project can use the BYO connection.
- **Sample model deployment** (`gpt-4o-mini`) inside the AI Foundry account for validation.

## Required inputs
Collect the following resource IDs:
- Existing virtual network: `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>`
- Subnet dedicated to Private Link endpoints: `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet>`
- Existing Azure OpenAI account: `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<aoai>`

Ensure the subnet has private endpoint network policies disabled before deployment.

## Deploy
1. Create or select a resource group in a supported region:
   ```bash
   az group create --name <rg-name> --location <region>
   ```
2. Deploy the template, providing the resource IDs collected above. You can edit `main.parameters.json` or pass values inline:
   ```bash
   az deployment group create \
     --resource-group <rg-name> \
     --template-file main.bicep \
     --parameters \
       existingVnetResourceId="/subscriptions/<...>/virtualNetworks/<...>" \
       existingPeSubnetResourceId="/subscriptions/<...>/subnets/<...>" \
       existingAoaiResourceId="/subscriptions/<...>/accounts/<...>"
   ```

## Outputs
The deployment emits the Foundry account ID, name, endpoint, project name, and the fully qualified resource ID of the project connection (`projectConnectionName`).

## Notes
- The template does not modify VNet settings; confirm the subnet is configured for Private Link and that required route/firewall rules exist.
- Private DNS zones are created in the deployment resource group and linked to your VNet. Skip linking if your environment already centralizes these zones.
- Access to the AI Foundry endpoint requires connectivity to the specified virtual network.
