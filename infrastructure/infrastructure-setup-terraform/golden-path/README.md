# Microsoft Foundry Agent — Golden Path (Terraform)

The Terraform edition of the [Bicep golden path](../../infrastructure-setup-bicep/golden-path/README.md):
the same six steps, mapped to the Terraform samples in this folder.

1. Create a Foundry resource (account)
2. Create a project
3. Create a VNet *(VNet path only)*
4. Create a gateway and add it to the project
5. Bring your own model (BYOM) through the gateway
6. Create an agent

Steps 1–5 are `terraform apply`; step 6 is SDK code.

---

## Path A — Non-VNet (public networking)

### Steps 1–2 — Foundry account + project

Deploy [`41-standard-agent-setup`](../41-standard-agent-setup/) (standard agent, BYO Storage / Search / Cosmos DB)
or [`00-basic`](../00-basic/). From `41`, keep the **`ai_project_id`** output — it's the input for steps 4–5.

### Steps 4–5 — Gateway + BYOM (pick one)

| Variant | When to use | Sample |
|---------|-------------|--------|
| **AI Gateway** — recommended for new gateways | A dedicated AI Gateway (`Microsoft.ApiManagement/aigateways`) with a token limit in front of a Foundry model, shared by one or more spoke projects (same or cross-subscription) | [`01-connections/ai-gateway-tier`](../01-connections/ai-gateway-tier/) — `hub/` **once**, then `connection/` per project (pass `ai_project_id` as `project_resource_id`) |
| **API Management (classic tiers)** | You run, or need, a full Azure API Management service (APIs, products, custom policies) | [`46-bring-your-own-models`](../46-bring-your-own-models/) (single subscription) or [`47-bring-your-own-models-platform-lob`](../47-bring-your-own-models-platform-lob/) (platform / line-of-business split, cross-subscription) |

Both produce a connection whose model the agent references as `<connectionName>/<modelName>`
(for example `ai-gateway/gpt-5.4`).

---

## Path B — VNet (network-secured)

| Steps | What | Sample |
|-------|------|--------|
| 1–5, one apply | **AI Gateway** in front of a private model, plus the full private standard-agent foundation | [`16-.../extensions/ai-gateway-tier-private`](../16-private-network-standard-agent-apim-setup-preview/extensions/ai-gateway-tier-private/) |
| 1–3 only | Private standard-agent foundation without a gateway | [`15a-private-network-standard-agent-setup`](../15a-private-network-standard-agent-setup/) or [`15b-...-byovnet`](../15b-private-network-standard-agent-setup-byovnet/) |
| 1–5, classic APIM | Platform hub / workload spoke with a private APIM, or a private-CA gateway | [`47-bring-your-own-models-platform-lob`](../47-bring-your-own-models-platform-lob/) · [`48-bring-own-model-private-ca`](../48-bring-own-model-private-ca/) |

With AI Gateway, the gateway's **outbound** traffic to the model is private (VNet integration + private
endpoint); its **inbound** endpoint stays public because AI Gateway doesn't support inbound private endpoints
yet. The agent's data proxy calls it with the runtime key.

---

## Step 6 — Create an agent (both paths)

A gateway-connected model works **only** with a **prompt agent** invoked through the **Responses API**; the
classic Assistants API fails with `invalid_engine_error: Failed to resolve model info`. Use the runnable script
from the Bicep samples (it's networking- and IaC-agnostic):

```powershell
pip install "azure-ai-projects>=2.0.0" azure-identity
python ../../infrastructure-setup-bicep/01-connections/public-byom-apim/samples/create-agent.py `
  --endpoint https://<account>.services.ai.azure.com/api/projects/<project> `
  --model    ai-gateway/gpt-5.4
```

The AI Gateway samples output both values (`project_endpoint`, `model_reference`). The full walkthrough of the
code is in the [Bicep golden path, step 6](../../infrastructure-setup-bicep/golden-path/README.md#step-6--create-an-agent-both-paths).

---

## Personas & RBAC roles

Same personas as the [Bicep golden path](../../infrastructure-setup-bicep/golden-path/README.md#personas--rbac-roles):

| Persona | Runs | Minimum role(s) |
|---------|------|-----------------|
| **Admin** | Steps 1–5 (`terraform apply`) | Rights to create the resources **and role assignments** — the AI Gateway samples grant the gateway's identity **Foundry User** on the model account. Owner, or Contributor + Role Based Access Control Administrator / User Access Administrator, or Foundry Account Owner on the account. Contributor alone fails with `AuthorizationFailed` on `roleAssignments/write`; see [No role-assignment rights?](../01-connections/ai-gateway-tier/README.md#no-role-assignment-rights). |
| **Developer** | Step 6 — create and test the agent | **Foundry User** on the project |
| **Consumer** | Invoke the agent | **Foundry User** on the project (Foundry Agent Consumer isn't sufficient yet for the prompt-agent Responses path) |

Grant the developer/consumer roles after deployment:

```powershell
az role assignment create --assignee-object-id <object-id> --assignee-principal-type User `
  --role 53ca6127-db72-4b80-b1b0-d745d6d5456d `
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
```
