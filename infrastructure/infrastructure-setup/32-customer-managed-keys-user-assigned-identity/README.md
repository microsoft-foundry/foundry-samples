# Azure AI Foundry with Customer-Managed Keys (CMK) and User-Assigned Identity

This repository contains modular Bicep templates for deploying Azure AI Foundry with Customer-Managed Key encryption and User-Assigned Managed Identity.

## Overview

This solution creates a complete Azure AI Foundry environment with:

- **Azure AI Foundry Account** with User-Assigned Managed Identity
- **Customer-Managed Key (CMK)** encryption for enhanced security
- **AI Foundry Project** for organizing your AI workflows
- **Modular architecture** for easy customization and maintenance

## Architecture

```
Azure AI Foundry Solution
├── User-Assigned Managed Identity (UAI)
├── Key Vault with CMK key
├── AI Foundry Account
│   ├── Identity: UserAssigned only
│   ├── CMK encryption enabled
│   └── Project management enabled
└── AI Foundry Project
    └── Identity: UserAssigned (inherited)
```

## Template Structure

This solution uses a modular approach with separate templates:

```
├── main.bicep                        # Main orchestrator template
├── deployment.parameters.json        # Parameters file
├── modules/
│   ├── foundry-account.bicep         # AI Foundry account creation
│   ├── cmk-encryption.bicep          # CMK encryption configuration
│   └── foundry-project.bicep         # Project creation
└── README.md                         # This documentation
```

## Prerequisites

Before deploying this solution, ensure you have:

1. **Azure CLI** installed and configured
2. **Azure subscription** with appropriate permissions
3. **Resource Group** created
4. **Key Vault** with a key for CMK encryption
5. **User-Assigned Managed Identity** with Key Vault permissions

### Setting Up Prerequisites

If you don't have the prerequisites, you can create them:

```powershell
# Create resource group
az group create --name rg-ai-foundry-cmk --location eastus2

# Create user-assigned managed identity
az identity create --name uai-ai-foundry --resource-group rg-ai-foundry-cmk

# Create Key Vault
az keyvault create --name kv-ai-foundry-cmk --resource-group rg-ai-foundry-cmk --location eastus2

# Get your user account for RBAC permissions
$USER_EMAIL = az account show --query user.name -o tsv

# Assign yourself Key Vault Crypto Officer role to create/manage keys
az role assignment create --assignee $USER_EMAIL --role "Key Vault Crypto Officer" --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-ai-foundry-cmk/providers/Microsoft.KeyVault/vaults/kv-ai-foundry-cmk"

# Create key for CMK (wait a moment for RBAC permissions to propagate)
Start-Sleep -Seconds 30
az keyvault key create --vault-name kv-ai-foundry-cmk --name cmk-key --kty RSA --size 2048

# Get UAI details for Key Vault permissions
$UAI_PRINCIPAL_ID = az identity show --name uai-ai-foundry --resource-group rg-ai-foundry-cmk --query principalId -o tsv

# Grant Key Vault Crypto User role to UAI for encryption operations
az role assignment create --assignee $UAI_PRINCIPAL_ID --role "Key Vault Crypto User" --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-ai-foundry-cmk/providers/Microsoft.KeyVault/vaults/kv-ai-foundry-cmk"
```

## Parameters

The solution requires the following parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `aiFoundryName` | Name of the AI Foundry account | `ai-foundry-prod` |
| `location` | Azure region | `eastus2` |
| `keyVaultName` | Name of existing Key Vault | `kv-ai-foundry-cmk` |
| `keyName` | Name of the CMK key | `cmk-key` |
| `keyVersion` | Version of the CMK key | `abc123...` |
| `userAssignedIdentityId` | Resource ID of UAI | `/subscriptions/.../uai-ai-foundry` |
| `userAssignedIdentityClientId` | Client ID of UAI | `12345678-...` |

## Deployment Instructions

### Step 1: Update Parameters

1. Copy the parameters file:
   ```powershell
   Copy-Item deployment.parameters.json my-deployment.parameters.json
   ```

2. Edit `my-deployment.parameters.json` with your specific values:
   ```json
   {
     "parameters": {
       "aiFoundryName": {
         "value": "your-ai-foundry-name"
       },
       "keyVaultName": {
         "value": "your-key-vault-name"
       }
     }
   }
   ```

### Step 2: Get Required Values

Get the Key Vault key version:
```powershell
az keyvault key show --vault-name your-key-vault-name --name your-key-name --query key.kid -o tsv
```

