---
description: AI Gateway tier (preview) hub-and-spoke module for the Foundry golden path. main.bicep deploys a standalone Microsoft.ApiManagement/aigateways resource that fronts a Foundry model over managed identity, with a callable model alias, a token-limit policy, and a runtime key; connection.bicep attaches a consumer (spoke) project to it with an "Admin-connected models" ModelGateway connection, same subscription or cross-subscription. An agent then references the model as <connectionName>/<modelName> via the Responses API.
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
| [`main.bicep`](./main.bicep) | **Hub** — Foundry account + hub project + model + standalone AI Gateway (`Microsoft.ApiManagement/aigateways`) + managed-identity provider + callable model alias + token-limit policy + runtime key | Once (the admin) |
| [`connection.bicep`](./connection.bicep) | **Spoke** — an "Admin-connected models" (`ModelGateway` + `ApiKey`) connection on an existing project, pointed at the hub | Per consumer project (same or cross-subscription) |

> [!IMPORTANT]
> AI Gateway is a **release-gated public preview**. This sample uses the standalone
> `Microsoft.ApiManagement/aigateways` resource with API version **`2026-11-01`**, not an API
> Management `service`. Its workspace, provider, model, alias, and API-key operations use
> **`2026-09-01-preview`** with the corresponding preview payloads. It deploys only where the
> preview is enabled — currently **East US 2** and **Sweden Central**. It sits on its own
> **`gatewayLocation`** so the account/model can live in another region.
>
> This is a different Azure resource type, **not an in-place upgrade** of an existing
> `Microsoft.ApiManagement/service`. Existing APIM resources are not removed by this template.
> The obsolete `publisherEmail` and `publisherName` parameters have been removed.

The runtime URL comes from the gateway's returned `properties.frontend.defaultHostname`; do not
assume it is `<gatewayName>.azure-api.net`. Bicep type catalogs that do not yet include the
resource/API-version combinations can emit **BCP081** warnings and cannot validate those resource
bodies.

The standalone gateway uses **`sku.name: 'Standard'`**. The former APIM `AIGateway` SKU name is
rejected by standalone gateway creation with `InvalidSkuName`.

## API versions and compatibility

The published November contract is valid, but its availability must be checked **per operation**.
A successful parent gateway GET does not establish support for provider/model/key creation or
`listSecrets`.

| Operation | Version used by this sample | Compatibility check in Sweden Central (2026-11-11) |
|-----------|-----------------------------|----------------------------------------------------|
| Parent gateway | `2026-11-01` | GET returned HTTP 200; isolated gateway creation succeeded with SKU `Standard`. |
| Default workspace GET | `2026-09-01-preview` | HTTP 200; November returned HTTP 400 `MissingOrIncorrectVersionParameter`. |
| Provider PUT / GET | `2026-09-01-preview` | Temporary provider creation returned HTTP 201; GET preserved managed-identity authentication. November PUT and GET rejected the version. |
| Model PUT / GET | `2026-09-01-preview` | Temporary registration returned HTTP 201; GET preserved both endpoint paths and the token policy. November PUT and GET rejected the version. |
| Callable model alias | `2026-09-01-preview` | Isolated alias deployment succeeded; GET returned both runtime endpoints. Alias name matches the caller's model name. |
| Runtime key PUT / GET | `2026-09-01-preview` | Temporary key creation returned HTTP 201; an existing key's GET returned HTTP 200. November PUT and GET rejected the version. |
| Runtime key `listSecrets` | `2026-09-01-preview` | HTTP 200 with both generated keys; November returned HTTP 400. Key values were not logged. |

Keep the API version and payload together: the tested preview provider/model bodies use
`displayName` and full endpoint paths (`/openai/v1/chat/completions`, `/openai/v1/responses`).
The November contract uses `name`; its examples use endpoint identifiers such as `chatCompletions`.
The token policy's `counterKey` remains an array containing `identity`; this was verified on
read-back, not reverted to the older string form.

Registered models are backend assets; the gateway also needs a **callable alias**. `gatewayAlias`
maps the unchanged caller model name to `gatewayModel`, using the preview routing order
`selectionOrder: ['priority']`. Registration alone left the isolated runtime endpoints returning
HTTP 404; publishing the alias made both endpoints callable.

The temporary child probes were deleted. An isolated gateway and connection were retained for the
live checks below. Availability can vary by rollout; recheck the target subscription and region
before changing either version or payload.

## Live validation result

The 2026-11-11 Sweden Central check reused an existing account, project, and `gpt-5-mini`
deployment (`2025-08-07`), rather than creating another backend.

| Check | Result |
|-------|--------|
| Compile, generated ARM consistency, Azure validation, and scoped what-if | **PASS** |
| Isolated gateway, provider/model/alias/key, scoped Foundry User assignment, and project connection | **PASS** |
| Direct Chat Completions and Responses inference | **PASS** — HTTP 200 and non-empty expected model text. |
| Gateway token policy at 100 TPM | **PASS** — a bounded burst returned HTTP 429 with `Token limit is exceeded`; invalid keys returned HTTP 401. |
| Existing backend, existing connections, and previous gateway unchanged | **PASS** — baseline comparisons matched, excluding the intended new connection. |
| Prompt-agent inference through the project connection | **BLOCKED** — the test tenant reached its directory-object quota during agent identity creation. Connection configuration and stored credentials were verified, but are not an inference pass. |

