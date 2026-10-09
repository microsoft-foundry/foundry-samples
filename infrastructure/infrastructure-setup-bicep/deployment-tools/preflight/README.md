# Preflight Check for Foundry Private Network Deployments

`preflight-check.ps1` validates your Azure environment **before** running `az deployment group create`. It catches common misconfigurations that would otherwise surface as cryptic ARM errors mid-deploy — saving you from failed deployments, wasted time, and difficult-to-diagnose issues.

For Microsoft Foundry managed-compute deployments, use the separate
[managed-compute quota and capacity preflight](./managed-compute/README.md).
It provides equivalent Python 3.9+ and PowerShell 7 commands that check
managed-compute accelerator quota and current platform capacity before create or
scale operations.

## Why Run Preflight Checks?

ARM template deployments can fail 10–20 minutes in with opaque error messages. By that point resources may be partially created, leaving your environment in an inconsistent state that requires manual cleanup. This script validates everything upfront so you can fix issues before they become problems.

## What It Checks

### 0. Azure CLI Login & Subscription

| Check | What It Prevents |
|---|---|
| Azure CLI is logged in | Script failures when `az` commands can't authenticate |
| Subscription is accessible | Deployment against a subscription you don't have access to |
| Active subscription matches the requested one | Running checks (and later deploying) against the wrong subscription |
| Location is a valid Azure region | Deployments targeting a misspelled or non-existent region (accepts both display names like "Sweden Central" and API names like "swedencentral") |

### 1. Resource Provider Registration

| Check | What It Prevents |
|---|---|
| Required providers are registered: `Microsoft.CognitiveServices`, `Microsoft.Storage`, `Microsoft.Search`, `Microsoft.DocumentDB`, `Microsoft.Network`, `Microsoft.App`, `Microsoft.KeyVault`, `Microsoft.MachineLearningServices`, `Microsoft.ContainerService` | Deployment failures with "resource provider not registered" errors, which require registration and a retry |
| Optional providers are checked: `Microsoft.Bing` (Bing Search tool), `Microsoft.ApiManagement` (APIM setups), `Microsoft.Web` (Azure Functions agent tools), `Microsoft.ManagedIdentity` (user-assigned identity setups), `Microsoft.ContainerRegistry` (most templates enable ACR) | Warns if an optional provider needed for your scenario is not registered |

### 2. Resource Group State

| Check | What It Prevents |
|---|---|
| Resource group exists and its location matches the deployment location | Cross-region failures where private endpoints reference `resourceGroup().location` but the RG is in a different region than intended |
| Existing AI accounts in the resource group | Accidental creation of duplicate resources with timestamp-based naming when re-deploying, instead of reusing existing ones |
| Soft-deleted Cognitive Services accounts | Name collision failures when a new deployment tries to create an account with the same name as a soft-deleted one |

### 3. BYO (Bring-Your-Own) Resource Validation

When you pass existing resource IDs, the script validates them before the template tries to reference them.

| Check | What It Prevents |
|---|---|
| ARM resource ID format is valid (correct segments, valid subscription GUID) | Template failures caused by malformed resource IDs |
| AI Search resource exists and is accessible | References to non-existent or inaccessible Search services |
| AI Search SKU is not `free` | Private endpoint creation failures — free tier doesn't support private endpoints |
| AI Search has AAD authentication enabled (`disableLocalAuth` or `aadOrApiKey`) | Bicep deployment failures when AAD auth is not configured — provides fix commands |
| Storage Account exists and is accessible | References to non-existent or inaccessible storage accounts |
| Storage Account kind is `StorageV2` | Feature incompatibilities (e.g., file shares) with non-StorageV2 account kinds |
| Cosmos DB exists and is accessible | References to non-existent or inaccessible Cosmos DB accounts |
| Cosmos DB `disableLocalAuth` is enabled | Silent failures in Foundry role assignments when key-based auth is still active |
| API Management instance exists (when `ApiManagementResourceId` provided) | References to non-existent or inaccessible APIM instances in private network setups |
| Fabric Workspace exists (when `FabricWorkspaceResourceId` provided) | References to non-existent or inaccessible Fabric workspaces in agent tools / MCP setups |

### 4. VNet and Subnet Validation

When using an existing VNet (`-ExistingVnetId`), the script performs deep network checks.

| Check | What It Prevents |
|---|---|
| VNet exists and its location matches the deployment location | Private endpoint failures when VNet and deployment are in different regions |
| Expected subnets exist (`agent-subnet`, `pe-subnet`, `mcp-subnet`) with per-subnet guidance on which scenarios need which subnet | Unclear errors when the template expects subnets that don't exist yet |
| No Service Association Links (SALs) on subnets | Deployment will fail — the platform cannot inject into a subnet already owned by another resource (SAL holder type is reported, e.g. `Microsoft.App/environments` on agent/mcp subnets) |
| Agent and MCP subnets are delegated to `Microsoft.App/environments` | Container App environment provisioning failures due to missing or incorrect delegation |
| PE subnet has enough usable IPs (4 base PEs for AI Services, Search, Storage, Cosmos DB — plus 1 each for APIM and/or Fabric when configured) | Private endpoint creation failures when the subnet is too small (recommends /24, minimum /28) |

