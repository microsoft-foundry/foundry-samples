---
description: This template deploys an Azure AI Foundry project.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: aifoundry-basic-project
languages:
- bicep
- json
---
# Deploy an Azure AI Foundry project

This Azure AI Foundry template is built on Azure Cognitive Services as a resource provider. This template deploys an Azure AI Foundry resource and project. This allows you to access AI Foundry capabilities like Agents, Evaluations, Tracing, etc.

The `location` parameter defaults to the resource group's region. Choose a region
with the required Foundry features and quota, or override `location` at deployment.

If you are new to Azure AI Foundry, see:

- [Azure AI Foundry](https://learn.microsoft.com/azure/ai-foundry/)

If you are new to template deployment, see:

- [Azure Resource Manager documentation](https://learn.microsoft.com/azure/azure-resource-manager/)
- [Azure AI services quickstart article](https://learn.microsoft.com/azure/cognitive-services/resource-manager-template)

`Tags: Microsoft.CognitiveServices/accounts/projects`

<!-- CI validation marker for infrastructure sample changes. -->