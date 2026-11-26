# Set up an AI Gateway for Foundry models (Python)

These scripts show a platform administrator how to put an AI Gateway in front of an existing Microsoft Foundry model
deployment by using the Azure management SDKs for Python. They:

1. Create the gateway with a system-assigned managed identity.
2. Publish a Foundry model deployment through the gateway, with a per-caller token limit.
3. Give a Foundry project keyless access to the model.
4. Optionally, create a runtime API key for an application outside Foundry and send a test request.

The scripts reuse your Foundry account, model deployment, and project. They don't create a resource group, account,
project, or model deployment.

## What the SDK covers today

The [`azure-mgmt-aigateway`](https://pypi.org/project/azure-mgmt-aigateway/) 1.0.0b1 package manages only the gateway
resource. Its API version, `2026-09-01-preview`, doesn't define model providers, models, aliases, or API keys. Those
resources are defined in the stable `2026-11-01` API, which doesn't have an SDK yet.

| Task | How the scripts do it |
| --- | --- |
| Create and read the gateway | `azure-mgmt-aigateway` |
| Grant roles | `azure-mgmt-authorization` |
| Read the Foundry account, deployment, and project, and create the project connection | `azure-mgmt-cognitiveservices` |
| Create the model provider, model registration, alias, and API key, and read the key | [`gateway_rest.py`](gateway_rest.py) |

`gateway_rest.py` sends `2026-11-01` requests through the AI Gateway SDK client's pipeline with `send_request`, so they
use the same credential, retry, and logging policies as the typed calls. Replace those calls when the SDK adds typed
operations for them.

`azure-mgmt-cognitiveservices` 15.0.0 has no typed model for a connection that signs in with the project's managed
identity, so `connect-foundry-project.py` passes that connection as JSON to the typed `create` operation.

## Prerequisites

- Python 3.10 or later.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), signed in with `az login`.
- The `Microsoft.ApiManagement` resource provider registered in your subscription.
- A resource group for the gateway, in a region where AI Gateway is available.
- A Foundry account in the same subscription, with a model deployment that supports Chat Completions.
- For step 3, a Foundry project in that account with a system-assigned managed identity.

Your identity needs these roles:

| Task | Scope | Role |
| --- | --- | --- |
| Create and configure the gateway, and read runtime keys | Gateway resource group | Contributor |
| Grant the gateway identity **Foundry User** (step 2) | Foundry account | Owner, User Access Administrator, or Role Based Access Control Administrator |
| Grant the project identity **AI Gateway Models User** (step 3) | Gateway resource group | Owner, User Access Administrator, or Role Based Access Control Administrator |
| Create the project connection (step 3) | Foundry project | Contributor, or another role that can write project connections |

The **API Management Service Contributor** role doesn't cover `Microsoft.ApiManagement/aigateways` resources.

## Set up

Run these commands from this directory.

