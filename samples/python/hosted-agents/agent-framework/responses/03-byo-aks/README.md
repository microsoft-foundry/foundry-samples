# Agent Framework Responses Agent on BYO AKS

Clone this repository and change to the sample directory:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples/samples/python/hosted-agents/agent-framework/responses/03-byo-aks
```

This sample runs a basic Microsoft Agent Framework agent on a
customer-managed Azure Kubernetes Service (AKS) cluster through Microsoft
Foundry hosted agents. It uses the Responses protocol, an existing Foundry
project, and an existing model deployment.

> [!IMPORTANT]
> This is a brownfield sample. The existing project's parent Foundry account
> must already have a successful customer-managed AKS `ManagedCluster` entry in
> `properties.agentHostingConfigurations`. The included provisioning scripts
> only create or reuse an AKS cluster and its `sandbox` KataVmIsolation node
> pool. They do **not** complete Foundry BYO-AKS onboarding, create identities,
> storage, or a subnet, or register the cluster as a Foundry hosting
> configuration.

## How it works

The agent uses `FoundryChatClient` with `DefaultAzureCredential` and is served
by `ResponsesHostServer`. Foundry manages response history, so the Agent
Framework agent sets `store` to `false`.

The `azure.yaml` manifest targets an existing Foundry project endpoint and
deploys the container through a remote build with 0.5 CPU and 1 GiB memory.
The parent Foundry account's existing hosting configuration determines that
the hosted agent runs on customer-managed AKS.

## Prerequisites

Install:

- [Azure Developer CLI (`azd`) 1.27.1 or later](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
- [Python 3.13](https://www.python.org/downloads/) and
  [uv 0.11.7](https://docs.astral.sh/uv/getting-started/installation/)
- The Microsoft Foundry `azd` extension:

  ```bash
  azd ext install microsoft.foundry
  ```

Authenticate with `azd auth login` and `az login`.

The following deployment values must already exist:

| Value | Existing resource or setting |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Endpoint of the existing Foundry project |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Name of a compatible model deployment that already exists in the project |
| `FOUNDRY_ACCOUNT_RESOURCE_ID` | Resource ID of the parent Foundry account; used only for preflight verification and documentation |

The parent account's `properties.agentHostingConfigurations[]` must contain an
entry with:

- `name`
- `hostingType` set to `ManagedCluster`
- `hostingManagementIdentityResourceId`
- `workloadIdentityResourceId`
- `clusterResourceId`
- `storageAccountResourceId`

The hosting management identity must also appear in the account's
`identity.userAssignedIdentities`. The AKS cluster, subnet, identities, storage
account, networking, workload identity federation, and RBAC assignments must
otherwise be prepared before using this sample.

## Optional: Create the AKS cluster and sandbox pool

The AKS provisioning scripts create a sandbox node pool with
`--workload-runtime KataVmIsolation`; this currently requires the Azure CLI
`aks-preview` extension. Use the scripts at the sample root to create a test
AKS cluster and sandbox node pool. Use Bash on macOS/Linux, and use PowerShell
on Windows.

Bash:

```bash
export AZURE_SUBSCRIPTION_ID="<subscription id>"
export AZURE_LOCATION="<supported private preview Azure region>"
export RESOURCE_GROUP="<new resource group name>"
export AKS_NAME="<new AKS cluster name>"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
az group create --name "$RESOURCE_GROUP" --location "$AZURE_LOCATION" --output none

bash ./provision_aks.sh
bash ./provision_aks.sh --apply
```

PowerShell:

```powershell
$env:AZURE_SUBSCRIPTION_ID = "<subscription id>"
$env:AZURE_LOCATION = "<supported private preview Azure region>"
$env:RESOURCE_GROUP = "<new resource group name>"
$env:AKS_NAME = "<new AKS cluster name>"

az account set --subscription $env:AZURE_SUBSCRIPTION_ID
az group create --name $env:RESOURCE_GROUP --location $env:AZURE_LOCATION --output none

