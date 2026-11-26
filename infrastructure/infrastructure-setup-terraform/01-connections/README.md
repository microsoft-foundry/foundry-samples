# Connections Terraform Examples

Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

## Model gateway connections

These folders are complete Terraform configurations that you can deploy with `terraform apply`. Each one is the
Terraform version of a Bicep sample and creates the same connection from the same inputs.

| Folder | Connection | Bicep sample |
|--------|------------|--------------|
| [`apim`](./apim/) | `ApiManagement` connection to an API in Azure API Management | [`apim`](../../infrastructure-setup-bicep/01-connections/apim/) |
| [`model-gateway`](./model-gateway/) | `ModelGateway` connection to another gateway or model provider | [`model-gateway`](../../infrastructure-setup-bicep/01-connections/model-gateway/) |

Agents reference a model behind these connections as `<connection-name>/<model-name>`.

## Resource connection snippets

The `.tf` files in this folder show how to create a connection for a common connection category:

- **AI Search**: Connect to Azure AI Search (Cognitive Search) services
- **Key Vault**: Securely access secrets and keys
- **Application Insights**: Enable monitoring and telemetry
- **Azure OpenAI**: Connect to Azure OpenAI endpoints
- **Foundry**: Connect to another Microsoft Foundry resource
- **Storage Account**: Access Azure Storage for data
- **Cosmos DB**: Connect to Cosmos DB databases
- **Bing Grounding**: Enable Bing Search for grounding

The Azure OpenAI, Foundry, Cosmos DB, and Bing Grounding snippets are the Terraform versions of the Bicep samples of the
same name in [`infrastructure-setup-bicep/01-connections`](../../infrastructure-setup-bicep/01-connections/). They use
only the AzAPI provider. The Azure OpenAI, Foundry, and Bing Grounding snippets read the key at apply time and send it
as a write-only value, so it isn't stored in Terraform state or plan files; they need Terraform 1.11 or later.

## Usage

Each snippet file demonstrates how to create a specific connection type using Terraform with the AzAPI provider. These are example snippets that you can integrate into your own Terraform configurations.

## Prerequisites

- An existing Microsoft Foundry account
- The target resource you want to connect (e.g., AI Search service, Key Vault, etc.)
- Appropriate permissions to create connections

## Important Notes

- Uses AzAPI provider for connection resources (not yet in Az
ureRM)
- Some connections require API keys or managed identity configuration
- Role assignments may be needed for managed identity auth
- The service stores `isSharedToAll` as `true` on a connection on the Foundry account and as `false` on a project
  connection, whatever value is sent

## Documentation

- [Microsoft Foundry connections](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/connections)
- [AzAPI Provider](https://registry.terraform.io/providers/azure/azapi/latest/docs)

`Tags: Microsoft.CognitiveServices/accounts/connections, Integration`
