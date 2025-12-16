# Azure AI Foundry Agent Service: Standard Agent Setup with Public Networking & Additional Customization

## Required Permissions

1. To deploy this template and create a Standard Setup project you need the follow permissions:
    * **Azure AI Account Owner**
    * **Role Based Access Administrator**

For more information on the setup process, [see the getting started documentation.](https://learn.microsoft.com/en-us/azure/ai-services/agents/environment-setup)

For more details on the standard agent setup, see the [standard agent setup concept page.](https://learn.microsoft.com/en-us/azure/ai-services/agents/concepts/standard-agent-setup)

## Limitations

* Your existing Azure OpenAI resource must be in the sample region as you deploy the template
* Your existing Azure Cosmos DB for NoSQL account used in standard setup must have a total throughput limit of **at least 3000 RU/s**. Both Provisioned Throughput and Serverless are supported.
  * Three containers will be provisioned in your existing Cosmos DB account, each requiring 1000 RU/s

## Auto deploy or manually deploy the template

Easily provision the entire standard-setup infrastructure in one of two ways:

### Option 1: Autodeploy with the “Deploy to Azure” button

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F43-standard-agent-setup-with-customization%2Fazuredeploy.json)

When the portal opens you will be asked for the parameters below.  
Leave any value blank to have the template create that resource automatically.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `projectName` | ✔︎ | A short name (letters & numbers) used to prefix resources. |
| `location` | ✔︎ | Azure region for deployment (e.g. `westus2`). |
| `existingAoaiResourceId` |  | ARM ID of an existing Azure OpenAI resource. |
| `aiStorageAccountResourceId` |  | ARM ID of an existing Storage account. |
| `cosmosDBResourceId` |  | ARM ID of an existing Cosmos DB for NoSQL account. |
| `aiSearchServiceResourceId` |  | ARM ID of an existing Azure AI Search service. |

See the next sections for instructions on how to look up these IDs.

### Option 2: Manual deployment from the CLI

1. Create (or pick) a resource group:

```bash
    az group create --name <rg-name> --location <azure-region>
```

1. Deploy the Bicep template

Pass parameters inline **or** refer to a parameter file:

> [!IMPORTANT]
> If a parameter is omitted (or left empty), the deployment creates a new resource of that type.  
> Supplying these parameters is optional.

```bash
    az deployment group create \
      --resource-group <rg-name> \
      --template-file main.bicep \
      --parameters existingAoaiResourceId=<aoai-id-if-any> \
                   aiStorageAccountResourceId=<storage-id-if-any> \
                   cosmosDBResourceId=<cosmos-id-if-any> \
                   aiSearchServiceResourceId=<search-id-if-any>
```

See more details below on how to get existing resource ids.

## Use an existing Azure OpenAI, Azure Storage account, Azure Cosmos DB for NoSQL account, and/or Azure AI Search resource 

### Use an existing Azure OpenAI resource

Replace the parameter value for `existingAoaiResourceId` with the full arm resource ID of the Azure OpenAI resource you want to use

1. To get the Azure OpenAI account resource ID, sign in to the Azure CLI and select the subscription with your AI Services account:

    ```bash
        az login
    ```

2. Replace `<your-resource-group>` with the resource group containing your resource and `your-azure-openai-resource-name` with the name of your AI Service resource, and run:

    ```bash
        az cognitiveservices account show --resource-group <your-resource-group> --name <your-ai-service-resource-name> --query "id" --output tsv
    ```

    The value returned is the `existingAoaiResourceId` you need to use in the template.

3. In the main.bicep template, replace the following placeholder:

    ```bash
        existingAoaiResourceId:/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.CognitiveServices/accounts/{serviceName}
    ```

### Use an existing Azure Storage account for file storage

1. To get your storage account resource ID, sign in to the Azure CLI and select the subscription with your storage account: 

    ```bash
        az login
    ```

2. Then run the command:

    ```bash
        az storage account show --resource-group  <your-resource-group> --name <your-storage-account>  --query "id" --output tsv```
   
     The output is the `aiStorageAccountResourceID` you need to use in the template.
   
3. In the main.bicep file, replace the following placeholders:

    ```bash
        aiStorageAccountResourceId:/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Storage/storageAccounts/{storageAccountName}
    ```

### Use an existing Azure Cosmos DB for NoSQL account for thread storage

1. To get your Azure Cosmos DB account resource ID, sign in to the Azure CLI and select the subscription with your account: 

    ```bash
    az login
    ```

2. Then run the command:

    ```bash
    az cosmosdb show --resource-group  <your-resource-group> --name <your-cosmosdb-account> --query "id" --output tsv
    ```

     The output is the `cosmosDBResourceId` you need to use in the template.
3. In the standard agent template file, replace the following placeholders:

    `cosmosDBResourceId:/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/{cosmosDbAccountName}`

### Use an existing Azure AI Search resource

1. To get your Azure AI Search resource ID, sign into Azure CLI and select the subscription with your search resource: 

    ```bash
        az login
    ```

2. Then run the command:

    ```bash
        az search service show --resource-group  <your-resource-group> --name <your-search-service> --query "id" --output tsv
    ```

3. In the standard agent template file, replace the following placeholders:

    ```bash
        aiSearchServiceResourceId:/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Search/searchServices/{searchServiceName}
    ```