.\provision_aks.ps1
.\provision_aks.ps1 -Apply
```

Preview first, and then rerun with `--apply` or `-Apply`.

During apply, the scripts query VM SKUs available to the subscription in
`AZURE_LOCATION`. They select the closest qualifying general-purpose VM sizes
for the system pool (at least 4 vCPUs and 16 GiB memory) and sandbox pool (at
least 8 vCPUs and 32 GiB memory), preferring the previously tested
`Standard_D4ds_v5` and `Standard_D8as_v5` when available. To require specific
sizes, set `SYSTEM_NODE_VM_SIZE` and `SANDBOX_NODE_VM_SIZE`; the scripts
validate explicit sizes against the regional SKU list before provisioning.

If sandbox node-pool creation fails with
`unrecognized arguments: --workload-runtime KataVmIsolation --ssh-access disabled`,
install or update `aks-preview`, and then rerun the script.

> [!WARNING]
> These scripts only create or reuse AKS and the `sandbox` KataVmIsolation node
> pool. They don't create identities, storage, a subnet, or Foundry
> registration. They also don't attach a separately managed subnet, create ACR
> resources, enable Azure Policy, or configure an ACR image-admission policy.
> Existing clusters and pools are reused without being updated or fully
> validated.

## Configure and provision

Create an `azd` environment and set the existing project, model, and account
values:

```bash
azd env new
azd env set FOUNDRY_PROJECT_ENDPOINT "<foundry-project-endpoint>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<existing-model-deployment-name>"
azd env set FOUNDRY_ACCOUNT_RESOURCE_ID "<foundry-account-resource-id>"
```

Before provisioning, verify the parent account's hosting registration.

Bash:

```bash
FOUNDRY_ACCOUNT_RESOURCE_ID="$(azd env get-value FOUNDRY_ACCOUNT_RESOURCE_ID)"
az resource show \
  --ids "$FOUNDRY_ACCOUNT_RESOURCE_ID" \
  --api-version 2026-09-15-preview \
  --query "properties.agentHostingConfigurations"
```

PowerShell:

```powershell
$foundryAccountResourceId = azd env get-value FOUNDRY_ACCOUNT_RESOURCE_ID
az resource show `
  --ids $foundryAccountResourceId `
  --api-version 2026-09-15-preview `
  --query "properties.agentHostingConfigurations"
```

The command must return a `ManagedCluster` entry with the required fields
listed above. Don't continue if the result is `null` or empty.

Target the existing project and provision the supported sample-owned services
declared by the manifest:

```bash
azd provision
```

`azd provision` does not create the project or model deployment and does not
register AKS. The model named by `AZURE_AI_MODEL_DEPLOYMENT_NAME` must already
exist in the target project.

## Run and invoke locally

Synchronize the locked Python environment:

```bash
cd src/agent-framework-agent-basic-responses-byoaks
uv sync --frozen
cd ../..
```

Start the local host:

```bash
azd ai agent run
```

In another terminal, from the sample directory, invoke it:

```bash
azd ai agent invoke --local "Reply briefly and include the exact marker BYO-AKS-OK."
```

The agent listens on `http://localhost:8088`.

## Deploy and invoke

Deploy the agent to the existing project:

```bash
azd deploy
```

The Foundry account's existing hosting configuration determines that the agent
runs on customer-managed AKS. `azd deploy` does not register the cluster.

Invoke the deployed agent:

```bash
azd ai agent invoke "Reply briefly and include the exact marker BYO-AKS-OK."
```

## Test in the Foundry Playground

Open the deployed agent in the **Foundry Playground**, start a new conversation,
and send a prompt such as:

```text
Reply briefly and include the exact marker BYO-AKS-OK.
```

The response should include `BYO-AKS-OK`.

## Troubleshooting

- **Preflight returns `null` or an empty array:** complete Foundry BYO-AKS
  onboarding on the parent account before using this sample.
- **Deployment doesn't use the expected cluster:** verify the parent account's
  `ManagedCluster` hosting entry and its identity, cluster, and storage resource
  IDs. The manifest and provisioning scripts don't register hosting.
- **The hosted agent cannot start or receive requests:** verify AKS and subnet
  networking, workload identity federation, and RBAC assignments.
- **Authentication fails locally:** run `az login` and confirm your identity has
  access to the existing Foundry project and model deployment.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Basic Agent Framework Responses sample](../01-basic/)
