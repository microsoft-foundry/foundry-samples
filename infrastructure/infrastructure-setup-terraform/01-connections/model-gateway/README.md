# ModelGateway connection (Terraform)

This is the Terraform version of the
[Bicep ModelGateway connection sample](../../../infrastructure-setup-bicep/01-connections/model-gateway/).
It creates a `ModelGateway` connection on an existing Microsoft Foundry project, so prompt agents in the
project can use models from another gateway or model provider as `<connection-name>/<model-name>`.

Given the same inputs, it creates the same connection as `connection-modelgateway.bicep`. Each file in
[`samples`](./samples/) has the same inputs as one of the Bicep sample parameter files.

Before you deploy, use the Bicep sample's
[setup guide](../../../infrastructure-setup-bicep/01-connections/model-gateway/modelgateway-setup-guide-for-agents.md)
to collect your gateway's settings, such as `deployment_in_path` and `inference_api_version`. The
[connection objects reference](../../../infrastructure-setup-bicep/01-connections/model-gateway/ModelGateway-Connection-Objects.md)
describes each metadata field. If agent calls fail, see the
[troubleshooting guide](../../../infrastructure-setup-bicep/01-connections/model-gateway/troubleshooting-guide.md).

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) 1.11 or later.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), signed in with `az login`.
- An existing Foundry project, and permission to create connections on it.

## Deploy

1. Select the subscription that contains the project:

   ```shell
   az account set --subscription <subscription-id>
   ```

2. From this directory, copy the sample for your scenario to `terraform.tfvars`, and then replace its
   `YOUR-...` values:

   ```shell
   cp samples/static.tfvars.example terraform.tfvars
   ```

3. Set the gateway's API key in an environment variable. For OAuth2, set `TF_VAR_client_secret` instead.

   ```powershell
   # PowerShell
   $env:TF_VAR_api_key = "<api-key>"
   ```

   ```bash
   # bash
   export TF_VAR_api_key="<api-key>"
   ```

4. Create the connection:

   ```shell
   terraform init
   terraform apply
   ```

