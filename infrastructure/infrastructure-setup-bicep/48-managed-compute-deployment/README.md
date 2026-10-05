---
description: Deploy an OSS model to Microsoft Foundry managed compute under an existing AIServices account with Bicep or generated ARM JSON.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-ai-foundry
urlFragment: foundry-managed-compute-oss-model-bicep-arm
languages:
- bicep
- json
---

# Deploy OSS models to Microsoft Foundry managed compute using Bicep or ARM JSON

This sample declaratively creates one
`Microsoft.CognitiveServices/accounts/managedComputeDeployments@2026-07-15-preview`
child resource under an existing Microsoft Foundry account. `main.bicep` is the
source of truth; `azuredeploy.json` is generated from it and is the separately
documented raw ARM JSON method.

## Support model and limitations

This sample uses Bicep's generic ARM resource declaration and compiles it into
an ARM JSON template. Both formats call the same
`Microsoft.CognitiveServices/accounts/managedComputeDeployments` resource API;
there is no separate Bicep service endpoint.

The current released Bicep tooling can emit warning `BCP081` for this resource
and API version when its local type catalog doesn't contain the corresponding
schema. The compiler still generates the ARM template, but it can't validate
managed-compute property names and types before deployment. Azure Resource
Manager and the Cognitive Services resource provider perform the authoritative
validation when the template is submitted.

This repository doesn't currently provide an Azure Verified Module for managed
compute. The template is a standalone resource example. The
`deploymentNameSeed` parameter is required so redeployments don't silently
create another billable child resource. Generate it once, then reuse it when
redeploying or changing capacity so Bicep and ARM target the existing
deployment.

> [!WARNING]
> Managed compute is billed hourly per accelerator for as long as the deployment
> exists, including periods with no traffic. This sample uses one accelerator.
> Check the [current Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/)
> before deployment. Deleting the deployment releases the accelerator and stops
> its billing.

## Choose a method

All six methods deploy the same resource and defaults.

| Method | Sample |
| --- | --- |
| Azure CLI | [Azure CLI](../../../samples/cli/foundry-models/managed-compute-deployment/) |
| Direct ARM REST API | [REST API](../../../samples/REST/managed-compute-deployment/) |
| Python management SDK | [Python SDK](../../../samples/python/foundry-models/managed-compute-deployment/) |
| Bicep | This sample (`main.bicep`) |
| ARM JSON template | This sample (`azuredeploy.json`) |
| Terraform AzAPI | [Terraform](../../infrastructure-setup-terraform/48-managed-compute-deployment/) |

## Deployment configuration

| Parameter | Default |
| --- | --- |
| `foundryAccountName` | Required existing account name |
| `deploymentNameSeed` | Required user-generated GUID used to derive a six-character alphanumeric suffix |
| `modelId` | `azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5` |
| `deploymentTemplateId` | `azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest` |
| `acceleratorType` | `A100_80GB` |
| `capacity` | `1` model instance |
| SKU | `GlobalManagedCompute` (fixed) |
| `versionUpgradeOption` | `OnceNewDefaultVersionAvailable` |

This sample uses Google Gemma 4 31B instruction-tuned as the example OSS model.
Its compatible deployment template runs vLLM with a 16K context length and one
NVIDIA A100 80 GB accelerator per model instance. Capacity is the number of
model instances, not a generic VM count. Therefore, capacity one requires one
`A100_80GB` accelerator in total.

The resulting deployment name is
`gemma-4-31b-it-a100-<suffix>`. Bicep derives the six-character alphanumeric
suffix from `uniqueString(deploymentNameSeed)`. Save and reuse the seed for later
capacity updates and redeployments.

## Prerequisites

