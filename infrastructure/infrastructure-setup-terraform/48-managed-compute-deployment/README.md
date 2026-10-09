---
description: Deploy an OSS model to Microsoft Foundry managed compute under an existing AIServices account with Terraform and the Azure AzAPI provider.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-ai-foundry
urlFragment: foundry-managed-compute-oss-model-terraform
languages:
- hcl
---

# Deploy OSS models to Microsoft Foundry managed compute using Terraform

This sample uses the Azure AzAPI provider to manage one
`Microsoft.CognitiveServices/accounts/managedComputeDeployments@2026-07-15-preview`
child resource under an existing Microsoft Foundry account. Managed compute
doesn't currently have a dedicated first-class AzureRM resource, so the sample
uses `azapi_resource`, not `azurerm_cognitive_deployment` (which maps to the
different `Microsoft.CognitiveServices/accounts/deployments` resource). Azure
preflight remains enabled; resource-level embedded schema validation is disabled
because the provider schema doesn't yet include this API version.

## Support model and limitations

This sample provides Terraform support through the generic Azure AzAPI provider,
not through a native `azurerm` managed-compute resource. AzAPI sends the
specified ARM resource type, API version, parent ID, and request body to Azure
and adds Terraform planning, state, dependency, update, and destroy behavior.
There is no separate Terraform service endpoint.

The current AzAPI embedded schema doesn't include
`2026-07-15-preview`, so this resource sets
`schema_validation_enabled = false`. This disables only the provider's local
resource-body schema check; Azure Resource Manager and the Cognitive Services
resource provider still validate every request. Provider preflight remains
enabled.

Because `azapi_resource` is generic, it doesn't automatically translate
managed-compute immutability into plan-time replacement behavior. Model,
deployment template, accelerator, and version upgrade policy changes can reach
Azure as updates and fail during apply. Use a new deployment-name prefix for
these changes, verify the replacement, switch consumers, and then destroy the
old deployment. Capacity is updated in place.

Keep Terraform state for the full lifecycle. The generated six-character suffix
is stored in state; losing state can prevent Terraform from finding and updating
or destroying the original deployment. Generic ARM ID import is available, but
there is no managed-compute-specific AzureRM importer, data source, or native
resource schema in this sample.

> [!WARNING]
> Managed compute is billed hourly per accelerator for as long as the deployment
> exists, including periods with no traffic. This sample uses one accelerator.
> Check the [current Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/)
> before deployment. Destroying the deployment releases the accelerator and
> stops its billing.

## Choose a method

All six methods deploy the same resource and defaults.

