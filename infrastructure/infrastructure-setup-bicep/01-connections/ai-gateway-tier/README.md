---
description: AI Gateway tier (preview) hub-and-spoke module for the Foundry golden path. main.bicep deploys a centralized AI Gateway tier (Azure API Management AIGateway SKU) that fronts a Foundry model over managed identity, with a token-limit policy and a runtime key; connection.bicep attaches a consumer (spoke) project to it with an "Admin-connected models" ModelGateway connection, same subscription or cross-subscription. An agent then references the model as <connectionName>/<modelName> via the Responses API.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-api-management
- azure-ai-foundry
urlFragment: ai-gateway-tier
languages:
- bicep
- json
---

# AI Gateway tier (preview) — hub + spoke connection

The **AI Gateway tier** variant of the [Foundry golden path](../../golden-path/README.md). It splits
the classic "gateway in front of a model" into a **centralized hub** you deploy once and a **spoke
connection** each consumer project attaches with — the pattern where one gateway serves many
Foundry projects/subscriptions.

| File | Role | Run |
|------|------|-----|
| [`main.bicep`](./main.bicep) | **Hub** — Foundry account + hub project + model + AI Gateway tier (`AIGateway` SKU) + managed-identity provider + token-limit policy + runtime key | Once (the admin) |
| [`connection.bicep`](./connection.bicep) | **Spoke** — an "Admin-connected models" (`ModelGateway` + `ApiKey`) connection on an existing project, pointed at the hub | Per consumer project (same or cross-subscription) |

> [!IMPORTANT]
> The AI Gateway tier is a **release-gated public preview**. The gateway is
> `Microsoft.ApiManagement/service` with the **`AIGateway` SKU** (`2025-09-01-preview`), which
> deploys only where it is enabled — currently **East US 2** and **Sweden Central**. It sits on its
> own **`gatewayLocation`** so the account/model can live in another region. `az bicep build` emits
> **BCP081** warnings for the preview `modelProviders`/`models`/`apiKeys` types (expected).

## Prerequisites

1. **Azure CLI** logged in (`az login`) and the **`AIGateway` preview enabled** in East US 2 / Sweden Central.
2. Quota for the model (`gpt-5.4`, `GlobalStandard`) in `location`.
3. Admin roles — see [Personas & RBAC](../../golden-path/README.md#personas--rbac-roles): **Foundry
   Account Owner** on the resource **+ API Management Service Contributor** on the resource group.
4. `pip install "azure-ai-projects>=2.0.0" azure-identity` for the agent step.

## 1. Deploy the hub (once)

```powershell
$rg  = "<hub-rg>"
$loc = "<azure-region>"          # Region for the Foundry account and model
$gatewayLoc = "swedencentral"   # AIGateway preview region, if enabled for your subscription

az group create --name $rg --location $loc
az deployment group create --resource-group $rg --template-file main.bicep --parameters "@samples/parameters.json" gatewayLocation=$gatewayLoc
```

Capture the outputs the spoke connection needs:

```powershell
$gwUrl = az deployment group show -g $rg -n main --query properties.outputs.gatewayModelsBaseUrl.value -o tsv
$gwName = az deployment group show -g $rg -n main --query properties.outputs.gatewayName.value -o tsv
```

## 2. Get the gateway runtime key

The key is intentionally **not** a deployment output. Read it from the gateway (listSecrets on its
`apiKeys/default`):

```powershell
$sub = (az account show --query id -o tsv)
$key = az rest --method post `
  --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.ApiManagement/service/$gwName/apiKeys/default/listSecrets?api-version=2025-09-01-preview" `
  --query primaryKey -o tsv
```

## 3. Attach a spoke project (per consumer project)

Run against the project you created in golden-path steps 1–2 — in this or **another subscription**
(`az account set --subscription <spoke-sub>` first for cross-subscription). Edit
`samples/connection.parameters.json` (`projectResourceId`, `gatewayModelsBaseUrl`), then:

```powershell
az deployment group create --resource-group <spoke-rg> --template-file connection.bicep `
  --parameters "@samples/connection.parameters.json" `
  --parameters gatewayModelsBaseUrl=$gwUrl gatewayRuntimeKey=$key
```

The connection's model is referenced as `<connectionName>/<modelName>` (default `ai-gateway/gpt-5.4`).

## 4. Create an agent

Identical to [golden-path step 6](../../golden-path/README.md#step-6--create-an-agent-both-paths):
a **prompt agent** bound to `<connectionName>/<modelName>`, invoked through the **Responses API**
(a gateway-connected model does **not** resolve through the classic Assistants API). Point the SDK
at the spoke project endpoint (the connection deployment's `projectEndpoint` output).

## Parameters — `main.bicep` (hub)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `location` | Resource group location | Region for the account, project, and model; can differ from `gatewayLocation`. Choose a region with model availability and quota. |
| `gatewayLocation` | `eastus2` | Region for the AI Gateway tier (`AIGateway` SKU) — `eastus2` or `swedencentral`. |
| `aiServicesName` | `hub` | Base name for the hub account (a unique suffix is appended). |
| `projectName` | `hub-project` | Hub project (admin workspace) created under the account. |
| `modelName` / `modelFormat` / `modelVersion` | `gpt-5.4` / `OpenAI` / `2026-03-05` | Model deployed on the hub and imported into the gateway. |
| `modelSkuName` / `modelCapacity` | `GlobalStandard` / `1` | Deployment SKU and capacity. Default `1` keeps the sample deployable anywhere; raise it for real workloads. |
| `gatewayName` | auto | Globally unique AI Gateway name (`<name>.azure-api.net`). Auto-generated if empty. |
| `publisherEmail` / `publisherName` | `noreply@example.com` / `AI Gateway tier hub` | Required by the API Management service. |
| `tokensPerMinute` | `100` | Token-limit policy budget per caller identity. |

## Parameters — `connection.bicep` (spoke)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `projectResourceId` | — | Resource ID of the existing spoke project (account + project must be in the deployment's resource group). |
| `gatewayModelsBaseUrl` | — | Hub output `gatewayModelsBaseUrl`. |
| `gatewayRuntimeKey` | — | Secure. The hub gateway runtime key from step 2. |
| `connectionName` | `ai-gateway` | Callers reference `<connectionName>/<modelName>`. |
| `modelName` / `modelVersion` / `modelFormat` | `gpt-5.4` / `2026-03-05` / `OpenAI` | Must match the hub model. |
| `authHeaderName` | `api-key` | Header the connection uses to send the gateway key. |
| `isSharedToAll` | `true` | Surface the connection in the portal "Admin-connected models" picker. |

## References

- [Foundry golden path](../../golden-path/README.md) — this module is BYOM variant 5.
- [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway) — prompt agent + Responses API.
- [Manage models and tools on the AI Gateway](https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools).
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry).