The API key and client secret are
[ephemeral variables](https://developer.hashicorp.com/terraform/language/values/variables#exclude-values-from-state)
that Terraform sends as write-only values, so they aren't stored in Terraform state or plan files.

## Samples

| Sample | Scenario | Bicep parameter file |
| --- | --- | --- |
| `openai.tfvars.example` | OpenAI, with dynamic model discovery and the key sent as a bearer token | `parameters-openai.json` |
| `foundry-azureai.tfvars.example` | Models in another Foundry account, through its Azure AI model inference endpoint | `parameters-foundryazureai.json` |
| `foundry-openai.tfvars.example` | Azure OpenAI deployments in another Foundry account | `parameters-foundryopenai.json` |
| `foundry-anthropic.tfvars.example` | Anthropic deployments in another Foundry account | `parameters-foundryanthropic.json` |
| `responses.tfvars.example` | Responses API requests sent upstream to an Azure OpenAI v1 endpoint | `parameters-responses.json` |
| `dynamic.tfvars.example` | Dynamic model discovery, with custom headers | `parameters-dynamic.json` |
| `static.tfvars.example` | A static list of models | `parameters-static.json` |
| `custom-auth-config.tfvars.example` | A custom header for the key, plus custom request headers | `parameters-custom-auth-config.json` |
| `oauth2.tfvars.example` | OAuth2 client credentials, with custom headers | `parameters-oauth2.json` |

The `responses` sample needs the connected-model Responses API preview in your environment. For more
information, see the Bicep sample's
[upstream Responses API section](../../../infrastructure-setup-bicep/01-connections/model-gateway/README.md#upstream-responses-api-connection).

## Variables

| Variable | Bicep parameter | Default | Description |
| --- | --- | --- | --- |
| `project_resource_id` | `projectResourceId` | Required | Resource ID of the Foundry project. |
| `target_url` | `targetUrl` | Required | Base URL of the gateway or provider. Don't append `/chat/completions`, `/responses`, or a deployment path. |
| `connection_name` | `connectionName` | `modelgateway-<gateway_name>-comprehensive` | Connection name. |
| `gateway_name` | `gatewayName` | `example-gateway` | Used only to generate the default connection name. |
| `auth_type` | `authType` | `ApiKey` | `ApiKey` or `OAuth2`. |
| `api_key` | `apiKey` | None | API key, for `ApiKey`. Set it with `TF_VAR_api_key`. |
| `client_id` | `clientId` | `""` | Client ID, for `OAuth2`. |
| `client_secret` | `clientSecret` | None | Client secret, for `OAuth2`. Set it with `TF_VAR_client_secret`. |
| `token_url` | `tokenUrl` | `""` | Token endpoint, for `OAuth2`. |
| `scopes` | `scopes` | `[]` | Scopes, for `OAuth2`. |
| `is_shared_to_all` | `isSharedToAll` | `false` | Share the connection with all users of the project. The service stores `false` on a project connection, whatever value is sent. |
| `deployment_in_path` | `deploymentInPath` | `false` | `true` if the gateway expects the deployment name in the URL path. |
| `inference_api_version` | `inferenceAPIVersion` | `""` | `api-version` for inference calls, if the gateway needs one. |
| `deployment_api_version` | `deploymentAPIVersion` | `""` | `api-version` for dynamic discovery calls, if the gateway needs one. |
| `upstream_surface` | `upstreamSurface` | `""` | Set to `responses` to send Responses API requests upstream. |
| `model_discovery` | `listModelsEndpoint`, `getModelEndpoint`, `deploymentProvider` | `null` | Discovery endpoints. Set this or `static_models`. |
| `static_models` | `staticModels` | `[]` | Models the connection exposes. Set this or `model_discovery`. |
| `custom_headers` | `customHeaders` | `{}` | Extra request headers. Don't put secrets here: they're stored in the connection's metadata. |
| `auth_config` | `authConfig` | `{}` | How to send the key, such as the header name and format. |
| `credential_version` | None | `"1"` | Change it after you rotate the key or client secret. |

The configuration checks your settings at `terraform plan`. For example, it fails if you set both
`static_models` and `model_discovery`, set neither, or leave out the key for your authentication type.

## Outputs

| Output | Description |
| --- | --- |
| `connection_name` | Connection name. Agents reference a model as `<connection_name>/<model-name>`. |
| `connection_id` | Resource ID of the connection. |
| `target_url` | Base URL that the connection calls. |
| `metadata` | Metadata sent with the connection. |
| `has_static_models`, `has_model_discovery`, `has_custom_headers` | Which optional settings the connection uses. |

## Differences from the Bicep template

- Invalid settings fail at `terraform plan`, before anything is created. The Bicep template creates a
  deployment script that fails the deployment.
- `deployment_in_path` is a boolean instead of the strings `'true'` and `'false'`, and the three
  discovery parameters are one `model_discovery` object.
- Terraform sorts the keys of the JSON values that it writes to the metadata. The values are the same.
- Terraform doesn't store the key or client secret, so it can't detect a new value. After you rotate
  one, change `credential_version` and apply: Terraform replaces the connection to send the new value.

## Use the model from an agent

A `ModelGateway` model works only with a prompt agent invoked through the Responses API. To create an
agent that uses the model, run the connection-agnostic
[`create-agent.py`](../../../infrastructure-setup-bicep/01-connections/public-byom-apim/samples/create-agent.py)
script with `--model <connection-name>/<model-name>`. For details, see the
[Bicep sample](../../../infrastructure-setup-bicep/01-connections/model-gateway/README.md#after-deployment--create-an-agent-that-uses-the-model).

## Clean up

```shell
terraform destroy
```