```shell
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install the dependencies and sign in:

```shell
python -m pip install -r requirements.txt
az login
```

Copy `.env.example` to `.env` and set the values. Variables already set in your environment take precedence over
`.env`.

## Run the steps

### 1. Create the gateway

```shell
python create-gateway.py
```

The script creates the gateway with a system-assigned managed identity, or leaves an existing gateway unchanged. It
doesn't set a SKU, so the service applies its default. Creating a gateway can take several minutes.

```text
Creating gateway 'contoso-gateway' in eastus2. This can take several minutes...
Gateway ID:         /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/aigateways/contoso-gateway
Provisioning state: Succeeded
Managed identity:   <principal-id>
Runtime base URL:   https://<assigned-hostname>/default/models/openai/v1
Next: run publish-model.py.
```

Use the runtime base URL that the script prints. The service assigns the hostname, so don't build it from the gateway
name.

### 2. Publish a Foundry model

```shell
python publish-model.py
```

The script:

1. Grants the gateway's managed identity the **Foundry User** role on the Foundry account, so the gateway calls the
   model without a Foundry key.
2. Registers the Foundry account as a model provider, and the deployment as a backend model.
3. Publishes an alias, which is the model name that callers send, and limits each caller to
   `AI_GATEWAY_TOKENS_PER_MINUTE` tokens per minute.

```text
Granted Foundry User on '<account>' to the gateway identity.
Model provider '<account>' is ready.
Model registration 'gpt-5-mini' is ready.
Alias 'gpt-5-mini' is ready, limited to 10000 tokens per minute per caller.
Runtime base URL: https://<assigned-hostname>/default/models/openai/v1
Callers send model 'gpt-5-mini'. Next: run connect-foundry-project.py or create-api-key.py.
```

### 3. Give a Foundry project keyless access

```shell
python connect-foundry-project.py
```

The script grants the project's managed identity the **AI Gateway Models User** role on the gateway's default
workspace. It then creates a project connection that signs in to the gateway with that identity. No gateway key is
stored in Foundry, and the connection isn't shared with other projects.

```text
Granted AI Gateway Models User to project '<project>'.
Connection 'ai-gateway' is ready.
Agents in project '<project>' can use model 'ai-gateway/gpt-5-mini'.
```

Developers use `<connection-name>/<alias>` as the model of a prompt agent. For an example, see the
[connected models sample](../../foundry-models/connected-models/README.md).

### 4. Optional: create a runtime API key

```shell
python create-api-key.py
```

Use a runtime key for an application outside Foundry. The script creates the key, or reuses it without rotating it. It
reads the key's value into memory and sends one test request through the alias.

```text
Created runtime API key 'external-app'.
Model 'gpt-5-mini' replied: <the model's answer>
Give the application the runtime base URL https://<assigned-hostname>/default/models/openai/v1 and model 'gpt-5-mini'.
Share the key through a secret store, such as Azure Key Vault, not in source code or chat.
```

A runtime key grants gateway-wide access. The script never prints, logs, or saves it. To retrieve the key later, use
[`az aigateway api-key list-secrets`](https://learn.microsoft.com/azure/ai-gateway/get-started-cli#create-a-runtime-api-key).

New role assignments, keys, and aliases can take a few minutes to take effect. If the test request returns 401, 403,
or 404, the script retries for a few minutes.

## Rerun the scripts

You can rerun every script. The scripts check for an existing role assignment before they grant a role, so reruns
don't need permission to grant roles after the first run. The scripts also mark the resources they create: a tag on the
gateway, and a description or display name on the gateway's child resources. They update only marked resources. If a
model provider, model, or alias with the same name exists but this sample didn't create it, the script stops instead of
changing it.

## Clean up

```shell
python cleanup.py
```

The script lists what it deletes and asks for confirmation. It removes the project connection if it points at this
gateway, the role assignments that these scripts granted, and the runtime key, alias, model registration, and model
provider that this sample created. It deletes the gateway only if `create-gateway.py` created it. It doesn't delete your
Foundry account, deployment, or project.

## Troubleshooting

- **`AuthorizationFailed` for `Microsoft.Authorization/roleAssignments/write`:** Contributor can't grant roles. Ask an
  administrator for a role-granting role from [Prerequisites](#prerequisites), or to grant the role for you. Then rerun
  the script.
- **The test request keeps returning 401 or 403:** Role assignments can take several minutes to take effect. Rerun
  `create-api-key.py` later.
- **The test request returns 404:** Check that `AI_GATEWAY_ALIAS` matches the alias that `publish-model.py` published.
- **`... already exists and wasn't created by this sample`:** Choose different names in `.env`.

## Related content

- [Start with the AI Gateway Azure CLI extension](https://learn.microsoft.com/azure/ai-gateway/get-started-cli)
- [Quickstart: Create an AI Gateway](https://learn.microsoft.com/azure/ai-gateway/quickstart-create-ai-gateway)
- [AI Gateway labs](https://github.com/Azure/aigateway/tree/main/labs)
- [AI Gateway REST API specification](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/apimanagement/resource-manager/Microsoft.ApiManagement/AIGateway)