| Method | Sample |
| --- | --- |
| Azure CLI | [Azure CLI](../../../samples/cli/foundry-models/managed-compute-deployment/) |
| Direct ARM REST API | [REST API](../../../samples/REST/managed-compute-deployment/) |
| Python management SDK | [Python SDK](../../../samples/python/foundry-models/managed-compute-deployment/) |
| Bicep | [Bicep](../../infrastructure-setup-bicep/48-managed-compute-deployment/) |
| ARM JSON template | [Generated ARM JSON](../../infrastructure-setup-bicep/48-managed-compute-deployment/#deploy-the-arm-json-template) |
| Terraform AzAPI | This sample |

## Deployment configuration

| Variable | Default |
| --- | --- |
| `subscription_id` | Required |
| `resource_group_name` | Required |
| `foundry_account_name` | Required existing account name |
| `deployment_name_prefix` | `gemma-4-31b-it-a100` |
| `model_id` | `azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5` |
| `deployment_template_id` | `azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest` |
| `accelerator_type` | `A100_80GB` |
| `capacity` | `1` model instance |
| SKU | `GlobalManagedCompute` (fixed) |
| `version_upgrade_option` | `OnceNewDefaultVersionAvailable` |

The provider derives the existing account's ARM ID from the subscription ID,
resource group, and account name and uses it as `parent_id`.

This sample uses Google Gemma 4 31B instruction-tuned as the example OSS model.
Its compatible deployment template runs vLLM with a 16K context length and one
NVIDIA A100 80 GB accelerator per model instance. Capacity is the number of
model instances, not a generic VM count. Therefore, capacity one requires one
`A100_80GB` accelerator in total.

Terraform appends a persistent random six-character lowercase alphanumeric
suffix to the deployment name prefix. The suffix remains stable for later
capacity updates because it is stored in Terraform state.

## Prerequisites

- Terraform 1.10 or later and earlier than 2.0.
- Azure AzAPI provider `~> 2.5` (installed by `terraform init`).
- Azure CLI for Microsoft Entra ID authentication.
- Python 3.9 or PowerShell 7 for the quota and capacity preflight check.
- An Azure subscription.
- An existing Microsoft Foundry account with `kind = AIServices` and a Foundry
  project, as required by the [managed-compute deployment guide](https://learn.microsoft.com/azure/foundry/how-to/deploy-models-managed).
- Approved managed-compute quota for at least one `A100_80GB` accelerator in
  the account's region. Managed-compute quota is separate from Azure VM quota.
- **Cognitive Services Contributor**, **Foundry Owner**, or **Foundry Account
  Owner** on the Foundry account for control-plane operations.

Authenticate without embedding credentials:

```bash
az login
az account set --subscription "00000000-0000-0000-0000-000000000000"
```

## Configure

```bash
cd code
cp example.tfvars terraform.tfvars
```

Replace the subscription, resource group, and account placeholders in
`terraform.tfvars`. The example model values are shown explicitly but can be
omitted because they are variable defaults. Keep model, deployment template,
and accelerator compatible.

Terraform state can contain sensitive infrastructure data. For team use,
configure a secure remote backend with encryption, access controls, state
locking, and audit logging. Supply backend credentials through your approved
identity or secret system; don't put backend credentials in this repository or
`terraform.tfvars`.

## Check quota and capacity

Before Terraform plan/apply, run the
[managed-compute preflight helper](../../infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/README.md).
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

Before changing capacity, rerun the helper with the deployment ID from
`terraform output deployment_resource_id` and the new target capacity. It reads
current capacity and checks only the additional instances. The result is
advisory; quota and capacity aren't reserved. The linked helper README includes
the equivalent PowerShell 7 commands.

## Initialize, preview, and create

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Creation is a long-running operation and commonly takes 10-15 minutes or
longer. After apply, inspect:

```bash
terraform output
```

The outputs include the deployment resource ID, name, selected accelerator, and
capacity. You can verify the service state with:

```azurecli
az cognitiveservices account managed-compute-deployment show \
  --resource-group "your-resource-group" \
  --name "your-foundry-account" \
  --deployment-name "$(terraform output -raw deployment_name)"
```

Require `properties.provisioningState == Succeeded` and confirm the exact model,
deployment template, accelerator, and capacity before sending traffic. List
account deployments with:

```azurecli
az cognitiveservices account managed-compute-deployment list \
  --resource-group "your-resource-group" \
  --name "your-foundry-account"
```

## Scale

Change only `capacity` in `terraform.tfvars`, then run:

```bash
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Capacity changes in place. Each additional model instance for this template adds
one A100 accelerator and requires matching managed-compute quota.

The model, deployment template, and accelerator are immutable after creation.
Because generic AzAPI resources can't encode every service-side immutability
rule at Terraform plan time, don't apply those changes in place. Use blue/green
replacement: declare a new deployment name, apply and verify it, switch
consumers, and then remove the old deployment.

## Clean up

```bash
terraform plan -destroy -var-file=terraform.tfvars
terraform destroy -var-file=terraform.tfvars
```

Confirm the destroy completes. Releasing the deployment's accelerator stops
managed-compute billing.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing or insufficient `A100_80GB` quota | Request managed-compute quota for the account region; Azure VM quota doesn't apply. |
| A100 capacity unavailable | Retry later or check current managed-compute regional availability. |
| Authorization failure | Confirm the Azure CLI identity can manage the child resource under the existing Foundry account. |
| Provisioning reaches `Failed` | Inspect the AzAPI error, resource provisioning details, and Azure activity log. |
| Concurrent-write conflict | Wait for the other account-level deployment operation to finish, then apply again. |
| Apply timeout or very long operation | Creation often takes 10-15 minutes or longer. Inspect the service state before starting another apply. |
| Model/template compatibility error | Restore the exact compatible model and deployment-template IDs shown in the configuration table. |

## Static validation

These checks don't create Azure resources:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

Don't run `terraform apply` as part of static validation.

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
