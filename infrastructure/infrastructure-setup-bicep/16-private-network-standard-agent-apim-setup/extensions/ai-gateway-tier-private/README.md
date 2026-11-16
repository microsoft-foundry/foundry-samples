---
description: The VNet (network-secured) variant of the AI Gateway tier for the Microsoft Foundry golden path. A self-contained, one-shot deployment that stands up the full private-network standard-agent foundation (VNet, private Foundry account + project, Cosmos/Search/Storage with private endpoints and DNS, capability host) AND adds a private hub Foundry account behind an AI Gateway tier (AIGateway SKU) with inbound-public + outbound-VNet-integrated networking, then a ModelGateway connection on the project. An agent consumes the model as <connectionName>/<modelName> via the Responses API.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-api-management
- azure-ai-foundry
urlFragment: ai-gateway-tier-private
languages:
- bicep
- json
---

# Network-secured AI Gateway tier (preview) — self-contained (Path B)

The **VNet (Path B)** variant of [`01-connections/ai-gateway-tier`](../../../01-connections/ai-gateway-tier/).
It is **self-contained and one-shot**: a single deployment stands up the full
[template 16](../../) private-network **standard-agent foundation** *and* the **AI Gateway tier**
(`AIGateway` SKU) in front of a **private** Foundry model — no separate "deploy template 16 first"
step. Like the sibling [`byom-cross-region`](../byom-cross-region/) extension, it references the
shared [`../../modules-network-secured/*`](../../modules-network-secured/) modules and inlines the
orchestration.

Unlike `byom-cross-region` (which uses a StandardV2 APIM and a manual `/inference` policy chain), this
variant uses the purpose-built AI Gateway tier with a native Foundry managed-identity provider and a
token-limit policy.

## Network posture — inbound-public + outbound-private

The gateway is **inbound-public, outbound-private** (the same posture as `byom-cross-region`):

- **Outbound** VNet integration (`virtualNetworkType: External` + a `virtualNetworkConfiguration`
  into a delegated subnet) lets the gateway reach the **private hub account** (`publicNetworkAccess:
  Disabled`) over the VNet.
