# Agent Framework Responses agent on BYO AKS

This sample deploys a Microsoft Agent Framework hosted agent to a
customer-managed Azure Kubernetes Service (AKS) cluster connected to a new
Microsoft Foundry account and project. The agent gives brief responses and
supports multi-turn conversations.

> [!IMPORTANT]
> Bring-your-own AKS hosting is a preview capability. Your subscription,
> region, cluster, and Foundry extensions must be enabled and supported for
> the preview. Confirm the current requirements with your preview program
> before creating resources. AKS, the model deployment, ACR, and telemetry can
> incur charges.

## How it works

`azure.yaml` connects the new Foundry project to `AKS_RESOURCE_ID`, deploys
`gpt-oss-120b`, and builds the agent image remotely in Azure Container Registry
(ACR). Foundry hosts the Responses protocol server; the cluster provides the
agent sandbox nodes.

For deployment names beginning with `gpt-oss-`, the agent uses
`OpenAIChatCompletionClient` against the account's OpenAI v1 chat-completions
endpoint and filters Responses-only options before the model call. Other
deployment names use `FoundryChatClient`. Foundry manages conversation
history; the GPT-OSS path doesn't set a model-side storage option.

The sample derives the account-level OpenAI endpoint from
`FOUNDRY_PROJECT_ENDPOINT` or `AZURE_AI_PROJECT_ENDPOINT`. Set the optional
`AZURE_OPENAI_ENDPOINT` to the account endpoint when an explicit override is
needed. See the shared [Python startup configuration](../../../README.md#python-startup-configuration).

## Prerequisites

- An Azure subscription and region approved for the BYO AKS preview, with
  quota for AKS node pools and the `gpt-oss-120b` Global Standard deployment.
- An existing, compatible AKS cluster, or permission to create one with the
  optional scripts below. An existing resource group is required by the
  scripts.
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and
  [Azure Developer CLI (`azd`) 1.27.1 or later](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd).
  Install the Azure CLI `aks-preview` extension if using the cluster scripts.
- The `microsoft.foundry` azd extension bundle, including versions of
  `azure.ai.agents` and `azure.ai.projects` that support BYO AKS. The standard
  extension bundle may not yet contain a preview capability; obtain a
  compatible build through the preview program if needed.
- [Python 3.13](https://www.python.org/downloads/) and
  [uv 0.11.7](https://docs.astral.sh/uv/getting-started/installation/) for
  local development. `kubectl` and `kubelogin` are useful for checking the
  cluster.
- Permission to create the Foundry account, project, model and registry, and
  project data-plane access for deploying the agent. Subscription Contributor
  alone doesn't grant project data-plane access. See the
  [hosted-agent permissions reference](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions).

Install the extensions and authenticate both CLIs:

```bash
az extension add --name aks-preview --upgrade
azd extension install microsoft.foundry --source azd
az login
azd auth login
```

### AKS requirements

Use an AKS Standard cluster, not AKS Automatic or Arc-enabled Kubernetes. The
preview requirements in the source guide include Kubernetes 1.31 or later,
Azure CNI Overlay or Pod Subnet, network policy, a managed cluster identity,
OIDC issuer and Workload Identity. The system pool must be in System mode.
The dedicated agent pool must be in User mode, use Azure Linux and
`KataVmIsolation`, contain at least one node, and have the label
`agents.ai.azure.com/sandbox-node=true`.

The source preview guide specified a Kata node image of
`AKSAzureLinux-V3katagen2-202608.14.0` or later and identified AKS 1.36.3 as a
product-qualified version. Check the current preview requirements and regional
availability rather than assuming these values remain current. Verify the
cluster and pool are provisioned and their nodes are ready.

## Prepare the AKS cluster

If you already have a compatible cluster, record its Azure resource ID and
continue to [Configure and provision Foundry](#configure-and-provision-foundry).
Otherwise, use the scripts to create a cluster and sandbox pool. 

Clone this repository and change to the sample directory:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples/samples/python/hosted-agents/agent-framework/responses/03-byo-aks
```

Choose names that aren't already in use, an approved subscription and region,
and a currently qualified AKS version. Create the resource group if necessary,
review the preview, and only then apply it:

**Bash**

```bash
export AZURE_SUBSCRIPTION_ID="<subscription-id>"
export AZURE_LOCATION="<preview-supported-region>"
export RESOURCE_GROUP="<resource-group>"
export AKS_NAME="<new-cluster-name>"
export KUBERNETES_VERSION="<qualified-aks-version>"

az group create --subscription "$AZURE_SUBSCRIPTION_ID" \
  --name "$RESOURCE_GROUP" --location "$AZURE_LOCATION"
bash ./provision_aks.sh
bash ./provision_aks.sh --apply
```

**PowerShell**

```powershell
$env:AZURE_SUBSCRIPTION_ID = "<subscription-id>"
$env:AZURE_LOCATION = "<preview-supported-region>"
$env:RESOURCE_GROUP = "<resource-group>"
$env:AKS_NAME = "<new-cluster-name>"
$env:KUBERNETES_VERSION = "<qualified-aks-version>"

az group create --subscription $env:AZURE_SUBSCRIPTION_ID `
  --name $env:RESOURCE_GROUP --location $env:AZURE_LOCATION
.\provision_aks.ps1
.\provision_aks.ps1 -Apply
```

Both scripts print `AKS_RESOURCE_ID`. During apply, they select VM sizes
available to the subscription, preferring `Standard_D4ds_v5` for the system
pool and `Standard_D8as_v5` for the sandbox pool. Automatic selection requires
at least 4 vCPUs and 16 GiB for the system pool and 8 vCPUs and 32 GiB for
the sandbox pool. Set `SYSTEM_NODE_VM_SIZE` or `SANDBOX_NODE_VM_SIZE` to
choose an available size explicitly. The SKU query doesn't prove that a
selected size or node image is qualified for the preview or that quota is
available.

> [!WARNING]
> Existing clusters and a pool named `sandbox` are reused without being
> updated or fully validated. The scripts don't create Foundry identities or
> storage, attach a custom subnet, configure ACR or image-admission policy,
> or change network security group rules. They don't complete Foundry
> onboarding or verify all networking and node-image requirements. Review the
> cluster and network configuration before proceeding.

## Configure and provision Foundry

The Foundry hosting configuration requires a hosting managed identity, a
separate workload managed identity, and a dedicated storage account. The
hosting identity needs Reader and Kubernetes Extension Contributor on the
cluster and Managed Identity Federated Identity Credential Contributor on the
workload identity. The workload identity needs Storage Blob Data Contributor
on the storage account. The storage account must be StorageV2 with Hot tier,
HTTPS and TLS 1.2 or later, shared-key and anonymous blob access disabled,
and hierarchical namespace disabled.

If your account has **Owner**, or **Contributor** and **Role Based Access
Control Administrator**, at subscription scope, Foundry provisioning can
create these supporting resources and role assignments. Otherwise, ask an
administrator to prepare them and supply their resource IDs as described
below. You still need permission to provision the Foundry account and project.

Create an azd environment from the sample directory:

```bash
azd env new "<environment-name>" --subscription "<subscription-id>" --location "<preview-supported-region>"
azd env set AKS_RESOURCE_ID "<aks-resource-id>"
azd env set AZURE_RESOURCE_GROUP "<foundry-resource-group>"
```

The projects extension creates and connects Application Insights during
provisioning. For this path, don't pre-create it or set
`APPLICATIONINSIGHTS_RESOURCE_ID` or `APPLICATIONINSIGHTS_CONNECTION_STRING`.

### Administrator-prepared supporting resources

If your account cannot create the supporting resources or assign their required roles. Ask your subscription administrator to prepare the resources and permissions listed below, then provide their resource IDs. Your account still needs permission to provision the Foundry account. 
| Resource                                | Required configuration or permissions                                                                                                                                         |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hosting user-assigned managed identity  | Reader and Kubernetes Extension Contributor on the AKS cluster; Managed Identity Federated Identity Credential Contributor on the workload identity.                          |
| Workload user-assigned managed identity | A separate identity for session snapshots, with Storage Blob Data Contributor on the storage account.                                                                         |
| Storage account                         | A dedicated `StorageV2` account with Hot tier, HTTPS only, TLS 1.2 or later, shared-key access disabled, anonymous blob access disabled, and hierarchical namespace disabled. |


Otherwise, add these properties under `services.ai-project.agentHosting` in
`azure.yaml`, keeping `clusterResourceId` and the rest of the manifest:

```yaml
hostingManagementIdentityResourceId: ${HOSTING_IDENTITY_RESOURCE_ID}
storageAccountResourceId: ${STORAGE_ACCOUNT_RESOURCE_ID}
workloadIdentityResourceId: ${WORKLOAD_IDENTITY_RESOURCE_ID}
```

Set the administrator-provided IDs in the selected azd environment:

```bash
azd env set HOSTING_IDENTITY_RESOURCE_ID "<hosting-identity-resource-id>"
azd env set STORAGE_ACCOUNT_RESOURCE_ID "<storage-account-resource-id>"
azd env set WORKLOAD_IDENTITY_RESOURCE_ID "<workload-identity-resource-id>"
```

### Provision and deploy

Enable the BYO AKS preview flag in the shell that runs `azd provision`:

**Bash**

```bash
export AZD_ALPHA_ENABLE_AGENTS_BYO_AKS=true
azd provision
azd deploy
```

**PowerShell**

```powershell
$env:AZD_ALPHA_ENABLE_AGENTS_BYO_AKS = "true"
azd provision
azd deploy
```

The manifest creates a `gpt-oss-120b` model deployment and uses an ACR remote
build for the agent image. Confirm the agent version is ready with
`azd ai agent show --output json` and `azd ai agent doctor`.

The GPT-OSS path calls the account-level OpenAI endpoint directly. The
deployed agent identity therefore needs account-scope model access, such as
**Cognitive Services OpenAI User**, unless equivalent access is already
granted. Ask an authorized administrator to assign the least-privileged role
if needed; see [account-level access](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#account-level-access).
If `AZURE_OPENAI_ENDPOINT` targets another account, the access is needed on
that account instead. Allow time for role assignments to propagate.

## Invoke and monitor

Start a remote session, then send a follow-up in the same session:

```bash
azd ai agent invoke --new-session "Remember the code word QUARTZ for this conversation. Reply with a brief acknowledgment."
azd ai agent invoke "What code word did I ask you to remember?"
```

The second response should contain `QUARTZ`. You can also use the Foundry
Playground. To inspect the session, substitute the session ID returned by the
first invocation:

```bash
azd ai agent monitor --session-id "<session-id>" --type system --tail 100
azd ai agent monitor --session-id "<session-id>" --type console --tail 100
```

Inspect the project's traces and connected Application Insights resource
separately. A successful response, console log, or root invocation span
doesn't establish that model-call spans, token counts, or prompt content were
captured. The GPT-OSS compatibility path isn't guaranteed to emit model spans;
verify them explicitly. Message-content capture is a separate,
privacy-sensitive configuration choice.

## Run locally

After provisioning a project and model, copy the example environment file in
`src/agent-framework-agent-basic-responses-byoaks` to `.env` and set the
project endpoint and model deployment name. Don't commit `.env`.

```bash
cd src/agent-framework-agent-basic-responses-byoaks
uv sync --frozen
uv run --frozen python main.py
```

Invoke the local host with an appropriate Responses client, or start it with
`azd ai agent run` from the sample directory and invoke it with
`azd ai agent invoke --local "Hello"`. A local model call tests the agent
logic, not AKS placement.

## Troubleshooting

- **Provisioning doesn't recognize `agentHosting` or the preview flag:** check
  that the preview-enabled projects and agents extensions are installed and
  that the subscription and region are approved.
- **The agent can't pull its image or start:** check the ACR connection and
  permissions, AKS network access, Kata node image, node labels and pool
  readiness.
- **Model calls return authorization errors:** check the invoking identity's
  project permissions and the agent identity's access to the account-level
  OpenAI endpoint.
- **A different model fails:** update both the model deployment in
  `azure.yaml` and the agent's `AZURE_AI_MODEL_DEPLOYMENT_NAME`. GPT-OSS
  deployment names must begin with `gpt-oss-` for the sample to select the
  chat-completions compatibility path.
- **Traces are incomplete:** first verify a successful invocation and the
  Application Insights connection. Check model spans and content capture
  separately from the root trace.

The shared cloud-test matrix doesn't provide a preview-enabled BYO AKS
cluster or GPT-OSS deployment, so the sample's multi-turn contract is excluded
from that matrix. A live test in an approved environment is needed to verify
cluster placement.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Basic Agent Framework Responses sample](../01-basic/)
