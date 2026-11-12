---
description: Layers a public (non-VNet) Azure API Management AI Gateway in front of an existing backend Microsoft Foundry account and adds a bring-your-own-model (BYOM) connection to an existing Foundry project. Public counterpart of template 16's private cross-region BYOM extension.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: public-byom-apim
languages:
- bicep
- json
---

# Microsoft Foundry: Public Bring-Your-Own-Model via Azure API Management

This sample stands up the **public (non-VNet) AI Gateway** plumbing for the
**bring-your-own-model (BYOM)** pattern. Given an existing Foundry project and an
existing backend Foundry account that hosts your model deployments, it deploys:

- A public **StandardV2 Azure API Management** service with a system-assigned managed identity.
- A **role assignment** granting APIM's MI `Cognitive Services User` on the backend Foundry account.
- The `/inference` API on APIM with the full **managed-identity + backend-rewrite** policy chain.
- A **BYOM model connection** on the project that surfaces the backend deployments as
  `<connectionName>/<deploymentName>` in agent code.

It is the public counterpart of the private, VNet-integrated
[`16-.../extensions/byom-cross-region`](../../16-private-network-standard-agent-apim-setup/extensions/byom-cross-region/)
template. Use it when your Foundry account, project, and backend model account are all
reachable over public networking and you want the AI Gateway pattern (central
observability, throttling, governance, managed-identity auth) in front of your model
traffic — without VNet injection or private endpoints.

Reference: [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway).

## Where this fits in the golden path

This sample covers **steps 4 and 5** of the non-VNet golden path. See the
[golden-path guide](../../golden-path/README.md) for the full end-to-end sequence
(create resource → project → APIM + BYOM → create an agent).

## Prerequisites

1. **Azure CLI** installed and logged in (`az login`) to the subscription that owns the Foundry project.
2. An existing **Foundry account + project** with a managed identity — deploy
   [template 40](../../40-basic-agent-setup/) or [template 41](../../41-standard-agent-setup/) first.
3. An existing **backend Foundry account** with your model deployments, **in the same
   resource group** as this deployment (the role assignment is scoped to that resource group).
4. The **application (client) ID** of the project's managed identity (`projectMiClientId`) —
   used by APIM to validate inbound tokens.

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `projectResourceId` | Yes | Resource ID of the existing Foundry project the BYOM connection is added to. |
| `backendAccountName` | Yes | Name of the existing backend Foundry account (in this resource group) hosting the models. |
| `backendRegion` | No | Region of the backend account (trace header only). Defaults to the resource group location; override it if the account is in another region. |
| `projectMiClientId` | Yes | Application (client) ID of the project managed identity. |
| `assignBackendRole` | No | Create the APIM MI → `Cognitive Services User` role assignment on the backend account (default `true`). Requires `roleAssignments/write` (Owner / User Access Administrator). Set `false` if you deploy as Contributor and arrange the role assignment separately. |
| `apimName` | No | Globally unique APIM name. Auto-generated if empty. |
| `publisherEmail` | Yes | Publisher email required by APIM at create time. |
| `publisherName` | Yes | Publisher organization required by APIM at create time. |
| `connectionName` | No | Foundry connection name (default `ai-gateway`). |
| `inferenceApiVersion` | No | Inference API version sent to the backend (default `2024-10-21`). |
| `backendModelDeployments` | No | Array of `{ name, format, version }` deployments on the backend account to surface. |

## How to deploy

```bash
# 1) Log in and select the project's subscription
az login
az account set --subscription <foundry-subscription-id>

# 2) Fill in samples/parameters.json (project resource ID, backend account name,
#    project MI client ID, publisher email/name), then deploy into the resource
#    group that holds your Foundry account, project, and backend account.
az deployment group create \
  --resource-group <your-rg> \
  --template-file public-byom-apim.bicep \
  --parameters @samples/parameters.json
```

## After deployment — step 6: create an agent

> [!IMPORTANT]
> A BYOM (gateway-connected) model works **only** with a *prompt agent* invoked through the
> **Responses API**. The classic Assistants API (`create_agent` + threads + runs) cannot
> resolve `<connection>/<model>` and fails with
> `invalid_engine_error: Failed to resolve model info`. Use the flow below.

The agent runs server-side using the **project's managed identity**, which mints the token
APIM's `validate-azure-ad-token` policy checks. Reference the model as
`<connectionName>/<deploymentName>` (e.g. `ai-gateway/gpt-4o`).

A runnable version of the snippet below is provided at
[`samples/create-agent.py`](./samples/create-agent.py):

```bash
pip install "azure-ai-projects>=2.0.0" azure-identity
python samples/create-agent.py \
  --endpoint https://<account>.services.ai.azure.com/api/projects/<project> \
  --model    ai-gateway/gpt-4o \
  --prompt   "Say hello in five words."
```

```python
# pip install azure-ai-projects>=2.0.0 azure-identity
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"

project = AIProjectClient(endpoint=ENDPOINT, credential=DefaultAzureCredential())

agent = project.agents.create_version(
    agent_name="gateway-agent",
    definition=PromptAgentDefinition(
        model="ai-gateway/gpt-4o",           # <connectionName>/<deploymentName>
        instructions="You are a helpful assistant.",
    ),
)

client = project.get_openai_client()
conversation = client.conversations.create()
response = client.responses.create(
    conversation=conversation.id,
    input="Say hi in five words.",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)
print(response.output_text)
```

> [!NOTE]
> The BYOM connection created by this sample sets **`audience`** on the connection
> (`https://cognitiveservices.azure.com`). If it is missing, the Responses call fails with
> `Project identity requires an audience to be specified`. The connection's `authType` is
> `ProjectManagedIdentity` and its `audience` must match the `<audience>` in the APIM
> `validate-azure-ad-token` policy.

### If you deployed with `assignBackendRole=false`

An administrator with `roleAssignments/write` on the backend account must grant
APIM's managed identity access before inference calls will succeed:

```bash
az role assignment create \
  --assignee-object-id <apim-principal-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services User" \
  --scope <backend-account-resource-id>
```

Get `<apim-principal-id>` from `az apim show -g <rg> -n <apim-name> --query identity.principalId -o tsv`.

> **Note:** `Microsoft.Resources/links` and cross-resource references may surface a
> `BCP081` warning during `az bicep build` — this is expected and does not block deployment.
