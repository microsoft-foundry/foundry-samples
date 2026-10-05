---
description: Create, inspect, list, scale, and delete an OSS model deployment on Microsoft Foundry managed compute through the ARM REST API.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-ai-foundry
urlFragment: foundry-managed-compute-oss-model-rest
languages:
- bash
---

# Deploy OSS models to Microsoft Foundry managed compute using ARM REST

This sample uses Bash, `curl`, and `jq` to manage one
`Microsoft.CognitiveServices/accounts/managedComputeDeployments@2026-07-15-preview`
child resource under an existing Microsoft Foundry account. It calls the Azure
Resource Manager management/control plane, not a model inference/data-plane
endpoint.

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
| Azure CLI | [Azure CLI](../../cli/foundry-models/managed-compute-deployment/) |
| Direct ARM REST API | This sample |
| Python management SDK | [Python SDK](../../python/foundry-models/managed-compute-deployment/) |
| Bicep | [Bicep](../../../infrastructure/infrastructure-setup-bicep/48-managed-compute-deployment/) |
| ARM JSON template | [Generated ARM JSON](../../../infrastructure/infrastructure-setup-bicep/48-managed-compute-deployment/#deploy-the-arm-json-template) |
| Terraform AzAPI | [Terraform](../../../infrastructure/infrastructure-setup-terraform/48-managed-compute-deployment/) |

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
- Bash 3.2 or later, `curl` 7.29 or later with HTTPS support, and `jq` 1.6 or
  later.
- Azure CLI 2.30 or later only when the script acquires a token for you.
- Python 3.9 or PowerShell 7 for the quota and capacity preflight check.

Use Microsoft Entra ID authentication. Either run `az login` and let the script
call:

```azurecli
az account get-access-token \
  --resource https://management.azure.com \
  --query accessToken \
  --output tsv
```

or provide a caller-acquired management-plane token through the
`AZURE_ACCESS_TOKEN` environment variable. The script acquires a fresh Azure CLI
token for every request, including long-running-operation polls, and never
prints or persists a token. Don't pass tokens as command-line arguments.

## Check quota and capacity

Before create or scale, run the
[managed-compute preflight helper](../../../infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/README.md).
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
`ACCELERATOR_TYPE`, `CAPACITY`, and `VERSION_UPGRADE_OPTION`. Polling defaults
are `POLL_INTERVAL_SECONDS=30` and `LRO_TIMEOUT_SECONDS=3600`. Command-line
options shown by `./manage-managed-compute.sh --help` override nonsecret values.

The resource URL is:

```text
https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.CognitiveServices/accounts/{accountName}/managedComputeDeployments/{deploymentName}?api-version=2026-07-15-preview
```

List removes the final `/{deploymentName}` segment.

## Render the create body without Azure

```bash
./manage-managed-compute.sh render-create | jq .
```

`render-create` makes no network request. The script builds JSON with `jq -n`,
`--arg`, and `--argjson`, so customer-supplied values aren't interpolated into a
JSON heredoc.

## Create and verify

```bash
./manage-managed-compute.sh create
```

Create sends HTTP `PUT` with this shape:

```json
{
  "sku": {
    "name": "GlobalManagedCompute",
    "capacity": 1
  },
  "properties": {
    "model": "azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5",
    "deploymentTemplate": "azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest",
    "acceleratorType": "A100_80GB",
    "versionUpgradeOption": "OnceNewDefaultVersionAvailable"
  }
}
```

Creation is a long-running operation and commonly takes 10-15 minutes or
longer. The script accepts successful initial `200`, `201`, and `202` responses.
It parses response headers case-insensitively, follows `Azure-AsyncOperation` or
`Location`, honors numeric `Retry-After`, and otherwise uses the bounded default
poll interval. The overall timeout defaults to one hour.

Polling continues through nonterminal states such as `Accepted`, `Running`, and
`InProgress`. `Failed`, `Canceled`, and `Cancelled` are errors. After the ARM
operation completes, the script gets the resource, requires
`properties.provisioningState == Succeeded`, and verifies the exact model,
deployment template, accelerator, upgrade policy, SKU, and capacity.

HTTP status, headers, and body are captured separately. Non-success status codes
print the structured ARM error body when one is available; bearer tokens aren't
included.

## Show and list

```bash
./manage-managed-compute.sh show
./manage-managed-compute.sh list
```

## Scale

```bash
./manage-managed-compute.sh scale --capacity 2
```

Scale sends HTTP `PATCH` with only:

```json
{
  "sku": {
    "name": "GlobalManagedCompute",
    "capacity": 2
  }
}
```

It accepts `200` or `202`, polls any ARM operation, and performs the same final
verification as create. Each additional model instance for this template adds
one A100 accelerator and requires matching managed-compute quota.

The model, deployment template, and accelerator are immutable after creation.
For any immutable change, use blue/green replacement: create a new deployment
name, verify it, switch consumers, and delete the old deployment.

## Clean up

```bash
./manage-managed-compute.sh delete
```

Delete accepts `200`, `202`, or `204`, polls a returned operation URL, then gets
the deployment until ARM returns `404`. Delete as soon as the sample is no
longer needed; releasing the accelerator stops managed-compute billing.

## REST versus the ARM JSON template

This REST sample is imperative: it sends individual HTTP CRUD requests to one
resource URL and implements ARM long-running-operation polling. The
[ARM JSON method](../../../infrastructure/infrastructure-setup-bicep/48-managed-compute-deployment/#deploy-the-arm-json-template)
is declarative: it submits a generated template to the ARM deployment engine,
which evaluates the desired resource state.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing or insufficient `A100_80GB` quota | Request managed-compute quota for the account region; Azure VM quota doesn't apply. |
| A100 capacity unavailable | Retry later or check current managed-compute regional availability. |
| HTTP 401 or 403 | Acquire a token for `https://management.azure.com` and confirm the identity has a control-plane role on the Foundry account. |
| Provisioning reaches `Failed` | Inspect the structured ARM error, provisioning details, and Azure activity log. |
| HTTP 409 concurrent-write conflict | Wait for the other account-level deployment operation to finish, then retry. |
| Polling timeout | Check the operation URL or resource provisioning state, then increase `--timeout` if Azure is still making progress. Don't start a duplicate write. |
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