This does not validate the default `gpt-5.4` deployment or creation of a new Foundry backend.
Subscription Owner access does not resolve a tenant directory-object quota; that requires tenant
administration or the support contact in the service error.

## Prerequisites

1. **Azure CLI** logged in (`az login`) and the **AI Gateway preview enabled** in East US 2 / Sweden Central.
2. Quota for the model (`gpt-5.4`, `GlobalStandard`) in `location`.
3. Scoped Azure permissions as described below. GitHub repository access does not grant Azure
   deployment or role-assignment permissions.
4. `pip install "azure-ai-projects>=2.0.0" azure-identity` for the agent step.

### Required permissions

| Identity / task | Scope | Required access |
|-----------------|-------|-----------------|
| Hub deployer: create/update the Foundry account, model, project, gateway, and child resources | Hub resource group | **Contributor**, or a custom equivalent covering the required `Microsoft.CognitiveServices/accounts/*`, `Microsoft.ApiManagement/aigateways/*`, and deployment operations. |
| Hub deployer: grant the gateway access to Foundry | Created Foundry account, inherited from the hub resource group for a first deployment | `Microsoft.Authorization/roleAssignments/write`, for example **Role Based Access Control Administrator**. Contributor alone does not grant this permission. Administrators can constrain the grant to the **Foundry User** role and managed-identity principals. |
| Gateway system-assigned identity | Hub Foundry account | **Foundry User** (`53ca6127-db72-4b80-b1b0-d745d6d5456d`), assigned by `foundryUserRole` in `main.bicep`. Keep this assignment for keyless backend access. |
| Operator retrieving the runtime key | Gateway | `Microsoft.ApiManagement/aigateways/apiKeys/listSecrets/action`, included in the hub deployer's Contributor access. Reader alone is insufficient. |
| Spoke connection deployer | Spoke resource group | **Contributor**, or equivalent project-connection write and deployment permissions. |
| SDK caller creating/invoking the prompt agent | Spoke Foundry project | **Foundry User**. Management-plane Contributor access does not by itself grant this data-plane access. |

**API Management Service Contributor is not sufficient for this gateway:** it grants
`Microsoft.ApiManagement/service/*`, not `Microsoft.ApiManagement/aigateways/*`. The hub
deployer needs both resource-deployment access and the scoped role-assignment access above
(or equivalent inherited permissions). Activate eligible PIM roles before deploying.
Creating a new resource group additionally requires resource-group creation permission at
subscription scope; an administrator can instead create the test resource group for you.

## 1. Deploy the hub (once)

```powershell
$rg  = "<hub-rg>"
$loc = "eastus2"                 # eastus2 or swedencentral (AI Gateway preview regions)

az group create --name $rg --location $loc
az deployment group create --resource-group $rg --template-file main.bicep --parameters "@samples/parameters.json"
```

Capture the outputs the spoke connection needs:

```powershell
$gwUrl = az deployment group show -g $rg -n main --query properties.outputs.gatewayModelsBaseUrl.value -o tsv
$gwId = az deployment group show -g $rg -n main --query properties.outputs.gatewayId.value -o tsv
```

## 2. Get the gateway runtime key

The key is intentionally **not** a deployment output. Read it from the gateway (listSecrets on its
`apiKeys/default`):

```powershell
$key = az rest --method post `
  --url "https://management.azure.com$gwId/apiKeys/default/listSecrets?api-version=2026-09-01-preview" `
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

For interactive **direct gateway** inference, open the [AI Gateway portal](https://ai.gateway.azure.com),
select your gateway, open **Catalog**, select the model alias, choose **Chat completions** and a
runtime key, then send a short prompt. A 429 with `Token limit is exceeded` means the low sample
budget is throttling; wait for its retry interval before sending another prompt.

## Parameters — `main.bicep` (hub)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `location` | `eastus2` | Region for the account, project, and model. Any region; can differ from `gatewayLocation`. |
| `gatewayLocation` | `eastus2` | Region for the standalone AI Gateway — `eastus2` or `swedencentral`. |
| `aiServicesName` | `hub` | Base name for the hub account (a unique suffix is appended). |
| `projectName` | `hub-project` | Hub project (admin workspace) created under the account. |
| `modelName` / `modelFormat` / `modelVersion` | `gpt-5.4` / `OpenAI` / `2026-03-05` | Model deployed on the hub and imported into the gateway. |
| `modelSkuName` / `modelCapacity` | `GlobalStandard` / `1` | Deployment SKU and capacity. Default `1` keeps the sample deployable anywhere; raise it for real workloads. |
| `gatewayName` | auto | AI Gateway resource name: 3–24 lowercase letters, digits or hyphens; start and end with a letter or digit. Auto-generated if empty. Use the returned runtime hostname. |
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
- [AI Gateway ARM API contract (`2026-11-01`)](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/apimanagement/resource-manager/Microsoft.ApiManagement/AIGateway/stable/2026-11-01/openapi.json).
- [AI Gateway ARM API contract (`2026-09-01-preview`)](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/apimanagement/resource-manager/Microsoft.ApiManagement/AIGateway/preview/2026-09-01-preview/openapi.json) — the published preview specification covers the parent resource, not the child operation payloads tested above.
- [Assign Azure roles](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-portal) — prerequisites for the gateway-to-Foundry role assignment.
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry).
