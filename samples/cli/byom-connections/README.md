# Create bring-your-own-model connections with the Azure Developer CLI

Use `azd ai connection` to connect a Microsoft Foundry project to models behind your own gateway, also called
bring your own model (BYOM). After you create the connection, agents use a model as
`<connection-name>/<model-name>`.

These scripts are the command-line alternative to the Bicep templates in
[`infrastructure-setup-bicep/01-connections`](../../../infrastructure/infrastructure-setup-bicep/01-connections/).
They create the same project connections.

| Your gateway | Script | Connection category | Authentication | Bicep equivalent |
|---|---|---|---|---|
| A model gateway or provider with an OpenAI-compatible API, such as LiteLLM, Kong, OpenAI, or another Foundry resource | `create-model-gateway-connection` | `ModelGateway` | API key | [`model-gateway`](../../../infrastructure/infrastructure-setup-bicep/01-connections/model-gateway/) |
| An API in Azure API Management (APIM), with a subscription key | `create-apim-connection` | `ApiManagement` | API key | [`apim`](../../../infrastructure/infrastructure-setup-bicep/01-connections/apim/) |
| An API in Azure API Management, keyless | `create-apim-connection` with `AUTH_TYPE=project-managed-identity` | `ApiManagement` | Project managed identity | [`public-byom-apim`](../../../infrastructure/infrastructure-setup-bicep/01-connections/public-byom-apim/) |

Each script has a Bash (`.sh`) and a PowerShell (`.ps1`) version in [`scripts`](./scripts/). Azure AI Gateway
connections aren't covered here; use the
[`ai-gateway-tier`](../../../infrastructure/infrastructure-setup-bicep/01-connections/ai-gateway-tier/) template.

## Prerequisites

