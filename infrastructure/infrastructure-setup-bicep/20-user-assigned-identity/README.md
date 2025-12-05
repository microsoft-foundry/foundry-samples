---
description: This template deploys an Azure AI Foundry account, project, and model deployment with your User-Assigned Managed Identity.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: aifoundry-uai
languages:
- bicep
- json
---
# Set up Azure AI Foundry with user-assigned identity

This Azure AI Foundry template is built on Azure Cognitive Services as a resource provider. This template deploys an Azure AI Foundry account and project, previously known as Azure AI Services.

Run the command for BICEP:

az deployment group create --name "{DEPLOYMENT_NAME}" --resource-group "{RESOURCE_GROUP_NAME}" --template-file ./main.bicep --parameters  userAssignedIdentityName="{UASER_ASSIGNED_MANAGED_IDENTITY_NAME}" 

Limitations:
1. User-Assigned Managed Identity is not supported with Customer Managed Keys.

If you are new to Azure AI Foundry, see:

- [Azure AI Foundry](https://learn.microsoft.com/azure/ai-foundry/)

If you are new to template deployment, see:

- [Azure Resource Manager documentation](https://learn.microsoft.com/azure/azure-resource-manager/)
- [Azure AI services quickstart article](https://learn.microsoft.com/azure/cognitive-services/resource-manager-template)

`Tags: Microsoft.CognitiveServices/accounts/projects`