Get UAI details:
```powershell
# Get UAI resource ID
az identity show --name your-uai-name --resource-group your-rg --query id -o tsv

# Get UAI client ID
az identity show --name your-uai-name --resource-group your-rg --query clientId -o tsv
```

### Step 3: Deploy the Solution

```powershell
# Deploy the complete solution
az deployment group create `
  --resource-group your-resource-group `
  --template-file main.bicep `
  --parameters @deployment.parameters.json `
  --verbose
```

The deployment typically takes 20-30 minutes to complete.

### Step 4: Verify Deployment

Check the AI Foundry account:
```powershell
az cognitiveservices account show `
  --name your-ai-foundry-name `
  --resource-group your-resource-group `
  --query "{Name:name, Identity:identity.type, CMK:properties.encryption.keySource}"
```

Check the project:
```powershell
az rest --method GET `
  --uri "https://management.azure.com/subscriptions/{subscription-id}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account-name}/projects?api-version=2025-04-01-preview" `
  --query "value[].{Name:name, Identity:identity.type}"
```

## Module Details

### 1. Foundry Account Module (`foundry-account.bicep`)

Creates the AI Foundry account with:
- User-Assigned Managed Identity (only)
- Project management enabled (`allowProjectManagement: true`)
- Custom subdomain for API access

### 2. CMK Encryption Module (`cmk-encryption.bicep`)

Configures Customer-Managed Key encryption:
- Adds Key Vault access policy for UAI
- Updates account with CMK encryption settings
- Uses UAI client ID for Key Vault authentication

### 3. Project Module (`foundry-project.bicep`)

Creates an AI Foundry project:
- Inherits User-Assigned Identity from parent account
- Configurable display name and description
- Proper dependency management

## Security Features

- **User-Assigned Identity**: Enhanced security control with no system-assigned identities
- **Customer-Managed Keys**: Your keys, your control over encryption
- **Key Vault Integration**: Secure key storage and rotation capabilities
- **RBAC Ready**: Fine-grained access control through Azure RBAC

## Limitations

* Agent service does not support customer-managed key encryption in the basic setup. To use customer-managed key encryption, you must [bring your own storage resources using the standard setup](../31-customer-managed-keys-standard-agent/).
* Post-creation Foundry resources can update from Microsoft-managed key encryption to Customer-managed key encryption. However, updates from customer-managed key encryption to Microsoft-managed key encryption is not supported.
* Only RSA and RSA-HSM keys of size 2048 are supported.

## Troubleshooting

### Common Issues

1. **Deployment Timeout**: Large deployments may take 20-30 minutes
2. **Key Vault Permissions**: Ensure UAI has proper key permissions (get, wrapKey, unwrapKey)
3. **API Versions**: This solution uses `2025-04-01-preview` for latest features
4. **Quota Limits**: Check your subscription quotas for AI services

### Key Vault Requirements

- **Soft Delete must be enabled** (enabled by default on new Key Vaults)
- **Purge Protection must be enabled** (required for CMK)
- If using Key Vault firewall, allow trusted Microsoft services
- **RBAC Permissions Required:**
  - Your user account needs "Key Vault Crypto Officer" role to create keys
  - UAI needs "Key Vault Crypto User" role for encryption operations

### Specific Error Solutions

**Error: "The encryption key must be recoverable and not purgeable"**
```powershell
# Enable purge protection on existing Key Vault
az keyvault update --name your-key-vault-name --enable-purge-protection true
```

**Error: "The role assignment already exists"**
- This indicates the UAI already has the required Key Vault permissions
- The deployment should complete successfully on retry
- Ensure the template doesn't try to create duplicate role assignments

**Error: "KeyVaultProperties is invalid"**
- Verify the Key Vault URI format is correct
- Ensure key name and version are properly specified in parameters
- Check that the Key Vault exists and is accessible

**Error: PowerShell command syntax issues**
```powershell
# Correct syntax for PowerShell (don't use &&)
Set-Location "path\to\template"
az deployment group create --resource-group your-rg --template-file main.bicep --parameters deployment.parameters.json
```

## Additional Resources

- [Azure AI Foundry Documentation](https://docs.microsoft.com/azure/ai-foundry/)
- [Customer-Managed Keys Overview](https://docs.microsoft.com/azure/cognitive-services/encryption/)
- [Managed Identity Documentation](https://docs.microsoft.com/azure/active-directory/managed-identities-azure-resources/)
- [Azure Bicep Documentation](https://docs.microsoft.com/azure/azure-resource-manager/bicep/)
