# Foundry model connection with project managed identity

Connect an existing Foundry project directly to models on another existing
Foundry account, without deploying an API Management service or using API keys.
This sample uses the same `ApiManagement` connection category, project managed
identity (PMI), audience, Responses surface, and dynamic discovery metadata as
the Foundry model-resource connection UX.

```text
Prompt agent in source project
  -> foundry-models/<target-deployment>
  -> target Foundry account /openai/v1
     authenticated as the SOURCE PROJECT managed identity
```

`ApiManagement` is the connection category, not infrastructure provisioned by
this sample. For an actual gateway with policies, use
[`public-byom-apim`](../public-byom-apim/) or
[`ai-gateway-tier`](../ai-gateway-tier/) instead. The classic
[`connection-foundry.bicep`](../connection-foundry.bicep) creates a different
connection type and is not interchangeable for agent model references.

## Prerequisites

- An existing Foundry account and project, for example from
  [`40-basic-agent-setup`](../../40-basic-agent-setup/) or
  [`41-standard-agent-setup`](../../41-standard-agent-setup/).
  The source project must have a **system-assigned managed identity**.
- An existing target Foundry account (`AIServices`) with a model deployment
  that supports the Responses API. Use its **deployment name**, which can differ
  from the model name. This is not an Azure OpenAI account sample.
- Source and target must be in the same Entra tenant. The target can be in a
  different resource group or subscription.
- Azure CLI with Bicep. Deploy into the **source account's resource group**.
  The deploying identity needs connection-write permissions on the source
  project. With `assignBackendRole=true`, it also needs
  `Microsoft.Authorization/roleAssignments/write` at the target account and
  deployment permissions in the target resource group.
- The target endpoint must be reachable by the managed inference service.
  This sample does not provision private endpoints, networking, accounts,
  projects, model deployments, or agent infrastructure.
- The user running the agent script needs project data-plane permissions,
  independently of the project identity's target-account role.

The parameter example targets AzureCloud. Use the actual target endpoint and
appropriate `audience` and `foundryDataPlaneSuffix` for another cloud; this
sample does not establish feature availability in sovereign clouds.

## Deploy the connection and RBAC

From this directory, copy `samples/parameters.json` to a local parameter file
and replace all placeholders. Do not commit populated local files.
`targetOpenAIBaseUrl` must be the target's actual Foundry endpoint ending in
`/openai/v1`, with **no trailing slash or query string**. The target resource ID
must identify that same account.

```bash
az login
az account set --subscription "<source-subscription>"

az bicep build --file main.bicep --outfile azuredeploy.json

az deployment group create \
  --resource-group "<source-resource-group>" \
  --name foundry-model-connection \
  --template-file main.bicep \
  --parameters @parameters.local.json
```

The deployment:

1. Reads the existing source project's managed-identity principal ID.
2. Grants that identity **Foundry User (Azure AI User)**,
   `53ca6127-db72-4b80-b1b0-d745d6d5456d`, scoped only to the target account.
3. Creates a project-scoped, non-shared `ApiManagement` connection with
   `ProjectManagedIdentity` authentication and an explicit Cognitive Services
   audience. No keys or API-key `authConfig` are stored.

Set `assignBackendRole=false` if an administrator already provisioned the role.
That option does **not** make the target usable without equivalent permission.
The role assignment uses a deterministic name so repeat deployments reuse it.
If an identical assignment already exists under a different name, have an
administrator verify it and disable assignment rather than creating a duplicate.

Metadata matches the UX contract: `upstreamSurface: responses`,
`deploymentInPath: 'false'`, an empty static model list, and JSON-serialized
dynamic discovery for `/openai/deployments` and
`/openai/deployments/{deploymentName}` with `deploymentAPIVersion: '2022-12-01'`.
This sample does not change discovery endpoints or API versions.

Outputs include `connectionId`, `connectionName`, `projectEndpoint`,
`modelReference`, `targetEndpoint`, and `roleAssignmentId` (empty when skipped).
Creating the ARM resources does not prove that inference or discovery succeeds;
complete the agent invocation below. RBAC propagation can outlast deployment.

## Create and invoke an agent

Reuse the connection-agnostic
[`create-agent.py`](../public-byom-apim/samples/create-agent.py); no agent ARM
resource or duplicate script is needed. From this directory:

```bash
python -m pip install "azure-ai-projects>=2.0.0" azure-identity

PROJECT_ENDPOINT=$(az deployment group show \
  --resource-group "<source-resource-group>" \
  --name foundry-model-connection --query properties.outputs.projectEndpoint.value -o tsv)
MODEL_REFERENCE=$(az deployment group show \
  --resource-group "<source-resource-group>" \
  --name foundry-model-connection --query properties.outputs.modelReference.value -o tsv)

python ../public-byom-apim/samples/create-agent.py \
  --endpoint "$PROJECT_ENDPOINT" \
  --model "$MODEL_REFERENCE" \
  --agent-name foundry-pmi-sample-agent \
  --prompt "Say hello in five words."
```

The reference is `foundry-models/<existing-target-deployment>`. Use a **prompt
agent + Responses API**, not the classic Assistants threads/runs API.
Success means the script prints the created agent version and response text.
Use a unique agent name if an existing agent must not gain another version.
Agent calls consume model quota and can incur charges.

## Verification and troubleshooting

- Check the connection on the **source project**: category `ApiManagement`,
  authentication `ProjectManagedIdentity`, explicit audience, and the correct
  target endpoint and `metadata.ResourceId`.
- Check target-account IAM for Foundry User on the **source project's principal
  ID**, not the source account identity, application/client ID, or your user.
  Deployment ordering does not eliminate RBAC propagation delay; wait and retry.
- For upstream `Unauthorized`, check that role, audience, tenant, and target
  account match. Having Owner yourself does not grant the project identity access.
- For model-resolution errors, check the deployment name and connection name,
  model Responses support, and use of the prompt-agent Responses flow.
- A discovery timeout is separate from authentication. This template does not
  fix or extend the model gateway's discovery timeout.

## CI deployment fixture

The root `main.bicepparam` selects `tests/deploy.bicep` for the repository's
ephemeral deployment check. It provisions disposable source/target accounts
and a source project, then invokes the **actual** `main.bicep`, including its
project-identity role assignment. No model deployment or inference quota is
required: the fixture verifies ARM resources and RBAC, not inference or model
discovery. The pipeline owns resource-group cleanup. For an existing project,
deploy `main.bicep` with your own parameters as described above, not the fixture.

## Cleanup

Delete the sample agent versions, agent, and conversation created by the script
through the Foundry portal or SDK. Delete only the connection identified by the
`connectionId` output. If this deployment created the role assignment, remove
that assignment only after confirming no other connection or application needs
the same project identity's access to the target account.

Deleting the deployment record does **not** delete its resources. Do not delete
the existing source/target accounts, projects, resource groups, or model
deployments when cleaning up this layer-on-existing sample.