- **Inbound** stays public (`publicNetworkAccess: Enabled`) so the model call — which originates from
  the **managed Agent Service inference plane**, not the delegated agent subnet — can reach the
  gateway. A fully-private gateway (inbound private endpoint + public access disabled) is **not**
  used here for that reason; see the [golden-path Path B notes](../../../golden-path/README.md#notes-for-the-vnet-path).

> [!IMPORTANT]
> The AI Gateway tier is a **release-gated public preview** (`AIGateway` SKU, `2025-09-01-preview`),
> and this sample supports only **Sweden Central**. The whole sample deploys in **one** region
> (the `region` parameter, `swedencentral`) because outbound integration requires the VNet in
> the **same region** as the gateway. `az bicep build` emits **BCP081** warnings for the preview
> provider/model/apiKey types (expected); the networking property shapes are verified against the
> live AIGateway SKU.

## What it deploys

A single deployment, in one resource group and region:

| Layer | Resource | Purpose |
|-------|----------|---------|
| Foundation | VNet (agent + private-endpoint subnets) | Network-secured perimeter for the agent and private endpoints |
| Foundation | Private Foundry account + project (`publicNetworkAccess: Disabled`) | The agent's account and project |
| Foundation | Cosmos DB, AI Search, Storage + private endpoints + private DNS | Agent dependencies, reachable only over the VNet |
| Foundation | Project capability host | The agent runtime |
| Gateway | `apim-outbound` subnet (delegated `Microsoft.Web/serverFarms`, NSG) | Outbound integration target for the gateway |
| Gateway | Private hub Foundry account (`publicNetworkAccess: Disabled`) + model + private endpoint | The model backend, reachable only over the VNet (reuses the foundation's DNS zones) |
| Gateway | AI Gateway tier (`AIGateway` SKU) + Foundry MI provider + gateway model (token-limit policy) + runtime key + Foundry User role | The gateway, importing the private hub over managed identity |
| Gateway | ModelGateway `ApiKey` connection on the project | Surfaces the model as `<connectionName>/<modelName>` for the agent |

## Prerequisites

1. **A resource group** in **Sweden Central** (or let the deploy target an existing
   one). Nothing needs to be deployed into it first.
2. **Azure CLI** logged in (`az login`) with the **`AIGateway` preview enabled** in that region.
3. Quota for the model (default `gpt-5.4`, `GlobalStandard`) in the region — the consumer account and
   the private hub each deploy one model (capacity `1` by default).
4. Admin roles — see [Personas & RBAC](../../../golden-path/README.md#personas--rbac-roles): **Foundry
   Account Owner** on the resource **+ API Management Service Contributor** on the resource group.
5. `pip install "azure-ai-projects>=2.0.0" azure-identity` for the agent step.

## Deploy

Optionally edit [`main.bicepparam`](./main.bicepparam) (for example, `region`, `modelName`, or the
`apimOutboundSubnetPrefix`), then:

```powershell
az group create --name <rg> --location swedencentral
az deployment group create --resource-group <rg> --template-file main.bicep --parameters main.bicepparam
```

The runtime key is read via `listSecrets` in the same deployment, so there is no manual key step.

## Create an agent

Identical to [golden-path step 6](../../../golden-path/README.md#step-6--create-an-agent-both-paths):
a **prompt agent** bound to `<connectionName>/<modelName>` (default `ai-gateway/gpt-5.4`), invoked
through the **Responses API**. Point the SDK at the deployment's `projectEndpoint` output (the private
project this sample creates). The private connectivity is already established by the deployment.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `region` | `swedencentral` | Single region for every resource. Only `swedencentral` is allowed. |
| `aiServices` | `aiservices` | Base name for the Foundry account (a unique suffix is appended). |
| `firstProjectName` | `project` | Base name for the project. |
| `modelName` / `modelFormat` / `modelVersion` | `gpt-5.4` / `OpenAI` / `2026-03-05` | Model deployed on the consumer account and the private hub; the gateway imports the hub deployment. |
| `modelSkuName` / `modelCapacity` | `GlobalStandard` / `1` | Deployment SKU and capacity. |
| `vnetName` / `agentSubnetName` / `peSubnetName` | `agent-vnet-test` / `agent-subnet` / `pe-subnet` | VNet and subnet names (created new). |
| `existingVnetResourceId`, `aiSearchResourceId`, `azureStorageAccountResourceId`, `azureCosmosDBAccountResourceId` | `''` | Optional — reuse existing resources instead of creating them. |
| `apimOutboundSubnetName` / `apimOutboundSubnetPrefix` | `apim-outbound` / `192.168.2.0/27` | New delegated outbound subnet (must be a free `/27` in the VNet). |
| `hubAccountName` | `aigwhub` | Base name for the private hub account (a unique suffix is appended). |
| `gatewayName` | auto | Globally unique gateway name. Auto-generated if empty. |
| `publisherEmail` / `publisherName` | `noreply@example.com` / `AI Gateway tier hub (private)` | Required by API Management. |
| `tokensPerMinute` | `100` | Token-limit policy budget per caller identity. Low by default so the token-limit policy is easy to test (HTTP 429 throttling). |
| `connectionName` | `ai-gateway` | Callers reference `<connectionName>/<modelName>`. |
| `authHeaderName` | `api-key` | Header the connection uses to send the gateway key. |
| `isSharedToAll` | `true` | Surface the connection in the portal "Admin-connected models" picker. |

## References

- [Foundry golden path](../../../golden-path/README.md) — this is the Path B (VNet) AI Gateway tier variant.
- [Public (non-VNet) AI Gateway tier](../../../01-connections/ai-gateway-tier/) — the Path A counterpart.
- [Configure private networking for AI Gateway tier (preview)](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking).
- [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway) — prompt agent + Responses API.
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry).
