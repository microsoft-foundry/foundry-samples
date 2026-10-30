# Azure AI Agent Service: Basic Setup Using an Existing Azure OpenAI Resource

This Bicep template provisions the required resources for a basic agent project. It creates a new Cognitive Services Account and project, and connects your existing Azure OpenAI resource for model deployments.

> **Important:** You must provide the **resource ID** of your existing Azure OpenAI resource when deploying this template.
> **Temporary Limitation:** The Azure OpenAI resource must be in the same region as your Foundry account and project.

All agents created in this project will automatically use Microsoft-managed, multitenant search and storage resources.
---

## Prerequisites

1. **Azure roles**  
   - To deploy the template: **Foundry Account Owner** or **Contributor**  
   - To create your first agent: **Foundry User**
2. **Existing Azure OpenAI resource** – you must already have one.  

    Get the resource id in **Azure Portal**
    ![Azure BYO Example](./azurebyo.PNG)
---

## Deployment options

Below are two supported approaches.

### 1 — Deploy from the Azure portal (one-click)

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F42-basic-agent-setup-with-customization%2Fazuredeploy.json)

Click the button, then complete the portal wizard.  
Replace **existingAoaiResourceId** with the resource id of your Azure OpenAI resource.

### 2 — Deploy with the Azure CLI

```bash
# sign in and pick the subscription
az login

# create (or reuse) a resource group
az group create --name <rg-name> --location eastus

# deploy
az deployment group create \
  --resource-group <rg-name> \
  --template-file main.bicep \
  --parameters existingAoaiResourceId='/subscriptions/<sub-id>/resourceGroups/<rg-name>/providers/Microsoft.CognitiveServices/accounts/<aoai-name>' \
               account_name='foundry' \
               project_name='myProject'
```

## Agent tracing & evaluation (Application Insights)

By default (`deployApplicationInsights = true`) this template also:

- Deploys a **Log Analytics workspace** and a **workspace-based Application Insights** component and connects it to the Foundry account, so agents export OpenTelemetry traces.
- Grants the **project managed identity** **Log Analytics Reader** and **Privileged Monitoring Data Reader** on the component so evaluation can read traces, including GenAI prompt/response content.

**Additional deployment permission:** with `deployApplicationInsights=true` (the default), the deploying identity also needs `Microsoft.Authorization/roleAssignments/write` on the Application Insights component or an ancestor scope, for example **Owner**, or **Contributor** plus **Role Based Access Control Administrator** at the resource-group scope. **Contributor** alone is not sufficient for the default deployment.

This adds Log Analytics / Application Insights cost. Deploy with `deployApplicationInsights=false` to skip
all tracing resources and RBAC:

```bash
az deployment group create --resource-group <rg> --template-file main.bicep \
  --parameters existingAoaiResourceId='/subscriptions/<sub-id>/resourceGroups/<rg-name>/providers/Microsoft.CognitiveServices/accounts/<aoai-name>' \
               deployApplicationInsights=false
```
