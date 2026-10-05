---
description: Create, inspect, list, scale, and delete an OSS model deployment on Microsoft Foundry managed compute with Azure CLI.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-ai-foundry
urlFragment: foundry-managed-compute-oss-model-cli
languages:
- azurecli
- bash
---

# Deploy OSS models to Microsoft Foundry managed compute using Azure CLI

This sample manages one
`Microsoft.CognitiveServices/accounts/managedComputeDeployments` child resource
under an existing Microsoft Foundry account.

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
| Azure CLI | This sample |
| Direct ARM REST API | [REST API](../../../REST/managed-compute-deployment/) |
| Python management SDK | [Python SDK](../../../python/foundry-models/managed-compute-deployment/) |
| Bicep | [Bicep](../../../../infrastructure/infrastructure-setup-bicep/48-managed-compute-deployment/) |
| ARM JSON template | [Generated ARM JSON](../../../../infrastructure/infrastructure-setup-bicep/48-managed-compute-deployment/#deploy-the-arm-json-template) |
| Terraform AzAPI | [Terraform](../../../../infrastructure/infrastructure-setup-terraform/48-managed-compute-deployment/) |

## Deployment configuration

| Setting | Default |
| --- | --- |
| Deployment name | `gemma-4-31b-it-a100-<suffix>` |
| Model | `azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5` |
| Deployment template | `azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest` |
| Accelerator type | `A100_80GB` |
| Model instances / SKU capacity | `1` |
| SKU | `GlobalManagedCompute` |
| Upgrade policy | `OnceNewDefaultVersionAvailable` |

This sample uses Google Gemma 4 31B instruction-tuned as the example OSS model.
Its compatible deployment template runs vLLM with a 16K context length and one
NVIDIA A100 80 GB accelerator per model instance. Capacity is the number of
model instances, not a generic VM count. Therefore, capacity one requires one
`A100_80GB` accelerator in total.

When `create` runs without a deployment name, the script appends a random
six-character alphanumeric suffix. Reuse the returned name for show, scale, and
delete.

## Prerequisites

- An Azure subscription.
- An existing Microsoft Foundry account with `kind = AIServices` and a Foundry
  project, as required by the [managed-compute deployment guide](https://learn.microsoft.com/azure/foundry/how-to/deploy-models-managed).
- Approved managed-compute quota for at least one `A100_80GB` accelerator in
  the account's region. Managed-compute quota is separate from Azure VM quota.
- **Cognitive Services Contributor**, **Foundry Owner**, or **Foundry Account
  Owner** on the Foundry account for control-plane operations.
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.88.0 or
  later.
- Bash 3.2 or later and `jq` 1.6 or later.
- Python 3.9 or PowerShell 7 for the quota and capacity preflight check.

Authenticate with Microsoft Entra ID before running the script:

```bash
az login
az account set --subscription "00000000-0000-0000-0000-000000000000"
```

The script never invokes `az login` and contains no keys or tokens.

## Check quota and capacity

Before create or scale, run the
[managed-compute preflight helper](../../../../infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/README.md).
It reads managed-compute quota in the Foundry account's location and requires
the available quota to cover the additional A100 accelerators. It also queries
current platform capacity for `A100_80GB`, selects the deployment-size row for
one accelerator per model instance, and checks available accelerators, total
model-instance capacity, and the largest contiguous deployment capacity.

For create at capacity one:

From the repository root:

```bash
python3 infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/managed-compute-check.py \
  --account-id "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account" \
  --accelerator-type "A100_80GB" \
  --target-capacity 1 \
  --accelerators-per-instance 1
```

For scale, pass the deployment ID and target capacity. The helper reads current
capacity and checks only the additional instances. The result is advisory;
quota and capacity aren't reserved. The linked helper README includes the
equivalent PowerShell 7 commands.

## Configure

```bash
export AZURE_SUBSCRIPTION_ID="00000000-0000-0000-0000-000000000000"
export RESOURCE_GROUP="your-resource-group"
export FOUNDRY_ACCOUNT_NAME="your-foundry-account"
export DEPLOYMENT_NAME="gemma-4-31b-it-a100-$(od -An -N3 -tx1 /dev/urandom | tr -d '[:space:]')"
```

Optional environment variables correspond to the defaults in the configuration
table: `DEPLOYMENT_NAME`, `MODEL_ID`, `DEPLOYMENT_TEMPLATE_ID`,
`ACCELERATOR_TYPE`, `CAPACITY`, and `VERSION_UPGRADE_OPTION`. Command-line
options shown by `./manage-managed-compute.sh --help` override them.

## Create and verify

```bash
./manage-managed-compute.sh create
```

The script uses the dedicated command group, not `az rest`. Its create
request is equivalent to:

```azurecli
az cognitiveservices account managed-compute-deployment create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --deployment-name "$DEPLOYMENT_NAME" \
  --model "azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5" \
  --deployment-template "azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest" \
  --accelerator-type "A100_80GB" \
  --sku-name "GlobalManagedCompute" \
  --sku-capacity 1 \
  --version-upgrade-option "OnceNewDefaultVersionAvailable"
```

Creation is a long-running operation and commonly takes 10-15 minutes or
longer. After the CLI operation returns, the script calls `show`, requires
`properties.provisioningState == Succeeded`, and verifies the model, deployment
template, accelerator, upgrade policy, SKU, and capacity.

## Show and list

```bash
./manage-managed-compute.sh show
./manage-managed-compute.sh list
```

## Scale

```bash
./manage-managed-compute.sh scale --capacity 2
```

Scale sends the fixed `GlobalManagedCompute` SKU name with the new capacity, then
performs the same final verification as create. Capacity is the only value that
changes. Each additional model instance for this template adds one A100
accelerator and requires matching managed-compute quota.

The model, deployment template, and accelerator are immutable after creation.
For any immutable change, use blue/green replacement: create a new deployment
name, verify it, switch consumers, and delete the old deployment.

## Clean up

```bash
./manage-managed-compute.sh delete
```

Delete as soon as the sample is no longer needed. Releasing the deployment's
accelerator stops managed-compute billing.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing or insufficient `A100_80GB` quota | Request managed-compute quota for the account region; Azure VM quota doesn't apply. |
| A100 capacity unavailable | Retry later or check current managed-compute regional availability. |
| Authorization failure | Confirm the signed-in identity has a control-plane role on the Foundry account and the intended subscription is selected. |
| Provisioning reaches `Failed` | Inspect the returned provisioning details and Azure activity log; retain the deployment name when opening support requests. |
| Concurrent-write conflict | Wait for the other account-level deployment operation to finish, then retry. |
| Operation takes longer than expected | Creation often takes 10-15 minutes or longer. Re-run `show` and inspect the provisioning state rather than starting a second write. |
| Model/template compatibility error | Restore the exact compatible model and deployment-template IDs shown in the configuration table. |

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
