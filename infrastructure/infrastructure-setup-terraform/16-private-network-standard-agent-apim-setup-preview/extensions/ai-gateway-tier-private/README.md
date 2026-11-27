---
description: Terraform network-secured (VNet) AI Gateway for the Foundry golden path. One self-contained apply creates a private standard-agent foundation (VNet, private Foundry account + project, Cosmos DB / AI Search / Storage with private endpoints and DNS, capability host) and a private hub Foundry account behind an AI Gateway (Microsoft.ApiManagement/aigateways) with outbound private routing, then a ModelGateway connection on the project.
page_type: sample
products:
- azure
- azure-api-management
- azure-ai-foundry
urlFragment: ai-gateway-tier-private-terraform
languages:
- hcl
---

# Network-secured AI Gateway — self-contained (Terraform)

The Terraform version of the [Bicep `ai-gateway-tier-private`](../../../../infrastructure-setup-bicep/16-private-network-standard-agent-apim-setup/extensions/ai-gateway-tier-private/)
sample and the VNet (Path B) counterpart of [`01-connections/ai-gateway-tier`](../../../01-connections/ai-gateway-tier/).
**One `terraform apply`** creates everything: no separate foundation deployment first.

> [!IMPORTANT]
> Uses the new `Microsoft.ApiManagement/aigateways` resource type (the `service` + `AIGateway` SKU form can't
> be created anymore — see the [migration guide](https://learn.microsoft.com/azure/ai-gateway/ai-gateway-resource)).
> Everything deploys in one region (`location`, default `swedencentral`; `eastus2` is also verified) because
> the gateway's subnet must be in the gateway's region.

## Network posture — private behind, public in front

- **Outbound (private):** the gateway joins a dedicated subnet (`backend.subnet`, delegated to
  `Microsoft.App/environments`, with an NSG) and reaches the **private hub account** (`publicNetworkAccess:
  Disabled`) through its private endpoint, resolving it via the VNet-linked private DNS zones.
- **Inbound (public):** AI Gateway doesn't support inbound private endpoints or disabling public access yet.
  The agent's model calls are made by the project's **data proxy** in the agent subnet and reach the gateway's
  public endpoint with the runtime key; the gateway then reaches the model privately. Protect the endpoint
  with keys (and optionally an `ipFilter` policy).

## What it deploys

| File | Resources |
|------|-----------|
| [`main.tf`](./code/main.tf) | Resource group, naming |
| [`network.tf`](./code/network.tf) | VNet, agent subnet (delegated), private-endpoint subnet |
| [`data-stores.tf`](./code/data-stores.tf) | Storage, Cosmos DB, AI Search — private, Entra-only |
| [`dns.tf`](./code/dns.tf) | Private DNS zones + VNet links, private endpoints for the data stores and the agent's account |
| [`foundry.tf`](./code/foundry.tf) | The agent's private, VNet-injected Foundry account + project + connections + roles + capability host |
| [`gateway.tf`](./code/gateway.tf) | Gateway subnet + NSG, private hub account + model + private endpoint, **AI Gateway** (shared [`ai-gateway`](../../../01-connections/ai-gateway-tier/modules/ai-gateway/) module), and the **connection** (shared [`ai-gateway-connection`](../../../01-connections/ai-gateway-tier/modules/ai-gateway-connection/) module) |
| [`purge.tf`](./code/purge.tf) | Destroy-time purge of both soft-deleted Foundry accounts (with the agent-subnet cooldown from 15a) |

The foundation follows [`15a-private-network-standard-agent-setup`](../../../15a-private-network-standard-agent-setup/).
The agent's account has **no model deployment of its own** — the agent's model comes through the gateway.

## Prerequisites

1. Terraform **1.11 or later** and the Azure CLI, signed in.
2. `Microsoft.ApiManagement`, `Microsoft.CognitiveServices`, and `Microsoft.App` resource providers registered.
3. Quota for `gpt-5.4` (`GlobalStandard`, capacity `1`) in the region.
4. Rights to create resources **and role assignments** (the foundation grants the project identity data-store
   roles, and the gateway identity Foundry User) — for example Owner, or Contributor + Role Based Access Control
   Administrator.
5. For the agent step: `pip install "azure-ai-projects>=2.0.0" azure-identity`.

## Deploy

```powershell
cd code
Copy-Item terraform.tfvars.example terraform.tfvars   # set subscription_id
terraform init
terraform apply
```

The gateway key is read with `listSecrets` during the same apply (as an ephemeral value, never written to
state), so there's no manual key step.

## Create an agent

The project is private, so run the agent script from a machine inside the VNet (for example a jumpbox). For
testing from your workstation instead, open the agent's account (Entra ID auth is still required; the model
path stays private):

- `foundry_allowed_ip_ranges = ["<your public IP>"]` — only your IP, **or**
- `foundry_public_network_access_enabled = true` — all networks. Use this if the IP list still returns
  `403 Access denied due to Virtual Network/Firewall rules` (the Agents API can see a different source IP than
  `api.ipify.org`, especially from Azure-hosted machines).

Your identity also needs **Foundry User** on the project. Then, from the `code` folder:

```powershell
python ../../../../../infrastructure-setup-bicep/01-connections/public-byom-apim/samples/create-agent.py `
  --endpoint (terraform output -raw project_endpoint) `
  --model    (terraform output -raw model_reference)
```

The first call right after deployment can fail once with `424 CustomerManagedDownstreamError ... responded
with 500` while the data-proxy path warms up; retry after a minute.

You can also call the gateway directly — see [Test the gateway directly](../../../01-connections/ai-gateway-tier/README.md#test-the-gateway-directly-and-see-the-token-limit).

## Clean up

```powershell
terraform destroy
```

Expect about 15–20 minutes: destroy waits for the platform to release the agent subnet (900 s, as in 15a) and
the gateway subnet (300 s), then purges both soft-deleted Foundry accounts.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `subscription_id` | — | Subscription for everything. |
| `location` | `swedencentral` | `eastus2` or `swedencentral`; every resource deploys here. |
| `name_prefix` | `aigwpriv` | Prefix for generated names (random suffix appended). |
| `virtual_network_address_space` | `192.168.0.0/16` | VNet address space. |
| `agent_subnet_address_prefix` / `private_endpoint_subnet_address_prefix` | `192.168.0.0/24` / `192.168.1.0/24` | Agent and private-endpoint subnets. |
| `gateway_subnet_address_prefix` | `192.168.2.0/24` | Gateway subnet (`/27` minimum). Can't change after the gateway is created. |
| `foundry_allowed_ip_ranges` | `[]` | Testing convenience: client IPs allowed to reach the agent's account. |
| `foundry_public_network_access_enabled` | `false` | Testing convenience: open the agent's account to all networks (Entra auth still required). |
| `model_name` / `model_version` | `gpt-5.4` / `2026-03-05` | Model on the private hub, published through the gateway. |
| `model_sku_name` / `model_capacity` | `GlobalStandard` / `1` | Deployment SKU and capacity. |
| `tokens_per_minute` | `100` | Token limit per caller identity per minute. |
| `connection_name` | `ai-gateway` | Agents reference `<connection_name>/<model_name>`. |
| `credential_version` | `"1"` | Bump after rotating the gateway key. |
| `assign_foundry_user_role` | `true` | Create the gateway identity's Foundry User grant on the hub account. |
| `auth_header_name` / `auth_header_format` | `Authorization` / `Bearer {api_key}` | How the connection sends the gateway key. |

## Verification status

Verified end to end in Sweden Central with `terraform` 1.17, azapi 2.14, and azurerm 4.x:

- One `terraform apply` created the whole deployment (about 30 minutes; the VNet-integrated gateway took
  about 2.5 minutes).
- The private hub has `publicNetworkAccess: Disabled` and one private endpoint; the gateway's
  `backend.subnet` is the dedicated subnet. A direct call through the gateway (chat completions and
  Responses) returns `gpt-5.4` output, so the gateway reaches the hub privately.
- A prompt agent bound to `ai-gateway/gpt-5.4` on the private project answers through the data proxy →
  gateway → private hub path (after one transient 424 on the first call).
- If an Azure Policy in your tenant adds rules to (or replaces) the gateway subnet's NSG, `plan` can show a
  change on the NSG association; the sample's own rules are standalone resources so they don't conflict.

## References

- [Terraform golden path](../../../golden-path/README.md)
- [AI Gateway private networking lab](https://github.com/Azure/aigateway/tree/main/labs/18-private-networking)
- [Migrate to the AI Gateway resource type](https://learn.microsoft.com/azure/ai-gateway/ai-gateway-resource)
- [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway)
