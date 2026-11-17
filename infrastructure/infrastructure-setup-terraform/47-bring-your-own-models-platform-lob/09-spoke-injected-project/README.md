# 09 — Spoke VNet-Injected Project (Data-Proxy variant)

**Purpose.** Stand up a **VNet-injected** Foundry project alongside the existing
non-injected sample-47 project so you can compare the projects-scoped
**Responses → APIM (BYOG)** path with and without the **Foundry data-proxy**.

The existing sample-47 project (`05-spoke-workload-project`) has
`networkInjections = null`, so its Responses→APIM calls **bypass the data-proxy**.
This stack adds an account **with** `networkInjections`
into a delegated agent subnet, which provisions the agent runtime + data-proxy
inside the spoke VNet. The BYOG `gateway` connection is identical to sample 47,
so the only variable that changes between the two projects is **the data-proxy**.

## What it creates (in the EXISTING spoke RG / VNet)

| Resource | Notes |
|---|---|
| `snet-agent` (delegated `Microsoft.App/environments`) | Added to the existing spoke VNet (`10.20.5.0/24` by default; clear of bastion/jumpbox subnets). |
| Agent subnet route table | Forces default egress through the hub firewall, matching the existing spoke subnets. |
| Storage / Cosmos / AI Search (PNA disabled) + PEs | BYO agent stores required by Standard Agent Setup. |
| 3 private DNS zones (`blob`, `documents`, `search`) + VNet links | The Foundry/APIM zones are already hub-owned and linked. |
| Injected Foundry account (`networkInjections` → `snet-agent`) + PE | **This is what brings the data-proxy into the picture.** |
| Account + project capability hosts (project caphost bound to the stores) | Completes the private-agent metadata. |
| BYOG `gateway` ApiManagement connection + connected-model metadata | Same contract as sample 47's `05`. |
| RBAC + destroy-time account purge | Purge clears the subnet's `serviceAssociationLink` so destroy succeeds. |

## Prerequisites

Deploy the sample-47 chain first (this stack reads their state + contract):

- `01-hub-base` (hub DNS zones), `02-spoke-base` (spoke VNet/RG/PE subnet),
  `03-network-registration` (spoke↔hub zone links), `04-hub-workload`
  (APIM + `contracts/hub-workload.contract.json`).

Before deploying the injected account, update `provider_fqdn_allowlist` in
`01-hub-base/terraform.tfvars` to include the required runtime and managed-identity
destinations below **in addition to your existing approved provider FQDNs**, then
re-apply `01-hub-base`. Replace `<region>` with the agent's Azure region name,
for example `swedencentral`:

```hcl
# Add these entries to the existing provider_fqdn_allowlist.
"control-<region>.identity.azure.net",
"<region>.login.microsoft.com",
"*.identity.azure.net",
"login.microsoftonline.com",
"*.login.microsoftonline.com",
"*.login.microsoft.com",
"mcr.microsoft.com",
"*.data.mcr.microsoft.com",
"packages.aks.azure.com",
"acs-mirror.azureedge.net",
```

