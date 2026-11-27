---
description: Terraform AI Gateway hub-and-spoke module for the Foundry golden path. The hub deploys a Foundry model behind an AI Gateway (Microsoft.ApiManagement/aigateways) with a managed-identity provider, a token-limit policy, a callable alias, and a runtime key; the connection attaches any Foundry project (same or cross-subscription) with an "Admin-connected models" ModelGateway connection. An agent then references the model as <connectionName>/<modelName> via the Responses API.
page_type: sample
products:
- azure
- azure-api-management
- azure-ai-foundry
urlFragment: ai-gateway-tier-terraform
languages:
- hcl
---

# AI Gateway — hub + spoke connection (Terraform)

The Terraform version of the [Bicep AI Gateway tier sample](../../../infrastructure-setup-bicep/01-connections/ai-gateway-tier/)
and variant 5 of the [Terraform golden path](../../golden-path/README.md). A **hub** you deploy once puts a
Foundry model behind an AI Gateway; a **connection** attaches each consumer (spoke) project to it.

> [!IMPORTANT]
> **This sample uses the new `Microsoft.ApiManagement/aigateways` resource type.** AI Gateway moved off
> `Microsoft.ApiManagement/service` with the `AIGateway` SKU: new resources of that type can't be created
> since October 14, 2026, and existing ones are removed on January 15, 2027
> ([migration guide](https://learn.microsoft.com/azure/ai-gateway/ai-gateway-resource)). Compared with the
> earlier type: the runtime host comes from `properties.frontend.defaultHostname` (`*.ai.gateway.azure.com`),
> callers send keys as `Authorization: Bearer <key>`, and the callable model name is an
> **alias**. Resource shapes and the `2025-09-01-preview` API version follow the official
> [AI Gateway labs](https://github.com/Azure/aigateway/tree/main/labs).

Deploy the gateway in a region where AI Gateway is available (`eastus2` and `swedencentral` are verified).

## What's in this folder

```text
ai-gateway-tier/
├── README.md
├── modules/                      # shared building blocks (also used by the private sample)
│   ├── ai-gateway/               # gateway + Foundry User role + provider + model (token limit) + alias + runtime key
│   └── ai-gateway-connection/    # ModelGateway "Admin-connected models" connection on a project
├── hub/                          # ROOT 1 — run once: Foundry account + model + hub project + modules/ai-gateway
└── connection/                   # ROOT 2 — run per spoke project: reads gateway host + key, + modules/ai-gateway-connection
```

| Root | Creates | Who runs it, how often |
|------|---------|------------------------|
| [`hub/`](./hub/) | Resource group (optional), Foundry account (keyless) + model deployment + hub project, the AI Gateway with a managed-identity Foundry provider, the model with a per-identity **token-limit** policy, a callable **alias**, and a runtime **API key** | Admin, once |
| [`connection/`](./connection/) | A `ModelGateway` + `ApiKey` connection on an **existing** project. It reads the gateway host name and key from the hub itself, so there's no key copy-paste; the key is read as an [ephemeral value](https://developer.hashicorp.com/terraform/language/resources/ephemeral) and sent as a write-only attribute, so it's **never stored in Terraform state** | Admin, per consumer project (same or another subscription) |

The private (VNet) variant is [`16-.../extensions/ai-gateway-tier-private`](../../16-private-network-standard-agent-apim-setup-preview/extensions/ai-gateway-tier-private/);
it reuses the same two modules.

## Prerequisites

1. [Terraform](https://developer.hashicorp.com/terraform/install) **1.11 or later** (write-only attributes and ephemeral resources) and the Azure CLI, signed in (`az login`).
2. `Microsoft.ApiManagement` and `Microsoft.CognitiveServices` resource providers registered.
3. Quota for the model (`gpt-5.4`, `GlobalStandard`, capacity `1` by default) in `location`.
4. Admin roles — see [Personas & RBAC](../../golden-path/README.md#personas--rbac-roles). Besides creating
   resources, the hub **creates a role assignment** (gateway identity → Foundry User on the account), so you
   need Owner, User Access Administrator, Role Based Access Control Administrator, or Foundry Account Owner.
   **Contributor alone isn't enough** — see [No role-assignment rights?](#no-role-assignment-rights).
5. For the agent step: `pip install "azure-ai-projects>=2.0.0" azure-identity`.

## 1. Deploy the hub (once)

```powershell
cd hub
Copy-Item terraform.tfvars.example terraform.tfvars   # set subscription_id
terraform init
terraform apply
```

The gateway takes about a minute. Keep the outputs for the next step:

```powershell
terraform output
```

## 2. Attach a spoke project (per consumer project)

Use any existing Foundry project — for example the `ai_project_id` output of
[`41-standard-agent-setup`](../../41-standard-agent-setup/) — or, for a quick single-project test, the hub's
own `project_id` output.

```powershell
cd ../connection
Copy-Item terraform.tfvars.example terraform.tfvars
# set subscription_id (the spoke's), project_resource_id, and gateway_id (hub output)
terraform init
terraform apply
terraform output   # project_endpoint, model_reference (e.g. ai-gateway/gpt-5.4)
```

For a project in another subscription, set `subscription_id` to the spoke's subscription; `gateway_id` is a
full resource ID, so the hub can live anywhere your identity can read it.

## 3. Create an agent

Same as [golden-path step 6](../../golden-path/README.md#step-6--create-an-agent-both-paths): a **prompt
agent** bound to `<connectionName>/<modelName>`, invoked through the **Responses API**. From the
`connection` folder:

```powershell
python ../../../../infrastructure-setup-bicep/01-connections/public-byom-apim/samples/create-agent.py `
  --endpoint (terraform output -raw project_endpoint) `
  --model    (terraform output -raw model_reference)
```

## Test the gateway directly (and see the token limit)

From the `hub` folder:

```powershell
$gatewayId = terraform output -raw gateway_id
$keyName   = terraform output -raw api_key_name
$baseUrl   = terraform output -raw gateway_models_base_url
$model     = terraform output -raw model_name
$key = az rest --method post `
  --url "https://management.azure.com$gatewayId/apiKeys/$keyName/listSecrets?api-version=2025-09-01-preview" `
  --query primaryKey -o tsv

$body = @{ model = $model; messages = @(@{ role = "user"; content = "Say hi in five words." }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "$baseUrl/chat/completions" -Method Post -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $key" } -Body $body | ForEach-Object { $_.choices[0].message.content }

# A short burst trips the 100 tokens/minute limit: expect HTTP 429 after the first call or two.
1..5 | ForEach-Object {
  try { Invoke-RestMethod -Uri "$baseUrl/chat/completions" -Method Post -ContentType "application/json" `
          -Headers @{ Authorization = "Bearer $key" } -Body $body | Out-Null; "call $_ : 200" }
  catch { "call $_ : $($_.Exception.Response.StatusCode.value__)" }
}
```

Send **only** the `Authorization` header: the gateway rejects requests that carry both `api-key` and
`Authorization` with HTTP 400.

## No role-assignment rights?

If `terraform apply` fails with `AuthorizationFailed ... Microsoft.Authorization/roleAssignments/write`,
have an administrator grant the role and skip it in Terraform:

```powershell
# 1. Create just the gateway
terraform apply -var assign_foundry_user_role=false -target module.ai_gateway.azapi_resource.gateway

# 2. An administrator grants Foundry User to the gateway identity on the hub account
az role assignment create --assignee-object-id (terraform output -raw gateway_principal_id) `
  --assignee-principal-type ServicePrincipal --role 53ca6127-db72-4b80-b1b0-d745d6d5456d `
  --scope (terraform output -raw account_id)

# 3. Finish
terraform apply -var assign_foundry_user_role=false
```

## Clean up

Destroy the connection first, then the hub:

```powershell
cd connection; terraform destroy
cd ../hub;     terraform destroy
```

The hub purges its soft-deleted Foundry account during destroy (`purge_on_destroy = true`), so the name
and model quota are released immediately. AI Gateway resources aren't soft-deleted.

## Variables — `hub/`

| Variable | Default | Description |
|----------|---------|-------------|
| `subscription_id` | — | Hub subscription. |
| `location` | `eastus2` | Region for the account, project, and model. Any region; can differ from `gateway_location`. |
| `gateway_location` | `eastus2` | AI Gateway region: `eastus2` or `swedencentral`. |
| `existing_resource_group_name` | `""` | Deploy into an existing group instead of creating `rg-<name_prefix>-<suffix>`. |
| `name_prefix` | `aigwhub` | Prefix for generated names (random suffix appended). |
| `project_name` | `hub-project` | Hub project (admin workspace). |
| `model_name` / `model_version` / `model_format` | `gpt-5.4` / `2026-03-05` / `OpenAI` | Model deployed on the hub and published through the gateway. |
| `model_sku_name` / `model_capacity` | `GlobalStandard` / `1` | Deployment SKU and capacity (thousands of TPM). |
| `gateway_name` | auto | 3–24 lowercase letters, numbers, hyphens. |
| `alias_name` | `model_name` | Callable name sent in the request `model` field. |
| `tokens_per_minute` | `100` | Token limit per caller identity per minute (low so a burst shows 429). |
| `api_key_name` | `foundry-connection` | Runtime key the connections use. |
| `assign_foundry_user_role` | `true` | Create the gateway identity's Foundry User grant (needs role-assignment rights). |
| `purge_on_destroy` | `true` | Purge the soft-deleted account on destroy. |
| `tags` | `{}` | Tags on every resource. |

## Variables — `connection/`

| Variable | Default | Description |
|----------|---------|-------------|
| `subscription_id` | — | Spoke project's subscription. |
| `project_resource_id` | — | Existing project: `.../accounts/<account>/projects/<project>`. |
| `gateway_id` | — | Hub output `gateway_id`. |
| `api_key_name` | `foundry-connection` | Hub output `api_key_name`. |
| `model_name` / `model_version` | `gpt-5.4` / `2026-03-05` | Hub outputs `model_name` / `model_version`. |
| `connection_name` | `ai-gateway` | Agents reference `<connection_name>/<model_name>`. |
| `is_shared_to_all` | `true` | Show the connection in the portal "Admin-connected models" picker. |
| `credential_version` | `"1"` | Bump after rotating the gateway key; recreates the connection with the new key. |
| `auth_header_name` / `auth_header_format` | `Authorization` / `Bearer {api_key}` | How the connection sends the gateway key. |

## Verification status

Verified end to end in East US 2 with `terraform` 1.17 and azapi 2.14:

- `hub/` apply (13 resources, about 3.5 minutes) and `connection/` apply; a second `plan` on each shows **no changes**.
- Direct call through the gateway (`Authorization: Bearer`) returns a `gpt-5.4` completion; a short burst
  returns **HTTP 429** "Token limit is exceeded"; sending both `api-key` and `Authorization` returns HTTP 400.
- A prompt agent bound to `ai-gateway/gpt-5.4` answers through the Responses API
  (`public-byom-apim/samples/create-agent.py`).
- The gateway key isn't present in either root's Terraform state.
- `terraform destroy` removes everything and purges the soft-deleted account.

## References

- [Terraform golden path](../../golden-path/README.md) · [Bicep golden path](../../../infrastructure-setup-bicep/golden-path/README.md)
- [Migrate to the AI Gateway resource type](https://learn.microsoft.com/azure/ai-gateway/ai-gateway-resource)
- [AI Gateway CLI quickstart](https://learn.microsoft.com/azure/ai-gateway/get-started-cli) · [AI Gateway labs](https://github.com/Azure/aigateway/tree/main/labs)
- [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway)
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
