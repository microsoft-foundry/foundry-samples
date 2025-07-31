---
description: This template deploys an Azure AI Foundry account, project, and model deployment while using your key for encryption (Customer Managed Key).
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: aifoundry-cmk
languages:
- bicep
- json
---
# Set up Azure AI Foundry using Customer Managed Keys for encryption

This Azure AI Foundry template demonstrates how to deploy AI Foundry with Agents standard setup and customer-managed keys for encryption.

## Prerequisites

* An existing Azure Key Vault resource. This sample template does not create it.
* You must enable both the Soft Delete and Do Not Purge properties on the existing Azure Key Vault instance.
* If you use the Key Vault firewall, you must allow trusted Microsoft services to access the Azure Key Vault.
* You must grant your Azure AI Foundry resource and project system-assigned managed identity the following permissions on your key vault: get key, wrap key, unwrap key.
* Only RSA and RSA-HSM keys of size 2048 are supported. For more information about keys, see Key Vault keys in 

## Run the Bicep deployment commands

Steps:
1. Run the command above once to create the account and project without CMK.
   ```bash
   az deployment group create --name "{DEPLOYMENT_NAME}" --resource-group "{RESOURCE_GROUP_NAME}" --template-file ./main.bicep --parameters azureKeyVaultName="{KEY_VAULT_NAME}" azureKeyName="{KEY_NAME}" azureKeyVersion="{KEY_VERSION}"
   ```
1. Give account resource Key Vault Admin role, or more restricted get/wrap/unwrap key role assignments, on the Azure Key Vault. 
1. Uncomment out the encryption section in the main.bicep file to update with CMK.

## Learn more
If you are new to Azure AI Foundry, see:

- [Azure AI Foundry](https://learn.microsoft.com/azure/ai-foundry/)

If you are new to template deployment, see:

- [Azure Resource Manager documentation](https://learn.microsoft.com/azure/azure-resource-manager/)
- [Azure AI services quickstart article](https://learn.microsoft.com/azure/cognitive-services/resource-manager-template)

`Tags: Microsoft.CognitiveServices/accounts/projects`