The agent subnet's default route uses the hub firewall. Without these HTTPS
allowances, authentication or runtime provisioning can fail. Keep TLS inspection
disabled for these destinations. See the required
[Foundry agent firewall allowances](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks#limitations)
and [Container Apps application rules](https://learn.microsoft.com/en-us/azure/container-apps/use-azure-firewall#application-rules).

## Deploy

```bash
cd 09-spoke-injected-project
cp terraform.tfvars.example terraform.tfvars   # set spoke_subscription_id and tenant_id
terraform init
terraform plan -out tfplan
terraform apply tfplan
```

> APIM/account/injection provisioning can take a while; the agent-subnet
> `serviceAssociationLink` also adds a destroy cooldown (~15 min).

## REQUIRED post-step — allowlist the new project MI

The new project has a **new** managed-identity `oid`. The APIM policy only
admits allowlisted `oid`s, so until you add it the gateway call returns **401**:

```bash
terraform output -raw project_managed_identity_object_id
# paste into ../06-hub-allowlist/allowlist.auto.tfvars (project_oid_allowlist)
cd ../06-hub-allowlist && terraform apply
```

## Run the data-proxy path (from the jumpbox)

First grant the signed-in caller **Azure AI Developer** on the new project.
The jumpbox's existing assignment is scoped to the non-injected project and
does not cover this one. Run the following from `09-spoke-injected-project`
using an identity allowed to assign roles:

```bash
PROJECT_ID="$(terraform output -raw foundry_agent_account_id)/projects/$(terraform output -raw project_name)"
CALLER_OID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --assignee-object-id "$CALLER_OID" \
  --assignee-principal-type User \
  --role "Azure AI Developer" \
  --scope "$PROJECT_ID"
```

Allow time for the role assignment to propagate. For a different caller, use
that caller's object ID and principal type instead.

A connected model must be selected in a **prompt agent definition**, not the
top-level `model` field of the Responses request. Create a temporary prompt
agent, then invoke it with `agent_reference`. Run the following on a client
that can reach the private project endpoint and has Azure CLI and Python.
Copy the Terraform output values if the client does not have the state files:

```bash
python -m pip install "azure-ai-projects==2.3.0" azure-identity
export PROJECT=$(terraform output -raw project_endpoint)
export MODEL=$(terraform output -raw gateway_model_example) # use gateway/mock to test the local mock
export AGENT_NAME="byog-comparison-$(date +%s)"
AGENT_VERSION=$(python - <<'PY'
import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential

with DefaultAzureCredential() as credential:
    with AIProjectClient(endpoint=os.environ["PROJECT"], credential=credential) as project:
        agent = project.agents.create_version(
            agent_name=os.environ["AGENT_NAME"],
            definition=PromptAgentDefinition(
                model=os.environ["MODEL"],
                instructions="Answer clearly and concisely.",
            ),
        )
        print(agent.version)
PY
)
export AGENT_VERSION
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

req() {
  curl -s -o /dev/null -w '%{http_code} %{time_starttransfer} %{time_total}\n' \
    -X POST "$PROJECT/openai/v1/responses" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"agent_reference\":{\"type\":\"agent_reference\",\"name\":\"$AGENT_NAME\",\"version\":\"$AGENT_VERSION\"},\"input\":\"Say hello in one short sentence.\",\"stream\":true}"
}
echo "warmup: $(req)"
for i in $(seq 1 10); do printf 'run %2d: %s\n' "$i" "$(req)"; done

python - <<'PY'
import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

with DefaultAzureCredential() as credential:
    with AIProjectClient(endpoint=os.environ["PROJECT"], credential=credential) as project:
        project.agents.delete_version(
            agent_name=os.environ["AGENT_NAME"],
            agent_version=os.environ["AGENT_VERSION"],
        )
PY
```

Optionally run the same call against the non-injected `05-spoke-workload-project`
endpoint, creating a prompt agent there as well, to compare time-to-first-byte
with and without the data-proxy. Curl's `time_starttransfer` measures the first
response byte, not necessarily the first generated token. If interrupted,
delete the temporary agent version using the cleanup command above.

## Confirm the data-proxy is engaged

Unlike the non-injected account, `networkInjections` here is **not** null:

```bash
ACCT_ID=$(terraform output -raw foundry_agent_account_id)
az rest --method get \
  --url "https://management.azure.com${ACCT_ID}?api-version=2025-04-01-preview" \
  --query "properties.networkInjections"
```

A populated `agent`-scenario injection (subnet id) confirms the runtime is
VNet-injected and the data-proxy is in the path.

## Teardown

```bash
terraform destroy
```

Destroy deletes the Foundry account, purges the soft-deleted account, then waits
15 minutes for the purge-triggered service-association-link cleanup before
removing the agent subnet's route association and `snet-agent`.
