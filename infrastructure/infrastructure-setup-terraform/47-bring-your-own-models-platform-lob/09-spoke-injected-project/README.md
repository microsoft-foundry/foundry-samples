# 09 — Spoke VNet-Injected Project (Data-Proxy variant)

**Purpose.** Stand up a **VNet-injected** Foundry project alongside the existing
non-injected sample-47 project so you can A/B the **Foundry data-proxy** on the
projects-scoped **Responses → APIM (BYOG)** path — the `hosted-mock` outlier in
the latency investigation.

The existing sample-47 project (`05-spoke-workload-project`) has
`networkInjections = null`, so its Responses→APIM calls **bypass the data-proxy**
(measured ~72 ms TTFT). This stack adds an account **with** `networkInjections`
into a delegated agent subnet, which provisions the agent runtime + data-proxy
inside the spoke VNet. The BYOG `gateway` connection is identical to sample 47,
so the only variable that changes between the two projects is **the data-proxy**.

## What it creates (in the EXISTING spoke RG / VNet)

| Resource | Notes |
|---|---|
| `snet-agent` (delegated `Microsoft.App/environments`) | Added to the existing spoke VNet (`10.20.5.0/24` by default; clear of bastion/jumpbox subnets). |
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

## Deploy

```bash
cd 09-spoke-injected-project
cp terraform.tfvars.example terraform.tfvars   # edit sub/tenant if needed
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

Same Path A call as the non-injected project, pointed at this project's endpoint:

```bash
PROJECT=$(terraform output -raw project_endpoint)   # or copy the value
MODEL="gateway/gpt-4.1"
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

req() {
  curl -s -o /dev/null -w '%{http_code} %{time_starttransfer} %{time_total}\n' \
    -X POST "$PROJECT/openai/v1/responses" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"input\":\"Say hello in one short sentence.\",\"stream\":true}"
}
echo "warmup: $(req)"
for i in $(seq 1 10); do printf 'run %2d: %s\n' "$i" "$(req)"; done
```

Compare the TTFT against the non-injected project (`hrbot`). The delta is the
**data-proxy tax** on the projects-scoped Responses→APIM path.

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

The destroy waits out the purge cooldown before removing `snet-agent`.