- An Azure subscription.
- An existing Microsoft Foundry account with `kind = AIServices` and a Foundry
  project, as required by the [managed-compute deployment guide](https://learn.microsoft.com/azure/foundry/how-to/deploy-models-managed).
- Approved managed-compute quota for at least one `A100_80GB` accelerator in
  the account's region. Managed-compute quota is separate from Azure VM quota.
- **Cognitive Services Contributor**, **Foundry Owner**, or **Foundry Account
  Owner** on the Foundry account for control-plane operations.
- Azure CLI 2.88.0 or later and Bicep CLI 0.47.16 or later. The dedicated
  managed-compute commands used for verification first shipped in Azure CLI
  2.88.0.
- Python 3.9 or PowerShell 7 for the quota and capacity preflight check.
- Microsoft Entra ID authentication through `az login`; no keys are embedded.

Set customer-owned values:

```bash
export RESOURCE_GROUP="your-resource-group"
export FOUNDRY_ACCOUNT_NAME="your-foundry-account"
export ARM_DEPLOYMENT_NAME="gemma-managed-compute"

# Python 3.9+
export DEPLOYMENT_NAME_SEED="$(python3 -c 'import uuid; print(uuid.uuid4())')"

# PowerShell 7 alternative
# export DEPLOYMENT_NAME_SEED="$(pwsh -NoProfile -Command '[guid]::NewGuid().ToString()')"
```

Creation is a long-running operation and commonly takes 10-15 minutes or
longer.

## Check quota and capacity

Before Bicep or ARM JSON what-if/create, run the
[managed-compute preflight helper](../deployment-tools/preflight/managed-compute/README.md).
It reads managed-compute quota in the Foundry account's location and requires
the available quota to cover the additional A100 accelerators. It also queries
current platform capacity for `A100_80GB`, selects the deployment-size row for
one accelerator per model instance, and checks available accelerators, total
model-instance capacity, and the largest contiguous deployment capacity.

From the repository root:

```bash
python3 infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/managed-compute-check.py \
  --account-id "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account" \
  --accelerator-type "A100_80GB" \
  --target-capacity 1 \
  --accelerators-per-instance 1
```

Before changing capacity, rerun the helper with the deployment ID and new target
capacity. It reads current capacity and checks only the additional instances.
The result is advisory; quota and capacity aren't reserved. The linked helper
README includes the equivalent PowerShell 7 commands.

## Deploy the Bicep template

Preview the deployment:

```azurecli
az deployment group what-if \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file main.bicep \
  --parameters \
    foundryAccountName="$FOUNDRY_ACCOUNT_NAME" \
    deploymentNameSeed="$DEPLOYMENT_NAME_SEED"
```

Create it:

```azurecli
az deployment group create \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file main.bicep \
  --parameters \
    foundryAccountName="$FOUNDRY_ACCOUNT_NAME" \
    deploymentNameSeed="$DEPLOYMENT_NAME_SEED"
```

Save the generated resource name for verification, updates, and cleanup:

```bash
export DEPLOYMENT_NAME="$(az deployment group show \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.outputs.deploymentName.value \
  --output tsv)"
```

## Deploy the ARM JSON template

`azuredeploy.json` is generated by:

```bash
az bicep build --file main.bicep --outfile azuredeploy.json
```

Don't edit the generated JSON independently. Preview it:

```azurecli
az deployment group what-if \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file azuredeploy.json \
  --parameters \
    foundryAccountName="$FOUNDRY_ACCOUNT_NAME" \
    deploymentNameSeed="$DEPLOYMENT_NAME_SEED"
```

Create it:

```azurecli
az deployment group create \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file azuredeploy.json \
  --parameters \
    foundryAccountName="$FOUNDRY_ACCOUNT_NAME" \
    deploymentNameSeed="$DEPLOYMENT_NAME_SEED"
```

If you used the ARM JSON workflow directly, save its generated resource name
before verify, scale, or cleanup:

```bash
export DEPLOYMENT_NAME="$(az deployment group show \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.outputs.deploymentName.value \
  --output tsv)"
```

Bicep and ARM JSON are declarative infrastructure as code submitted to the ARM
deployment engine. By contrast, the [REST sample](../../../samples/REST/managed-compute-deployment/)
sends imperative HTTP CRUD requests and implements ARM operation polling.

## Verify and show

Get the deployment through the dedicated CLI command after the ARM deployment
finishes:

```azurecli
az cognitiveservices account managed-compute-deployment show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --deployment-name "$DEPLOYMENT_NAME"
```

Verify that `properties.provisioningState` is `Succeeded` and that the returned
model, deployment template, accelerator, and SKU capacity match the
configuration table. List all managed-compute deployments under the account
with:

```azurecli
az cognitiveservices account managed-compute-deployment list \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FOUNDRY_ACCOUNT_NAME"
```

## Scale

Reapply either template with a different capacity:

```azurecli
az deployment group create \
  --name "$ARM_DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file main.bicep \
  --parameters \
    foundryAccountName="$FOUNDRY_ACCOUNT_NAME" \
    deploymentNameSeed="$DEPLOYMENT_NAME_SEED" \
    capacity=2
```

Capacity changes in place. Each additional model instance for this template adds
one A100 accelerator and requires matching managed-compute quota.

The model, deployment template, and accelerator are immutable after creation.
For any immutable change, use blue/green replacement: deploy a new resource
name, verify it, switch consumers, and delete the old deployment. Changing an
immutable parameter in place causes the service operation to fail.

## Clean up

```azurecli
az cognitiveservices account managed-compute-deployment delete \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --deployment-name "$DEPLOYMENT_NAME"
```

Delete as soon as the sample is no longer needed. Releasing the deployment's
accelerator stops managed-compute billing.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing or insufficient `A100_80GB` quota | Request managed-compute quota for the account region; Azure VM quota doesn't apply. |
| A100 capacity unavailable | Retry later or check current managed-compute regional availability. |
| Authorization failure | Confirm the signed-in identity can deploy the child resource under the existing Foundry account. |
| Provisioning reaches `Failed` | Inspect the ARM deployment operations, resource provisioning details, and Azure activity log. |
| Concurrent-write conflict | Wait for the other account-level deployment operation to finish, then redeploy. |
| ARM deployment timeout | The resource can take 10-15 minutes or longer. Inspect its provisioning state before starting another deployment. |
| Model/template compatibility error | Restore the exact compatible model and deployment-template IDs shown in the configuration table. |

## Static validation

Build and parse the generated template:

```bash
az bicep build --file main.bicep --outfile azuredeploy.json
jq empty azuredeploy.json
```

Rebuilding must leave `azuredeploy.json` unchanged.

## Authoritative references

- [Managed-compute ARM, Bicep, and Terraform AzAPI resource reference](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/accounts/managedcomputedeployments?pivots=deployment-language-bicep)
- [Deploy open-source models with managed compute](https://learn.microsoft.com/azure/foundry/how-to/deploy-models-managed)
- [Managed-compute concepts and limitations](https://learn.microsoft.com/azure/foundry/concepts/managed-compute-overview)
- [Azure CLI managed-compute command group](https://learn.microsoft.com/cli/azure/cognitiveservices/account/managed-compute-deployment?view=azure-cli-latest)
- [Foundry Terraform guidance](https://learn.microsoft.com/azure/foundry/how-to/create-resource-terraform)
- [AzAPI provider overview](https://learn.microsoft.com/azure/developer/terraform/azapi/overview-azapi-provider)
- [Official managed-compute REST example](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/cognitiveservices/resource-manager/Microsoft.CognitiveServices/CognitiveServices/examples/2026-07-15-preview/CreateOrUpdateManagedComputeDeployment.json)
- [Samples contribution guide](https://github.com/microsoft-foundry/foundry-samples/blob/main/CONTRIBUTING.md)
- [Sample creation guide](https://github.com/microsoft-foundry/foundry-samples/blob/main/CREATE_SAMPLE.md)
- [Per-sample validation contract](https://github.com/microsoft-foundry/foundry-samples/blob/main/.github/scripts/validate-sample.README.md)

`Tags: Microsoft.CognitiveServices/accounts/managedComputeDeployments`
