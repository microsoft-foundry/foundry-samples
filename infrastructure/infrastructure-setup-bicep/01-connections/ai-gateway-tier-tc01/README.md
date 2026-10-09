---
description: End-to-end TC01 happy path for the Azure API Management AI Gateway tier (preview), all in Bicep. main.bicep creates a Foundry account, project, and gpt-5.4 model, then the AI Gateway (AIGateway SKU) with a Foundry model provider that imports the model over managed identity (keyless), a token-limit policy, a runtime key, and the Foundry User role assignment. Test with the included script.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-api-management
urlFragment: ai-gateway-tier-tc01
languages:
- bicep
- json
- python
---

# AI Gateway tier (preview) — TC01: end to end in Bicep

One `az deployment group create` provisions the whole TC01 happy path — the Foundry model
**and** the AI Gateway tier gateway, model import, and token-limit policy. Then a script tests it.

> [!IMPORTANT]
> The AI Gateway tier is a **release-gated public preview**. The gateway is
> `Microsoft.ApiManagement/service` with the **`AIGateway` SKU** (`2025-09-01-preview`) and
> **deploys only where the SKU is enabled** — currently **East US 2** and **Sweden Central**.
> `az bicep build` emits **BCP081** warnings for the preview `modelProviders`, `models`, and
> `apiKeys` types ("does not have types available … will not block deployment") — expected.
> Pattern from [Azure-Samples/simple-foundry-hosted-agent-python-aigateway](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway).

## How this maps to TC01

| TC01 step | Where | What `main.bicep` does |
|-----------|-------|------------------------|
| 1. Create project | **Bicep** | Foundry account + project. |
| 2. Create model | **Bicep** | `gpt-5.4` model deployment (local auth disabled). |
| 3. Create gateway + connect model | **Bicep** | AIGateway `service` + Foundry `modelProvider` (managed identity) + Foundry User role for the gateway MI. |
| 4. Add a policy | **Bicep** | `tokenLimit` policy on the registered model. |
| 5. Test via "Discover" | **Script** | Run [`samples/test-model-via-gateway.py`](./samples/test-model-via-gateway.py). |

## Prerequisites

1. **Azure CLI** logged in (`az login`).
2. The **`AIGateway` preview enabled** for your subscription in **East US 2** or **Sweden Central** (check `ai.gateway.azure.com`).
3. Quota for `gpt-5.4` (`GlobalStandard`) in that region.
4. **Owner** or **User Access Administrator** on the resource group — the template creates a **role assignment** (Foundry User for the gateway's managed identity).
5. `pip install openai` for the test script.

---

## Steps 1–4 — deploy everything (Bicep)

Set your inputs once at the top — every command below reuses them:

```powershell
$sub = "<subscription-id>"         # your subscription id (GUID)
$rg  = "<your-rg>"                 # resource group to deploy into
$loc = "eastus2"                   # eastus2 or swedencentral (AIGateway preview regions)

az login
az account set --subscription $sub

az group create --name $rg --location $loc
az deployment group create --resource-group $rg --template-file main.bicep --parameters "@samples/parameters.json"
```

The template provisions the account, project, and `gpt-5.4` model (steps 1–2), then the
AI Gateway (`AIGateway` SKU), the Foundry model provider over **managed identity**, the
model with a **token-limit policy**, a runtime key, and the **Foundry User** role
assignment for the gateway's managed identity (steps 3–4).

> [!NOTE]
> Managed-identity role assignments can take a few minutes to propagate. If the model
> provider fails to validate on the first run, re-run the same `az deployment group create`.

After it succeeds, load the gateway name, base URL, and a runtime key into the remaining
variables (these read the deployment outputs, so they run **after** the deploy):

```powershell
$gw = az deployment group show -g $rg -n main --query properties.outputs.gatewayName.value -o tsv

$env:AI_GATEWAY_BASE_URL = az deployment group show -g $rg -n main --query properties.outputs.gatewayModelsBaseUrl.value -o tsv
$env:AI_GATEWAY_API_KEY  = az rest --method post --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.ApiManagement/service/$gw/apiKeys/default/listSecrets?api-version=2025-09-01-preview" --query primaryKey -o tsv
```

> The `default` runtime key is created by the template; `listSecrets` returns its
> `primaryKey`/`secondaryKey`. Or copy a key from the gateway **Keys** page at
> [`ai.gateway.azure.com`](https://ai.gateway.azure.com). Treat keys as secrets.

## Step 5 — test the model through the gateway ("Discover")

`AI_GATEWAY_BASE_URL` and `AI_GATEWAY_API_KEY` are already set from the step above, so just
run it — `--repeat` exercises the token-limit policy (expect HTTP 429 after the budget):

```powershell
pip install openai
python samples/test-model-via-gateway.py --prompt "What is the meaning of life?" --repeat 16
```

You would see the following message.
```powershell
...
[14/16] 429 THROTTLED by the gateway token rate-limit policy.
[15/16] 429 THROTTLED by the gateway token rate-limit policy.
[16/16] 429 THROTTLED by the gateway token rate-limit policy.

Done. 14 of 16 calls were throttled by the token rate-limit policy.
```

Or open the **Discover** page in the portal and select the model to invoke it in the
built-in playground.

## Parameters (Bicep)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `aiServicesName` | `foundry` | Base name for the account (a unique suffix is appended). |
| `projectName` | `gateway-project` | Project name. |
| `location` | `eastus2` | Region — restricted to the tier preview regions (`eastus2`, `swedencentral`). |
| `modelName` / `modelFormat` / `modelVersion` | `gpt-5.4` / `OpenAI` / `2026-03-05` | Model to deploy and import. |
| `modelSkuName` / `modelCapacity` | `GlobalStandard` / `40` | Deployment SKU and capacity. `gpt-5.4` may need more — set a value you have quota for (the reference deployment used 681). |
| `gatewayName` | auto | Globally unique AI Gateway name (`<name>.azure-api.net`). Auto-generated if empty. |
| `publisherEmail` / `publisherName` | `noreply@example.com` / `AI Gateway TC01` | Required by the API Management service. |
| `tokensPerMinute` | `100` | Token-limit policy budget per caller identity. Low by default so `--repeat` visibly throttles. |

## References

- [Azure-Samples/simple-foundry-hosted-agent-python-aigateway](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway) — the Bicep pattern this sample follows
- [Manage models and tools](https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools) (managed-identity import)
- [Quickstart: Create an AI Gateway tier instance](https://learn.microsoft.com/azure/api-management/quickstart-ai-gateway-create)
- [Govern, secure, and operate](https://learn.microsoft.com/azure/api-management/ai-gateway-govern-secure-assets)
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry) (Foundry User role)
