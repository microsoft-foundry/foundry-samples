---
description: This template deploys a network-secured Microsoft Foundry project with a project capability host and three optional bring-your-own-model paths: private APIM to another Foundry account, direct connection to another Foundry account, and a third-party model provider.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: cross-region-byom-apim
languages:
- bicep
- json
---

# Microsoft Foundry: VNet BYOM Golden Path with a Capability Host

This template extends [template 16 (private-network standard agent + APIM private endpoint)](../../) with the Bicep resources for three connected-model scenarios on a network-secured project:

| Scenario | Connection | Model endpoint | Enable with |
|---|---|---|---|
| Deterministic mock model through APIM (optional) | `ApiManagement`, project managed identity | APIM policy returns an OpenAI-compatible response without calling a backend | `mockModelName = 'mock-model'` |
| Foundry model through APIM | `ApiManagement`, project managed identity | Private through APIM outbound VNet integration and a cross-region private endpoint | Always deployed |
| Foundry model without APIM | `ModelGateway`, API key | Backend Foundry public endpoint | `enableDirectFoundryConnection = true` |
| Third-party provider | `ModelGateway`, API key | Provider's public OpenAI-compatible endpoint | `enableThirdPartyConnection = true` |

All three produce a model reference in the form `<connection-name>/<deployment-name>` for a prompt agent invoked through the Responses API.

The APIM connection advertises the real backend deployments and, when `mockModelName` is set (for example to `mock-model`), a local mock model:

- `ai-gateway/mock-model` returns a deterministic response directly from APIM (only when the mock is enabled).
- `ai-gateway/gpt-4o` (or another name in `backendModelDeployments`) invokes the real model through APIM's managed-identity and private-endpoint path.

APIM adds `x-aigw-route: mock` or `x-aigw-route: real` to the corresponding gateway response for tracing.

The common project foundation includes:

- A Microsoft Foundry **project** in one region (the *project region*, e.g. `canadaeast`).
- A second Microsoft Foundry **account** in a different region (the *backend region*, e.g. `japaneast`) hosting the model deployments — typically frontier models that arrive in the backend region first.
- An **Azure API Management** service (StandardV2, outbound VNet-integrated) sitting between the two as the AI Gateway.
- A **cross-region private endpoint** from the project VNet into the backend Foundry account.
- The `/inference` API on APIM with the full **managed-identity + backend-rewrite** policy chain.
- A **BYOM model connection** on the project that surfaces the backend deployments as `<connection-name>/<deployment-name>` in agent code.

> [!IMPORTANT]
> The project capability host secures the project dependencies used by Agent Service, including Storage, Cosmos DB, and AI Search. It does not make connected-model inference originate from the delegated agent subnet. Connected-model calls originate from the managed Agent Service inference plane. Consequently, only the APIM scenario in this sample has a private model data path. The direct Foundry and third-party scenarios require endpoints that are reachable from that managed service plane.

Reference: [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway).

---

## When to use this template

Use this template when:

- The Foundry resource and the model you want to use **cannot live in the same region** — typically because frontier models (e.g. `gpt-5`, `gpt-5.1`) land in a region where Foundry projects are not yet GA, or vice versa.
- You need the **AI Gateway pattern** (BYOM via APIM) — central observability, throttling, governance, and managed-identity rotation — in front of the model traffic.
- You need an **end-to-end private APIM path**. When direct Foundry is disabled, the backend Foundry account has `publicNetworkAccess = Disabled`, the cross-region PE keeps the traffic on the Microsoft backbone, and the model never appears on the public internet.
- You want **managed-identity authentication** end to end. No API keys, no APIM subscription keys.

If you only need APIM in front of a Foundry account in the **same region**, use [template 16](../../) directly. If you only need the connection artifact and you already have APIM + Foundry deployed, use [`01-connections/apim/connection-apim.bicep`](../../../01-connections/apim/).

### Network boundary by scenario

Enabling `enableDirectFoundryConnection` changes the backend account to `publicNetworkAccess: Enabled` and `disableLocalAuth: false` so Agent Service can authenticate with the generated API key. The APIM private endpoint remains in place, but the direct request does not traverse it. Do not enable this option if policy requires the model endpoint itself to remain private.

The third-party endpoint and API key are supplied as deployment parameters. Pass `thirdPartyApiKey` as a secure command-line parameter or from a secret-aware deployment system; never put it in a parameter file. The endpoint must implement the OpenAI-compatible contract represented by `thirdPartyModels`.

---