- [Azure Developer CLI](https://aka.ms/azd) 1.37.0 or later, with the Foundry Connections extension 1.0.1 or later:

  ```bash
  azd extension install azure.ai.connections
  ```

- Bash, or PowerShell 7.3 or later.
- A Foundry project, and permission to create connections in it, such as **Contributor** on the Foundry resource.
  To run agents with the connection, you also need **Foundry User** on the project.
- The model's gateway, and the details the connection needs: the base URL, the model name, and a key or keyless
  access.

Sign in with `azd auth login`. To reuse your Azure CLI sign-in instead, run
`azd config set auth.useAzCliAuth true`.

## Set the common variables

Every script reads its inputs from environment variables, so keys never appear in the script.

| Variable | Required | Description |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | The project endpoint, such as `https://<resource>.services.ai.azure.com/api/projects/<project>`. |
| `CONNECTION_NAME` | Yes | The name of the new connection. Agents use it as the first part of `<connection-name>/<model-name>`. |
| `MODEL_DEPLOYMENT_NAME` | Yes | The model name that the gateway exposes. Agents use it as the second part of the model reference. |
| `MODEL_NAME` | No | The underlying model name. Defaults to `MODEL_DEPLOYMENT_NAME`. |
| `MODEL_VERSION` | No | The model version, such as `2025-08-07`. |
| `MODEL_FORMAT` | No | The model format. Defaults to `OpenAI`. |
| `DEPLOYMENT_IN_PATH` | No | `true` if the gateway expects `/deployments/<model>/` in the URL path; `false` if the model goes in the request body. Defaults to `false` for a model gateway and `true` for APIM. |
| `INFERENCE_API_VERSION` | No | The `api-version` query parameter for inference calls, if the gateway requires one. |

## Connect to a model gateway

Set `GATEWAY_URL` to the gateway's base URL, without an operation path such as `/chat/completions`, and set the key.

Bash:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export CONNECTION_NAME="my-gateway"
export GATEWAY_URL="https://<your-gateway>/v1"
export MODEL_DEPLOYMENT_NAME="gpt-4o"
read -rsp "Gateway API key: " GATEWAY_API_KEY && export GATEWAY_API_KEY && echo

./scripts/create-model-gateway-connection.sh
```

PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<resource>.services.ai.azure.com/api/projects/<project>"
$env:CONNECTION_NAME = "my-gateway"
$env:GATEWAY_URL = "https://<your-gateway>/v1"
$env:MODEL_DEPLOYMENT_NAME = "gpt-4o"
$env:GATEWAY_API_KEY = Read-Host "Gateway API key" -MaskInput

./scripts/create-model-gateway-connection.ps1
```

For an Azure OpenAI deployment in another Foundry resource, use
`GATEWAY_URL=https://<resource>.openai.azure.com/openai`, `DEPLOYMENT_IN_PATH=true`, and an `INFERENCE_API_VERSION`
such as `2025-03-01-preview`.

## Connect to Azure API Management

Set `APIM_API_URL` to the APIM gateway URL plus the API's path. You can read both with the Azure CLI:

```bash
gateway_url=$(az apim show --resource-group <apim-rg> --name <apim-name> --query gatewayUrl --output tsv)
api_path=$(az apim api show --resource-group <apim-rg> --service-name <apim-name> --api-id <api-id> --query path --output tsv)
export APIM_API_URL="$gateway_url/$api_path"
```

### With a subscription key

```bash
export APIM_SUBSCRIPTION_KEY=$(az rest --method post \
  --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<apim-rg>/providers/Microsoft.ApiManagement/service/<apim-name>/subscriptions/<apim-subscription>/listSecrets?api-version=2024-05-01" \
  --query primaryKey --output tsv)

./scripts/create-apim-connection.sh
```

In PowerShell, set the same variables with `$env:` and run `./scripts/create-apim-connection.ps1`.

### Keyless, with the project's managed identity

Foundry calls APIM with a token for the project's managed identity, so no key is stored. The API must accept that
token:

- Validate it with a `validate-azure-ad-token` policy. Set the audience to `https://cognitiveservices.azure.com` and
  the client application ID to the project identity's application ID.
- Call the backend model with APIM's own managed identity, for example with `authentication-managed-identity`.

The [`public-byom-apim`](../../../infrastructure/infrastructure-setup-bicep/01-connections/public-byom-apim/)
template configures an API this way.

```bash
export AUTH_TYPE=project-managed-identity
./scripts/create-apim-connection.sh
```

To use a different token audience, set `TOKEN_AUDIENCE`.

## What the scripts send

The scripts run `azd ai connection create` with these settings:

| Setting | Value |
|---|---|
| `--kind` | `ModelGateway` or `ApiManagement` |
| `--target` | `GATEWAY_URL` or `APIM_API_URL` |
| `--auth-type` | `api-key` with `--key`, or `project-managed-identity` with `--audience` |
| `--metadata deploymentInPath=...` | `DEPLOYMENT_IN_PATH` |
| `--metadata inferenceAPIVersion=...` | `INFERENCE_API_VERSION` (always for a model gateway; only when set for APIM, as in the Bicep templates) |
| `--metadata models=...` | A JSON list with one model, built from the `MODEL_*` variables |

To add a model or another setting, such as `customHeaders` or `authConfig`, run `azd ai connection create` yourself
with more `--metadata key=value` entries. JSON values are accepted. For every setting, see
[ModelGateway connection objects](../../../infrastructure/infrastructure-setup-bicep/01-connections/model-gateway/ModelGateway-Connection-Objects.md)
and [APIM connection objects](../../../infrastructure/infrastructure-setup-bicep/01-connections/apim/APIM-Connection-Objects.md).

## Use the model in an agent

Reference the model as `<connection-name>/<model-name>`, for example `my-gateway/gpt-4o`, in a prompt agent that you
call through the Responses API. To try it, run the
[connected-models sample](../../python/foundry-models/connected-models/) with
`CONNECTED_MODEL_CONNECTION_NAME` and `CONNECTED_MODEL_NAME` set to your connection and model. For more, see
[Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway).

## Manage connections

```bash
azd ai connection list --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
azd ai connection show "$CONNECTION_NAME" --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
azd ai connection update "$CONNECTION_NAME" --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" --key "$GATEWAY_API_KEY"
```

`update` keeps the connection's other settings. `--metadata` entries are merged with the existing metadata.

`create` fails if a connection with the same name exists. To replace it, add `--force`.

To delete a connection, run `azd ai connection delete <name> --force` from an azd project folder, one with an
`azure.yaml` file and an environment. In extension version 1.0.1, the command fails with `no project exists` in other
folders. From any folder, you can delete the connection with the Azure CLI instead. The Bash version needs
[`jq`](https://jqlang.org/):

```bash
connection_id=$(azd ai connection show "$CONNECTION_NAME" --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" --output json --no-prompt | jq -r .id)
az resource delete --ids "$connection_id" --api-version 2025-04-01-preview
```

```powershell
$connectionId = (azd ai connection show $env:CONNECTION_NAME --project-endpoint $env:FOUNDRY_PROJECT_ENDPOINT --output json --no-prompt | ConvertFrom-Json).id
az resource delete --ids $connectionId --api-version 2025-04-01-preview
```

## Security notes

- Prefer keyless access with the project's managed identity when your gateway accepts Microsoft Entra ID tokens.
- `azd ai connection create` takes a key as a command-line argument, so other processes on the same computer might
  see it while the command runs. Run the scripts on a computer you trust, and clear the variable afterward with
  `unset GATEWAY_API_KEY` or `Remove-Item Env:GATEWAY_API_KEY`.
- Foundry stores the key in the connection. `azd ai connection show` doesn't return it unless you add
  `--show-credentials`.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `Connection '<name>' not found` from an agent right after you create the connection | A new connection can take a minute or two before agents can use it. Wait, and try again. |
| `DeploymentNotFound` or `404` from the gateway | `GATEWAY_URL` or `APIM_API_URL` must be the base URL, without `/chat/completions`. Check `DEPLOYMENT_IN_PATH` and the model name. |
| `401` with keyless APIM | The API's `validate-azure-ad-token` policy must accept the project identity's application ID and the audience in `TOKEN_AUDIENCE`. |
| PowerShell passes broken JSON | Use PowerShell 7.3 or later. |
| `connections: no active azd environment` after `create` | You can ignore it outside an azd project. The connection is still created. |
