# Azure AI Foundry Agent Service: Standard Agent Setup with Public Networking

## Required Permissions
1. To deploy this template and create a Standard Setup project you need the follow permissions:
    * **Azure AI Account Owner**
    * **Role Based Access Administrator**

For more information on the setup process, [see the getting started documentation.](https://learn.microsoft.com/en-us/azure/ai-services/agents/environment-setup)

For more details on the standard agent setup, see the [standard agent setup concept page.](https://learn.microsoft.com/en-us/azure/ai-services/agents/concepts/standard-agent-setup)

## Steps

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Fsamples%2Fmicrosoft%2Finfrastructure-setup%2F41-standard-agent-setup%2Fazuredeploy.json)

1. Create new (or use existing) resource group:

```bash
    az group create --name <new-rg-name> --location westus
```

2. Deploy the template

```bash
    az deployment group create --resource-group <new-rg-name> --template-file main.bicep
```

## Use exitsing resources

**Azure Cosmos DB for NoSQL**
- Your existing Azure Cosmos DB for NoSQL Account used in standard setup must have at least a total throughput limit of at least 3000 RU/s. Both Provisioned Thoughtput and Serverless are supported.
    - 3 containers will be provisioned in your existing Cosmos DB account and each need 1000 RU/s
