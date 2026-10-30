# Agent Framework Responses Agent on BYO AKS

Clone this repository and change to the sample directory:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples/samples/python/hosted-agents/agent-framework/responses/03-byo-aks
```

This sample runs a basic Microsoft Agent Framework agent on a
customer-managed Azure Kubernetes Service (AKS) cluster through Microsoft
Foundry hosted agents. It uses the Responses protocol and an existing
Application Insights connection.

## How it works

The agent uses `FoundryChatClient` with `DefaultAzureCredential` and is served
by `ResponsesHostServer`. Foundry manages response history, so the Agent
Framework agent sets `store` to `false`.

The `azure.yaml` manifest configures the Foundry project's `primary`
`ManagedCluster` hosting instance with an existing AKS cluster, delegated agent
subnet, hosting and workload identities, storage account, and Application
Insights resource. It also creates and configures the Foundry project and a
`gpt-5.4-mini` model deployment, then deploys the container through a remote
build with 0.5 CPU and 1 GiB memory.

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

The following seven resource values must already exist:

| Value | Existing resource or setting |
| --- | --- |
| `AKS_RESOURCE_ID` | Resource ID of the AKS cluster used for managed-cluster agent hosting |
| `AGENT_SUBNET_RESOURCE_ID` | Resource ID of the subnet delegated for hosted-agent workloads |
| `HOSTING_IDENTITY_RESOURCE_ID` | Resource ID of the user-assigned managed identity used to manage hosting |
| `WORKLOAD_IDENTITY_RESOURCE_ID` | Resource ID of the user-assigned managed identity used by hosted workloads |
| `STORAGE_ACCOUNT_RESOURCE_ID` | Resource ID of the storage account used by hosted-agent sessions |
| `APPLICATIONINSIGHTS_RESOURCE_ID` | Resource ID of the existing Application Insights resource connected to the Foundry project |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Connection string for that Application Insights resource |

An existing Foundry project or model deployment is not required.

The AKS cluster, subnet, identities, storage account, Application Insights
resource, networking, workload identity federation, and RBAC assignments must
be prepared before using this sample. In particular, the cluster and subnet
must permit Foundry's hosted-agent traffic, the managed identities must have
the required federated credentials, and each identity must have the required
roles on the resources it accesses. This sample does not create or repair
those resources.

## Configure and provision

Create an `azd` environment and set the existing resource values:

```bash
azd env new
azd env set AKS_RESOURCE_ID "<aks-resource-id>"
azd env set AGENT_SUBNET_RESOURCE_ID "<agent-subnet-resource-id>"
azd env set HOSTING_IDENTITY_RESOURCE_ID "<hosting-identity-resource-id>"
azd env set WORKLOAD_IDENTITY_RESOURCE_ID "<workload-identity-resource-id>"
azd env set STORAGE_ACCOUNT_RESOURCE_ID "<storage-account-resource-id>"
azd env set APPLICATIONINSIGHTS_RESOURCE_ID "<application-insights-resource-id>"
azd env set APPLICATIONINSIGHTS_CONNECTION_STRING "<application-insights-connection-string>"
```

Provision the Foundry configuration described by the manifest:

```bash
azd provision
```

Provisioning creates and configures the Foundry project and the declared
`gpt-5.4-mini` deployment while registering the existing BYO-AKS, identity,
storage, and monitoring resources. It does not create those existing
resources. `azd` derives the agent service's
`AZURE_AI_MODEL_DEPLOYMENT_NAME` value from the deployment declared in
`azure.yaml`.

To use another compatible model, update the deployment name and model details
under `services.ai-project.deployments` in `azure.yaml` before provisioning.

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

Deploy the container to the configured managed-cluster hosting environment:

```bash
azd deploy
```

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

## Instrumentation

The hosted agent uses the `application-insights` connection declared in the
manifest and sets `ENABLE_INSTRUMENTATION` to `true`. After local or deployed
invocations, use the Foundry **Logs** view or the connected Application
Insights resource to inspect logs, traces, and request telemetry.

## Troubleshooting

- **Deployment cannot configure managed-cluster hosting:** verify all seven
  existing-resource values are complete resource IDs (except the Application
  Insights connection string) and refer to resources in the intended tenant and
  subscription.
- **The hosted agent cannot start or receive requests:** verify AKS and subnet
  networking, workload identity federation, and RBAC assignments.
- **Authentication fails locally:** run `az login` and confirm your identity has
  access to the provisioned Foundry project and model deployment.
- **No telemetry appears:** verify the Application Insights resource ID and
  connection string refer to the same existing resource.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Basic Agent Framework Responses sample](../01-basic/)