## Architecture Deep Dive

This template extends [template 16's architecture](../../#network-secured-agent-project-architecture-deep-dive) — the project-region VNet and Foundry account stay identical. The new pieces are: a third and fourth subnet (`apim-outbound` and `backend-pe`), an APIM service inside the project VNet, a backend Foundry account in a second region, and a cross-region private endpoint that connects them.

```text
                  Project Region (e.g. canadaeast)
┌────────────────────────────────────────────────────────────────────────────┐
│  VNet  192.168.0.0/16                                                      │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ agent-subnet      192.168.0.0/24                                   │    │
│  │ Delegated to Microsoft.App/environments                            │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ pe-subnet         192.168.1.0/24                                   │    │
│  │ Private endpoints:  Storage · Cosmos · AI Search · Foundry         │    │
│  │ (no public network access on any backing service)                  │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ apim-outbound     192.168.2.0/27                            [NEW]  │    │
│  │ Delegated to Microsoft.Web/serverFarms                             │    │
│  │ Network security group attached (required by APIM Standard v2)     │    │
│  │ defaultOutboundAccess: false                                       │    │
│  │                                                                    │    │
│  │   ┌──────────────────────────────────────────────────────────┐     │    │
│  │   │ APIM (StandardV2)                                        │     │    │
│  │   │ System-Assigned MI                                       │     │    │
│  │   │ /inference API                                           │     │    │
│  │   │   ├─ validate-azure-ad-token  (project MI client-id)     │     │    │
│  │   │   ├─ set-backend-service      (deployment-aware)         │     │    │
│  │   │   └─ authentication-managed-identity  (Entra token)      │     │    │
│  │   └────────────────────────────┬─────────────────────────────┘     │    │
│  └────────────────────────────────┼───────────────────────────────────┘    │
│                                   │                                        │
│  ┌────────────────────────────────┼───────────────────────────────────┐    │
│  │ backend-pe        192.168.3.0/27                            [NEW]  │    │
│  │ defaultOutboundAccess: false                                       │    │
│  │                                ▼                                   │    │
│  │   ┌──────────────────────────────────────────────────────────┐     │    │
│  │   │ Cross-region Private Endpoint                            │     │    │
│  │   │ Target:  Backend Foundry account (other region)          │     │    │
│  │   │ DNS:     privatelink.openai.azure.com                    │     │    │
│  │   │          privatelink.cognitiveservices.azure.com         │     │    │
│  │   │          privatelink.services.ai.azure.com               │     │    │
│  │   └────────────────────────────┬─────────────────────────────┘     │    │
│  └────────────────────────────────┼───────────────────────────────────┘    │
│                                   │                                        │
│  ┌────────────────────────────────┼───────────────────────────────────┐    │
│  │ Foundry Account (project region)                                   │    │
│  │ publicNetworkAccess: Disabled                                      │    │
│  │   └─ Foundry Project  (agent workspace + System-Assigned MI)       │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────┼────────────────────────────────────────┘
                                    │  Microsoft backbone (no public hop)
                                    ▼
                    Backend Region (e.g. japaneast)
┌────────────────────────────────────────────────────────────────────────────┐
│  Backend Foundry Account                                                   │
│    publicNetworkAccess: Disabled                                           │
│    disableLocalAuth: true                                           [NEW]  │
│    System-Assigned MI  (APIM mints Entra tokens against this MI)           │
│                                                                            │
│    Model deployments:                                                      │
│      • gpt-4o      (OpenAI · 2024-11-20 · GlobalStandard)                  │
│      • gpt-5       (OpenAI · 2025-08-07 · GlobalStandard)                  │
│      • gpt-5.1     (OpenAI · 2025-11-13 · GlobalStandard)                  │
└────────────────────────────────────────────────────────────────────────────┘

[NEW]  = added or changed in this extension on top of base template 16.
```

> **Tip:** For a new VNet, this extension declares all four subnets in one authoritative VNet resource so redeployment cannot remove an in-use child subnet. For an existing VNet, including one in another resource group or subscription, it derives the VNet scope and name from `existingVnetResourceId`, preserves template 16's additive behavior, and creates only the extension-owned `backend-pe` and `apim-outbound` child subnets. The APIM subnet includes the network security group required by APIM Standard v2.

---

## Prerequisites

1. **Azure subscription with appropriate permissions**
   - **Owner** or **Contributor + User Access Administrator** on the target resource group (the template creates role assignments).
   - **Foundry Account Owner** to create the Foundry account.
2. Quota for `gpt-4o`/`gpt-5`/`gpt-5.1` in the **backend** region, and quota for `gpt-4o` in the **project** region.
3. Quota for **APIM StandardV2** in the project region.
4. Permission to read the Foundry project's managed identity service principal in Microsoft Entra ID. The tested two-pass deployment creates the identity first, resolves its `appId` (client ID), and redeploys the APIM policy with that value.
5. The same resource provider registrations as [template 16](../../#prerequisites) plus `Microsoft.ApiManagement`.

---

## Preflight checks

This extension provisions resources across two regions, with quota and model-availability requirements in each. A deployment can fail half an hour in if the backend region doesn't have the model SKU you asked for, or if your subscription is out of GlobalStandard capacity. Verify the region pair first — every check is read-only and finishes in under 90 seconds.

### Option A — scripted (recommended)

```powershell
cd preflight
.\check-region.ps1 -Subscription <sub-id> -ProjectRegion canadaeast -BackendRegion japaneast
```

That uses the same defaults as `main.bicepparam` (`gpt-4o` project-side; `gpt-4o`/`gpt-5`/`gpt-5.1` backend-side; `GlobalStandard` SKU). If you've changed the bicepparam (different region pair, different model list, different SKU, BYO Search/Storage/Cosmos), pass matching flags — see [Matching the script to your bicepparam](./preflight/README.md#matching-the-script-to-your-mainbicepparam) for the full table.

On success the script prints the exact `az deployment group create` command for the regions it verified. On failure it ranks alternative regions by available quota.

### Option B — inline `az` commands

If you'd rather not run PowerShell, the same gates as one-liners. Set the regions first:

```bash
PROJECT_REGION="canadaeast"
BACKEND_REGION="japaneast"
```

**1. Required resource providers are registered**

```bash
for ns in Microsoft.CognitiveServices Microsoft.ApiManagement Microsoft.Network Microsoft.Storage Microsoft.DocumentDB Microsoft.Search; do
  state=$(az provider show --namespace $ns --query registrationState -o tsv)
  echo "$ns : $state"
done
```

Anything other than `Registered` blocks deployment. Register with `az provider register --namespace <ns> --wait`.

**2. Both regions support the services this extension creates**

```bash
# Foundry (Cognitive Services) — must include both regions
az provider show --namespace Microsoft.CognitiveServices \
  --query "resourceTypes[?resourceType=='accounts'].locations | [0]" -o tsv \
  | tr ',' '\n' | grep -iE "^($PROJECT_REGION|$BACKEND_REGION)$"

# APIM service — only project region matters (StandardV2 SKU support is region-specific;
# see https://aka.ms/apim-v2-tiers — the ARM provider list below does not distinguish SKUs)
az provider show --namespace Microsoft.ApiManagement \
  --query "resourceTypes[?resourceType=='service'].locations | [0]" -o tsv \
  | tr ',' '\n' | grep -iE "^$PROJECT_REGION$"
```

You should see both regions in the first output, and your project region in the second.

**3. Backend region offers the model SKU + version you want**

```bash
BACKEND_MODELS=$(az cognitiveservices model list --location $BACKEND_REGION \
  --query "[?kind=='OpenAI'].{name:model.name, version:model.version, sku:model.skus[?name=='GlobalStandard'].name | [0]}" -o json)

for m in gpt-4o gpt-5 gpt-5.1; do
  hit=$(echo $BACKEND_MODELS | jq -r ".[] | select(.name == \"$m\" and .sku == \"GlobalStandard\") | \"\(.name) \(.version)\"" | head -1)
  echo "$m : ${hit:-NOT AVAILABLE in $BACKEND_REGION}"
done
```

If a model shows `NOT AVAILABLE`, pick a different backend region or remove that deployment from `backendModelDeployments` in `main.bicepparam`.

**4. GlobalStandard quota in the backend region**

```bash
az cognitiveservices usage list --location $BACKEND_REGION \
  --query "[?contains(name.value, 'OpenAI.GlobalStandard')].{quota:name.value, limit:limit, used:currentValue}" -o table
```

`limit - used` must be at least the `capacity` you set in `main.bicepparam` (default 10 TPM per backend model). Request more in the Azure portal **Quotas** blade if needed.

**5. APIM SV2 quota in the project region**

```bash
az apim list --query "[?location=='$PROJECT_REGION'] | length(@)" -o tsv
```

If this number equals the per-subscription per-region limit (default 5), deployment will fail. Reuse an existing service or request a limit increase.

---

## Deploy

The APIM policy validates tokens issued to the project managed identity, but that identity does not exist until the project has been deployed. Use the same fixed `deploymentTimestamp` and resource names for both passes so the second pass updates the first deployment instead of creating another environment.

### Pass 1: create the project identity

```bash
az group create --name <rg> --location <project-region>

az deployment group create \
  --resource-group <rg> \
  --template-file main.bicep \
  --parameters @samples/parameters-cross-region.json \
  --parameters deploymentTimestamp=<fixed-timestamp> \
  --parameters projectMiClientId=00000000-0000-0000-0000-000000000000
```

The placeholder is used only to create the initial APIM policy. Do not invoke the gateway until the policy is updated in pass 2.

### Pass 2: resolve the client ID and update the policy

Get `projectId` from the first deployment's outputs, then resolve the project identity's principal ID to its application/client ID:

```bash
PROJECT_ID="<outputs.projectId>"
PROJECT_PRINCIPAL_ID=$(az resource show \
  --ids "$PROJECT_ID" \
  --api-version 2025-04-01-preview \
  --query identity.principalId -o tsv)

PROJECT_MI_CLIENT_ID=$(az ad sp show \
  --id "$PROJECT_PRINCIPAL_ID" \
  --query appId -o tsv)

az deployment group create \
  --resource-group <rg> \
  --template-file main.bicep \
  --parameters @samples/parameters-cross-region.json \
  --parameters deploymentTimestamp=<same-fixed-timestamp> \
  --parameters projectMiClientId="$PROJECT_MI_CLIENT_ID"
```

The principal/object ID and application/client ID are different values. `projectMiClientId` requires the application/client ID. Allow 30 to 60 seconds for APIM policy propagation before creating and invoking a fresh prompt-agent version.

You can use `main.bicepparam` instead of the JSON parameter file in both passes. Keep its `deploymentTimestamp` and all resource names unchanged between passes.

By default, the project account remains private-only. For deployment-time SDK validation from one trusted caller, set `developerIpCidr` to that caller's CIDR, such as `203.0.113.10/32`. The module normalizes a single IPv4 `/32` for the Cognitive Services IP rule. Leave the parameter empty for the secure default of `publicNetworkAccess: Disabled`.

### Manually compare the mock and real routes

Deploy with `mockModelName = 'mock-model'` to enable the mock route. Then run these commands from a client that can reach the private Foundry project endpoint. The shared prompt-agent script uses the required Prompt Agent plus Responses API path for gateway-connected models:

```bash
python ../../../01-connections/public-byom-apim/samples/create-agent.py \
  --endpoint https://<account>.services.ai.azure.com/api/projects/<project> \
  --model ai-gateway/mock-model \
  --agent-name gateway-mock-test \
  --prompt "This text is ignored by the deterministic mock."

python ../../../01-connections/public-byom-apim/samples/create-agent.py \
  --endpoint https://<account>.services.ai.azure.com/api/projects/<project> \
  --model ai-gateway/gpt-4o \
  --agent-name gateway-real-test \
  --prompt "Reply with: real model route succeeded"
```

The first invocation should return:

```text
This is a deterministic mock response generated by Azure API Management.
```

The second response is generated by the deployed Foundry model. If you changed `connectionName`, `mockModelName`, or `backendModelDeployments`, use the deployment outputs `mockModelReference` and `realModelReferences` instead of the default model references above.

After deployment, the gateway URL is in `outputs.apimGatewayUrl`. The connected models appear in the Foundry portal under **Connected resources** as `<connection-name>/<deployment-name>` (e.g. `ai-gateway/gpt-5`).

### Validation status

This template was deployed into a fresh test environment with a VNet-secured project and project capability host. Prompt-agent inference through the Responses API passed for both `ai-gateway/gpt-4.1-mini` and `foundry-direct/gpt-4.1-mini`. The external third-party scenario is implemented but was not tenant-validated because no external OpenAI-compatible endpoint and API key were available. APIM inference succeeded, but the test APIM instance had no Azure Monitor diagnostic setting, so independent gateway/backend log correlation was not collected.

---

## Smoke test

The `/inference` API has `subscriptionRequired: false` because authentication is managed-identity end to end. To verify the gateway is reachable, in the APIM Test Console call the `inference > chat-completions` operation with:

| Field | Value |
|---|---|
| `deploymentName` (template param) | `gpt-5` |
| `api-version` (query) | `2024-10-21` |
| `Content-Type` (header) | `application/json` |
| Body | `{ "messages": [{ "role": "user", "content": "Say hi in five words." }], "max_tokens": 30 }` |

A `200` with `x-aigw-backend` and `x-aigw-region` response headers proves the policy chain (MI validation → backend rewrite → cross-region PE) is healthy.

---

## How the pieces are wired together

Once everything is deployed, a single request from a Foundry agent to `gpt-5` traverses **six** layers. Understanding what travels at each hop is what makes the rest of this README make sense.

```
┌──────────────────┐   1. SDK call          ┌──────────────────────────┐
│ Foundry agent     │ ───────────────────► │ Foundry Project          │
│ (your code,       │   model name =       │ (resolves the model name │
│  Playground, etc) │   "<conn>/gpt-5"     │  via the BYOM connection)│
└──────────────────┘                       └────────────┬─────────────┘
                                                        │
                                                        │ 2. Project MI
                                                        │    mints AAD token
                                                        │    for audience:
                                                        │    cognitiveservices
                                                        │    .azure.com
                                                        ▼
                                            ┌────────────────────────┐
                                            │ APIM /inference API     │
                                            │  policy: validate-      │
                                            │  azure-ad-token         │
                                            │  (project MI app ID)    │
                                            └────────────┬───────────┘
                                                         │
                                                         │ 3. Token OK.
                                                         │    Strip caller key.
                                                         │    set-backend-service
                                                         │    rewrites URL to
                                                         │    https://<backend>
                                                         │    .openai.azure.com/
                                                         │    openai/deployments/
                                                         │    {deploymentName}/...
                                                         ▼
                                            ┌────────────────────────┐
                                            │ APIM MI                 │
                                            │  authentication-        │
                                            │  managed-identity       │
                                            │  mints a fresh AAD      │
                                            │  token for the backend  │
                                            │  Foundry account        │
                                            └────────────┬───────────┘
                                                         │
                                                         │ 4. DNS resolves
                                                         │    <backend>.openai
                                                         │    .azure.com to
                                                         │    private IP in
                                                         │    backend-pe subnet
                                                         ▼
                                            ┌────────────────────────┐
                                            │ Cross-Region PE         │
                                            │  (backend-pe subnet)    │
                                            │  Microsoft backbone     │
                                            │  to backend region      │
                                            └────────────┬───────────┘
                                                         │
                                                         │ 5. Bearer token
                                                         │    accepted; RBAC
                                                         │    check: APIM MI
                                                         │    has Cognitive
                                                         │    Services User on
                                                         │    backend account
                                                         ▼
                                            ┌────────────────────────┐
                                            │ Backend Foundry account │
                                            │  (publicNetworkAccess:  │
                                            │       Disabled)         │
                                            │  Runs gpt-5             │
                                            │                         │
                                            │  6. Response flows back │
                                            │     through the same    │
                                            │     path with x-aigw-*  │
                                            │     headers added by    │
                                            │     APIM on the way out │
                                            └────────────────────────┘
```

**What this means in practice:**

| Layer | Auth artefact | Identity used | Configured by |
|---|---|---|---|
| Agent → Project | None — in-process | n/a | Foundry SDK |
| Project → APIM | AAD bearer token | Project managed identity | `validate-azure-ad-token` policy needs the project MI's **app ID** (`projectMiClientId` template param) |
| APIM → Backend | Fresh AAD bearer token | APIM managed identity | `authentication-managed-identity` policy + Cognitive Services User RBAC on backend |
| Backend → APIM (response) | n/a | n/a | APIM adds `x-aigw-backend`, `x-aigw-region`, `apim-request-id`, `apim-trace-id` headers |
| Network path | Private throughout | n/a | Backend `publicNetworkAccess: Disabled`; resolution via privatelink DNS zones; data path via the cross-region PE on the Microsoft backbone |

**No API keys** are stored anywhere. **No APIM subscription key** is required (`subscriptionRequired: false`). Token rotation is handled automatically by both managed identities.

---

## Use the connected model from a Foundry agent

Once deployment finishes, each enabled connection appears on the Foundry project and its configured deployments become connected models. Reference them as:

- `ai-gateway/gpt-5` for the private APIM path.
- `foundry-direct/gpt-5` for the direct Foundry path.
- `third-party-models/<model-name>` for the third-party path.

Connected models are supported by prompt agents through the Responses API. Do not use the classic Assistants threads/runs flow for this validation.

### Enable the optional scenarios

Direct Foundry uses the model deployments already declared in `backendModelDeployments`:

```bicep
param enableDirectFoundryConnection = true
param directFoundryConnectionName = 'foundry-direct'
```

For an OpenAI-compatible third-party provider, describe each exposed model and pass the key separately at deployment time:

```bicep
param enableThirdPartyConnection = true
param thirdPartyConnectionName = 'third-party-models'
param thirdPartyTargetUrl = 'https://provider.example.com/v1'
param thirdPartyModels = [
  {
    name: 'provider-model-name'
    properties: {
      model: {
        name: 'provider-model-name'
        version: '1'
        format: 'OpenAI'
      }
    }
  }
]
```

```bash
az deployment group create \
  --resource-group <resource-group> \
  --template-file main.bicep \
  --parameters main.bicepparam \
  --parameters thirdPartyApiKey='<secret>'
```

Do not commit the API key or write it to the cross-VM handoff folder.

### In the Foundry portal

1. Open the project at `https://ai.azure.com/`.
2. Go to **Models + endpoints** → **Connected models**. You should see one connection (e.g. `ai-gateway`) with the deployments you configured (`gpt-4o`, `gpt-5`, `gpt-5.1`).
3. Open **Agents playground** and click **+ New agent**.
4. In the model picker, the connected models appear with the `<connection-name>/<deployment-name>` qualifier — for example `ai-gateway/gpt-5`. Select one.
5. Send a prompt. The first request takes a few seconds (token mint + APIM cold path). Subsequent requests are warm.

### In agent code (Python)

When you create a prompt agent from the SDK, reference the connected model with the same `<connection-name>/<deployment-name>` syntax. Foundry routes the request through the connection; your code never sees APIM directly.

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential

project = AIProjectClient(
    endpoint="https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>",
    credential=DefaultAzureCredential(),
)

agent = project.agents.create_version(
    agent_name="cross-region-agent",
    definition=PromptAgentDefinition(
        model="ai-gateway/gpt-5",
        instructions="You are a helpful assistant.",
    ),
)

response = project.get_openai_client().responses.create(
    input="Say hi.",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)
print(response.output_text)
```

See [Create a prompt agent with a model connection](https://learn.microsoft.com/azure/foundry/agents/how-to/connected-foundry-models#use-a-connected-model-in-an-agent) for the full SDK reference.

### Important: 1P (Microsoft on-behalf-of) tools are blocked

When an agent is configured against a BYOM connection, Foundry will reject tools that need to forward the caller's Microsoft tenant data to the model — most notably:

- **SharePoint Grounding** (`sharepoint_grounding_preview`)
- **Microsoft Fabric Data Agent**
- **Microsoft 365 Copilot Connectors**

The error surfaces as `bad_request` in the playground. This is by design: Foundry will not forward on-behalf-of tenant context outside the Microsoft trust boundary, regardless of whether the BYOM connection uses managed identity or API keys. If you need these tools, host the agent on a standard (non-BYOM) Foundry deployment and use the BYOM agent only for the model-only path.

---

## Manage from the Azure CLI

After the template deploys, common operational tasks can be done from the CLI without going back through Bicep. Set up the basics once per shell:

```bash
RG="<resource-group>"
PROJECT_ACCOUNT="<project-foundry-account-name>"
PROJECT_NAME="<project-name>"
BACKEND_ACCOUNT="<backend-foundry-account-name>"
BACKEND_RG="<backend-resource-group>"      # may be the same as $RG
APIM_NAME="<apim-name>"
CONNECTION_NAME="ai-gateway"
```

### Inspect the BYOM connection

```bash
# Show the connection that the template created on the project
az cognitiveservices account connection show \
  --name "$CONNECTION_NAME" \
  --account-name "$PROJECT_ACCOUNT" \
  --resource-group "$RG"

# List every connection on the project (useful when you have multiple gateways)
az cognitiveservices account connection list \
  --account-name "$PROJECT_ACCOUNT" \
  --resource-group "$RG" \
  --query "[?properties.category=='AzureOpenAI'].{name:name, target:properties.target, auth:properties.authType}"
```

The connection's `target` should be `https://<apim>.azure-api.net/inference`. That's the only URL the project ever sees.

### Add a new model on the backend (no APIM change required)

The `/inference` API uses the template `/deployments/{deploymentName}/chat/completions`, so any deployment you add on the backend becomes routable through APIM the moment it finishes provisioning. APIM does **not** need to be redeployed.

```bash
az cognitiveservices account deployment create \
  --name "$BACKEND_ACCOUNT" \
  --resource-group "$BACKEND_RG" \
  --deployment-name "gpt-5.1" \
  --model-name "gpt-5.1" \
  --model-version "2025-11-13" \
  --model-format "OpenAI" \
  --sku-name "GlobalStandard" \
  --sku-capacity 100
```

To make the new deployment selectable in the Foundry portal, you must also list it on the BYOM connection. Either redeploy the template with the new entry in `backendModelDeployments`, or patch the connection directly:

```bash
# Append a model to the connection's staticModels list
# (Replace the body with the full updated list; this API does a PUT, not a PATCH.)
az resource update \
  --ids "/subscriptions/<sub>/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$PROJECT_ACCOUNT/connections/$CONNECTION_NAME" \
  --set properties.metadata.staticModels="[{...existing models..., {\"name\":\"gpt-5.1\",\"properties\":{\"model\":{\"name\":\"gpt-5.1\",\"version\":\"2025-11-13\",\"format\":\"OpenAI\"}}}}]"
```

### Verify the RBAC chain

The whole flow falls apart if either MI loses its role assignment. Two checks worth scripting into a runbook:

```bash
# 1. APIM MI must have Cognitive Services User on the backend account
APIM_MI_PRINCIPAL=$(az apim show --name "$APIM_NAME" --resource-group "$RG" --query "identity.principalId" -o tsv)
BACKEND_ID=$(az cognitiveservices account show --name "$BACKEND_ACCOUNT" --resource-group "$BACKEND_RG" --query "id" -o tsv)

az role assignment list \
  --assignee "$APIM_MI_PRINCIPAL" \
  --scope "$BACKEND_ID" \
  --query "[?roleDefinitionName=='Cognitive Services User']"

# 2. Project MI must be referenced by the APIM validate-azure-ad-token policy
#    (audit by reading the inbound policy on the /inference API)
az apim api policy show \
  --service-name "$APIM_NAME" \
  --resource-group "$RG" \
  --api-id "inference" \
  --policy-format "rawxml"
```

### Call the gateway directly with a bearer token

For end-to-end troubleshooting (or to confirm an outage isn't a Foundry-side bug), bypass the project and hit APIM directly with your own AAD token:

```bash
TOKEN=$(az account get-access-token --resource "https://cognitiveservices.azure.com" --query accessToken -o tsv)

curl -sS -X POST \
  "https://$APIM_NAME.azure-api.net/inference/deployments/gpt-5/chat/completions?api-version=2024-10-21" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hi in five words."}],"max_tokens":30}' \
  | jq '.choices[0].message.content'
```

Your token must come from a principal whose **app ID** matches the one the `validate-azure-ad-token` policy was configured with (`projectMiClientId` template param). For a quick manual test, the simplest path is to temporarily add your own user/app to the policy, or use `az account get-access-token` from a session signed in as the project's MI itself.

---

## How this differs from template 16

| Concern | Template 16 | Template 16 + this extension |
|---|---|---|
| Foundry account region | Single (project region) | Two — project region **and** backend region |
| APIM service | Bring your own (existing) | Greenfield OR bring your own |
| APIM AI Gateway API + policy chain | Not deployed | `/inference` API + MI/backend-rewrite/headers chain |
| Cross-region private endpoint | Not deployed | Backend Foundry account PE on `backend-pe` subnet |
| `backend-pe` subnet | Not present | Added as a third subnet (configurable CIDR) |
| `apim-outbound` subnet | Not present | Added with an NSG for APIM SV2 VNet integration |
| BYOM model connection on project | Not created | Created automatically (calls `01-connections/apim/connection-apim.bicep`) |
| Backend `publicNetworkAccess` | Project account is `Disabled` | Project **and** backend are `Disabled` |
| Backend access path | N/A | Cross-region PE only |
| Auth between Foundry project and APIM | N/A | Project MI → `validate-azure-ad-token` |
| Auth between APIM and backend | N/A | APIM MI → `authentication-managed-identity` + Cognitive Services User RBAC |

---

## Module map

**Local modules (extension-specific):**

- [`modules/vnet-with-backend-subnet.bicep`](./modules/vnet-with-backend-subnet.bicep) - owns all four subnets atomically for a new VNet, or additively creates the extension subnets for an existing VNet; also creates the APIM outbound-subnet NSG.
- [`modules/backend-ai-account.bicep`](./modules/backend-ai-account.bicep) — backend Foundry account in the backend region with the model deployments.
- [`modules/backend-private-endpoint.bicep`](./modules/backend-private-endpoint.bicep) — cross-region PE on the `backend-pe` subnet; binds to the existing privatelink DNS zones.
- [`modules/apim-service.bicep`](./modules/apim-service.bicep) — APIM StandardV2 + outbound VNet integration + system-assigned MI.
- [`modules/apim-inference-api.bicep`](./modules/apim-inference-api.bicep) — `/inference` API, `chat-completions` operation, and the full inbound policy chain.
- [`modules/apim-backend-role-assignment.bicep`](./modules/apim-backend-role-assignment.bicep) — Cognitive Services User role for APIM's MI on the backend account.

**Tooling:**

- [`preflight/check-region.ps1`](./preflight/check-region.ps1) — pre-deployment region verifier (RP registrations, model + version catalogue, GlobalStandard quota, APIM SV2 SKU). See [`preflight/README.md`](./preflight/README.md).

**Template 16 modules (referenced as-is — full E2E parity with template 16):**

- [`network-agent-vnet.bicep`](../../modules-network-secured/network-agent-vnet.bicep) — base VNet with `agent-subnet` (delegated) + `pe-subnet`.
- [`ai-account-identity.bicep`](../../modules-network-secured/ai-account-identity.bicep) — project-region Foundry account + the local `gpt-4o` deployment, identity assigned.
- [`validate-existing-resources.bicep`](../../modules-network-secured/validate-existing-resources.bicep) — verifies any BYO dependency resource IDs you passed in.
- [`standard-dependent-resources.bicep`](../../modules-network-secured/standard-dependent-resources.bicep) — creates Storage / AI Search / Cosmos DB (or reuses your existing ones).
- [`private-endpoint-and-dns.bicep`](../../modules-network-secured/private-endpoint-and-dns.bicep) — PEs in `pe-subnet` for the project Foundry account, Storage, AI Search, Cosmos DB, and (optionally) APIM; creates/links the 7 private DNS zones.
- [`ai-project-identity.bicep`](../../modules-network-secured/ai-project-identity.bicep) — first Foundry project on the project account, with its system-assigned MI and the 3 connections (storage / search / cosmos).
- [`format-project-workspace-id.bicep`](../../modules-network-secured/format-project-workspace-id.bicep) — converts the project's internal id into the canonical GUID form needed by the capability host.
- [`azure-storage-account-role-assignment.bicep`](../../modules-network-secured/azure-storage-account-role-assignment.bicep) — *Storage Blob Data Contributor* on the storage account for the project MI (pre-caphost).
- [`cosmosdb-account-role-assignment.bicep`](../../modules-network-secured/cosmosdb-account-role-assignment.bicep) — *Cosmos DB Operator* on the cosmos account for the project MI (pre-caphost).
- [`ai-search-role-assignments.bicep`](../../modules-network-secured/ai-search-role-assignments.bicep) — *Search Index Data Contributor* on the AI Search service for the project MI (pre-caphost).
- [`add-project-capability-host.bicep`](../../modules-network-secured/add-project-capability-host.bicep) — **the showstopper** — attaches the capability host to the project. Without this, agents cannot run.
- [`blob-storage-container-role-assignments.bicep`](../../modules-network-secured/blob-storage-container-role-assignments.bicep) — *Storage Blob Data Owner* on the per-project containers Foundry created (post-caphost).
- [`cosmos-container-role-assignments.bicep`](../../modules-network-secured/cosmos-container-role-assignments.bicep) — *Cosmos Built-In Data Contributor* on the per-project containers Foundry created (post-caphost).

**External reference:**

- [`../01-connections/apim/connection-apim.bicep`](../../../01-connections/apim/) — referenced as-is for the BYOM model connection.

---

## Limitations / known issues

- **1P on-behalf-of tools** (e.g. SharePoint Grounding, Fabric Data Agent) are **not supported** on BYOM connections regardless of auth type — Foundry will return `bad_request` because forwarding 1P-token tenant data to a non-Microsoft-managed model endpoint would leak it outside the Microsoft trust boundary. Use a standard Foundry deployment for those tools, or split into two agents.
- Cross-region private endpoints from the project region to the backend account work because both ends are Azure-managed; you do **not** need VNet peering between regions.
- APIM SV2 outbound VNet integration requires a `/27` or larger dedicated subnet (`apim-outbound`).
- The backend Foundry account does **not** host its own project. It's used purely as a model host behind the AI Gateway.
- The external third-party provider connection has not been tenant-validated in this sample because the test environment did not have a provider endpoint and credential.
