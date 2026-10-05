# Managed-compute quota and capacity preflight

`managed-compute-check.py` and `managed-compute-check.ps1` provide equivalent
read-only advisory checks before a Microsoft Foundry managed-compute create or
scale operation. They check both the subscription's managed-compute accelerator
quota and currently reported platform capacity.

The check doesn't reserve quota or capacity. Availability can change after it
runs, so the deployment operation remains authoritative.

Azure requests are retried up to three times only for recognized transient transport,
HTTP 429, and HTTP 5xx failures. Authentication, authorization, matching, and
other request errors fail immediately.

## Prerequisites

- Python 3.9 or PowerShell 7.
- Azure CLI installed and authenticated with `az login`.
- Permission to read the Foundry account, managed-compute usage, capacity, and
  an existing deployment when checking scale.

## Create check

Provide the Foundry account ARM ID, accelerator type, target model instances,
and accelerators required by one model instance:

From the repository root:

### Python

```bash
python3 infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/managed-compute-check.py \
  --account-id "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account" \
  --accelerator-type "A100_80GB" \
  --target-capacity 1 \
  --accelerators-per-instance 1
```

### PowerShell

```powershell
pwsh infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/managed-compute-check.ps1 `
  -AccountId "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account" `
  -AcceleratorType "A100_80GB" `
  -TargetCapacity 1 `
  -AcceleratorsPerInstance 1
```

For the example A100 deployment template, one model instance uses one A100
accelerator.

## Scale check

For scale, supply the existing deployment ID. The helper reads current capacity,
accelerators per instance, SKU, and hosting-region capacity from Azure:

### Python

```bash
python3 infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/managed-compute-check.py \
  --account-id "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account" \
  --accelerator-type "A100_80GB" \
  --target-capacity 2 \
  --deployment-id "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account/managedComputeDeployments/your-deployment" \
  --output-format json
```

### PowerShell

```powershell
pwsh infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/managed-compute-check.ps1 `
  -AccountId "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account" `
  -AcceleratorType "A100_80GB" `
  -TargetCapacity 2 `
  -DeploymentId "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/your-resource-group/providers/Microsoft.CognitiveServices/accounts/your-foundry-account/managedComputeDeployments/your-deployment" `
  -OutputFormat json
```

Scale checks require only the additional capacity:

```text
additional instances = max(0, target capacity - current capacity)
additional accelerators = additional instances × accelerators per instance
```

Each helper first requests capacity for the deployment's hosting region. Some
existing deployments can return HTTP 404 for that optional capacity lookup. In
that case, the helper visibly marks `capacityLookup` as
`bestAvailableFallback`, emits a warning, and uses the broader offer/scope
snapshot. Use `--require-deployment-region-capacity` in Python or
`-RequireDeploymentRegionCapacity` in PowerShell to fail instead of falling
back.

## What the helper checks

### Quota

The helper discovers the Foundry account's location, reads
`managedComputeUsages`, and selects exactly one quota record by:

- offer scope, such as `Global`;
- unit `AcceleratorCount`; and
- quota metric name ending in the requested accelerator type, such as
  `.A100_80GB`.

It requires:

```text
limit - currentValue >= additional accelerators required
```

Managed-compute quota is separate from Azure VM quota.

### Platform capacity

The helper calls `managedComputeCapacities` with the requested accelerator type.
For scale, it also sends the deployment ID so Azure reports capacity for the
deployment's hosting region.

It selects the capacity object by accelerator and offer scope, then selects the
`deploymentSizeCapacities` row whose `modelInstanceAcceleratorCount` exactly
matches the template's accelerators per model instance. It requires:

```text
availableAccelerators >= additional accelerators required
totalAvailableCapacity >= additional model instances required
largestDeploymentCapacity >= additional model instances required
```

The helper fails instead of guessing when quota, capacity, scope, or
deployment-size matching returns zero or multiple records. It doesn't infer
accelerators per instance from a deployment-template name.

For Data Zone checks, capacity uses `OfferScope=DataZone` with a `ScopeId`, while
quota can use a combined value such as `Datazone-US`. The command derives that
quota scope when possible or accepts `--quota-offer-scope` in Python or
`-QuotaOfferScope` in PowerShell explicitly.

## Output and exit codes

Python uses `--output-format`; PowerShell uses `-OutputFormat`. Both accept
`table` for interactive output or `json` for automation and use the same exit
codes.

| Exit code | Meaning |
| --- | --- |
| `0` | Reported quota and platform capacity are sufficient. |
| `1` | The request exceeds reported quota or platform capacity. |
| `2` | Inputs, authentication, authorization, account state, or API response matching failed. |

## Test the matching logic

The offline tests cover create and scale calculations, single- and
multi-accelerator templates, insufficient quota, insufficient capacity,
scale-down, missing deployment-size rows, and ambiguous capacity records:

```powershell
pwsh infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/tests/test-managed-compute-preflight.ps1
```

```bash
python3 infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/managed-compute/tests/test_managed_compute_preflight.py
```