### 5. DNS Zone Conflict Detection

| Check | What It Prevents |
|---|---|
| Checks for existing private DNS zones in the resource group: `privatelink.services.ai.azure.com`, `privatelink.openai.azure.com`, `privatelink.cognitiveservices.azure.com`, `privatelink.search.windows.net`, `privatelink.blob.core.windows.net`, `privatelink.documents.azure.com`, `privatelink.azurecr.io` (ACR), `privatelink.azure-api.net` (APIM), `privatelink.fabric.microsoft.com` (Fabric) | VNet link creation failures when the template tries to create a DNS zone that already exists and is already linked |

### 6. Model and Cosmos DB Quota Checks

Model checks only run when `ModelName`, `ModelFormat`, `ModelSkuName`, and `ModelCapacity` are all provided. Cosmos DB throughput check only runs when `CosmosDBResourceId` is provided.

| Check | What It Prevents |
|---|---|
| Model is available in the target region (name + format) | Deployment failures when the requested model isn't available in the selected region |
| Sufficient TPM (tokens per minute) quota for the requested model SKU and capacity | Model deployment failures due to insufficient quota — directs you to the quota increase page |
| Cosmos DB account throughput cap is at least 3000 RU/s (3 containers × 1000 RU/s per project), or no cap is set | Agent service failures when a hard throughput cap on the account would block the required per-container provisioning |

### 7. Resource Quota Checks

| Check | What It Prevents |
|---|---|
| AI Search Standard tier quota in the target region | Search service creation failures due to exhausted quota |
| Storage account count in the region (limit: 250) | Storage account creation failures when approaching or exceeding the per-region limit |
| VNet and Private Endpoint quotas in the target region | Network resource creation failures when quotas are exhausted or near capacity (warns at 80%) |

## Usage

```powershell
cd infrastructure/infrastructure-setup-bicep/deployment-tools/preflight
```

### Option 1: Config File

Copy the sample config, fill in your values, and run:

```powershell
cp preflight.config.sample preflight.config
# Edit preflight.config with your values
.\preflight-check.ps1 -ConfigFile .\preflight.config
```

### Option 2: Command-Line Parameters

```powershell
# Minimal (new VNet, new resources)
.\preflight-check.ps1 -SubscriptionId "your-sub-id" -ResourceGroup "my-rg" -Location "swedencentral"

# With BYO VNet and AI Search
.\preflight-check.ps1 -SubscriptionId "your-sub-id" -ResourceGroup "my-rg" -Location "swedencentral" `
    -ExistingVnetId "/subscriptions/.../virtualNetworks/my-vnet" `
    -AiSearchResourceId "/subscriptions/.../searchServices/my-search"
```

Command-line parameters override config file values.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `ConfigFile` | No | Path to a key=value config file (see `preflight.config.sample`) |
| `SubscriptionId` | Yes* | Azure subscription ID |
| `ResourceGroup` | Yes* | Target resource group |
| `Location` | Yes* | Deployment region (e.g., `swedencentral`) |
| `ExistingVnetId` | No | Full ARM resource ID of an existing VNet |
| `AiSearchResourceId` | No | Full ARM resource ID of an existing AI Search resource |
| `StorageAccountResourceId` | No | Full ARM resource ID of an existing Storage Account |
| `CosmosDBResourceId` | No | Full ARM resource ID of an existing Cosmos DB account |
| `ApiManagementResourceId` | No | Full ARM resource ID of an existing API Management instance (for APIM private network setup) |
| `FabricWorkspaceResourceId` | No | Full ARM resource ID of an existing Fabric Workspace (for agent tools / MCP setup) |
| `ModelName` | No | Model name for quota checks (e.g., `gpt-4o`) |
| `ModelFormat` | No | Model format — must match `az cognitiveservices model list` output (e.g., `OpenAI`, `Mistral AI`) |
| `ModelSkuName` | No | Model SKU name (e.g., `Standard`, `GlobalStandard`) |
| `ModelCapacity` | No | Requested TPM capacity in thousands (e.g., `10` = 10K TPM) |

\* Can be provided via config file instead.

## Output

The script produces color-coded output:

- **[PASS]** (green) — Check passed
- **[FAIL]** (red) — Must fix before deploying
- **[WARN]** (yellow) — Potential issue, review recommended
- **[INFO]** (cyan) — Informational

A summary at the end shows total pass/fail/warn counts. The script sets exit code `1` if any checks fail, `0` if all pass.

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and logged in (`az login`)
- Active subscription set to the target subscription:
  ```powershell
  az account set --subscription <subscription-id>
  ```
- Sufficient permissions to read resources in the target subscription
