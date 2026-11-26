# API Management connection (Terraform)

This is the Terraform version of the
[Bicep API Management connection sample](../../../infrastructure-setup-bicep/01-connections/apim/).
It creates an `ApiManagement` connection from an existing Microsoft Foundry project to an API in Azure
API Management (APIM), so prompt agents in the project can use the models behind that API as
`<connection-name>/<model-name>`.

Given the same inputs, it creates the same connection as `connection-apim.bicep`. Each file in
[`samples`](./samples/) has the same inputs as one of the Bicep sample parameter files.

The connection targets the APIM gateway URL plus the API's path, which Terraform reads from your APIM
service. With `ApiKey` authentication, Terraform reads the APIM subscription key at apply time and sends
it as a write-only value, so the key isn't stored in Terraform state or plan files.

Before you deploy, configure your APIM API by following the Bicep sample's
[setup guide](../../../infrastructure-setup-bicep/01-connections/apim/apim-setup-guide-for-agents.md), and
collect its settings, such as `api_name`, `deployment_in_path`, and `inference_api_version`. The
[connection objects reference](../../../infrastructure-setup-bicep/01-connections/apim/APIM-Connection-Objects.md)
describes each metadata field. If agent calls fail, see the
[troubleshooting guide](../../../infrastructure-setup-bicep/01-connections/apim/troubleshooting-guide.md).

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) 1.11 or later.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), signed in with `az login`.
- An existing Foundry project, and permission to create connections on it.
- An APIM service with the API configured. The service can be in another resource group or subscription.
- Permission to read the APIM service and API. For `ApiKey`, you also need permission to read the
  subscription's keys (`Microsoft.ApiManagement/service/subscriptions/listSecrets/action`), which the
  **API Management Service Contributor** role includes.

## Deploy

1. Select the subscription that contains the project:

   ```shell
   az account set --subscription <subscription-id>
   ```

2. From this directory, copy the sample for your scenario to `terraform.tfvars`, and then replace its
   `YOUR-...` values:

   ```shell
   cp samples/static-models.tfvars.example terraform.tfvars
   ```

3. Create the connection:

   ```shell
   terraform init
   terraform apply
   ```

## Samples

| Sample | Scenario | Bicep parameter file |
| --- | --- | --- |
| `static-models.tfvars.example` | A static list of models, authenticated with the subscription key | `parameters-static-models.json` |
| `dynamic-discovery.tfvars.example` | Dynamic model discovery through the API's list and get deployment operations | `parameters-dynamic-discovery.json` |
| `custom-headers.tfvars.example` | Custom request headers | `parameters-custom-headers.json` |
| `custom-auth-config.tfvars.example` | A custom header for the subscription key | `parameters-custom-auth-config.json` |
| `managed-identity-static-models.tfvars.example` | Project managed identity authentication instead of a subscription key | `parameters-managed-identity-static-models.json` |

## Variables

| Variable | Bicep parameter | Default | Description |
| --- | --- | --- | --- |
| `project_resource_id` | `projectResourceId` | Required | Resource ID of the Foundry project. |
| `apim_resource_id` | `apimResourceId` | Required | Resource ID of the APIM service. |
| `api_name` | `apiName` | Required | Name of the API in APIM. |
| `connection_name` | `connectionName` | `apim-<service-name>-<api_name>` | Connection name. |
| `apim_subscription_name` | `apimSubscriptionName` | `master` | APIM subscription whose primary key the connection uses, for `ApiKey`. |
| `auth_type` | `authType` | `ApiKey` | `ApiKey` or `ProjectManagedIdentity`. |
| `is_shared_to_all` | `isSharedToAll` | `false` | Share the connection with all users of the project. The service stores `false` on a project connection, whatever value is sent. |
| `deployment_in_path` | `deploymentInPath` | `true` | `true` if the API expects the deployment name in the URL path. |
| `inference_api_version` | `inferenceAPIVersion` | `""` | `api-version` for inference calls, if the API needs one. |
| `deployment_api_version` | `deploymentAPIVersion` | `""` | `api-version` for dynamic discovery calls, if the API needs one. |
| `model_discovery` | `listModelsEndpoint`, `getModelEndpoint`, `deploymentProvider` | `null` | Discovery endpoints. Set this or `static_models`. |
| `static_models` | `staticModels` | `[]` | Models the connection exposes. Set this or `model_discovery`. |
| `custom_headers` | `customHeaders` | `{}` | Extra request headers. Don't put secrets here: they're stored in the connection's metadata. |
| `auth_config` | `authConfig` | `{}` | How to send the subscription key, such as the header name and format. |
| `credential_version` | None | `"1"` | Change it after you rotate the APIM subscription key. |

The configuration checks your settings at `terraform plan`. For example, it fails if you set both
`static_models` and `model_discovery`, or neither.

## Outputs

| Output | Description |
| --- | --- |
| `connection_name` | Connection name. Agents reference a model as `<connection_name>/<model-name>`. |
| `connection_id` | Resource ID of the connection. |
| `target_url` | APIM gateway URL plus the API's path. |
| `auth_type` | Authentication type of the connection. |
| `metadata` | Metadata sent with the connection. |
| `has_static_models`, `has_model_discovery`, `has_custom_headers` | Which optional settings the connection uses. |

## Differences from the Bicep template

- Invalid settings fail at `terraform plan`, before anything is created. The Bicep template creates a
  deployment script that fails the deployment.
- `deployment_in_path` is a boolean instead of the strings `'true'` and `'false'`, and the three
  discovery parameters are one `model_discovery` object.
- Terraform sorts the keys of the JSON values that it writes to the metadata. The values are the same.
- Terraform doesn't store the subscription key, so it can't detect a new key. After you rotate it, change
  `credential_version` and apply: Terraform replaces the connection to send the new key.

## Use the model from an agent

An `ApiManagement` model works only with a prompt agent invoked through the Responses API. To create an
agent that uses the model, run the connection-agnostic
[`create-agent.py`](../../../infrastructure-setup-bicep/01-connections/public-byom-apim/samples/create-agent.py)
script with `--model <connection-name>/<model-name>`.

## Clean up

```shell
terraform destroy
```
