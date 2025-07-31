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
# Set up Azure AI Foundry with Customer Managed Keys for Encryption

This Azure AI Foundry template example demonstrates how to configure customer-managed key encryption on an AI Foundry resource.

Configuring customer managed keys is performed using a two-step approach, in which first the resource is created without encryption to allow the managed identity to be created. In a second step, the managed identity is assigned access to your key vault and encryption is applied on your resource.

## Prerequisites

* An existing Azure Key Vault resource. This sample template does not create it.
* You must enable both the Soft Delete and Do Not Purge properties on the existing Azure Key Vault instance.
* If you use the Key Vault firewall, you must allow trusted Microsoft services to access the Azure Key Vault.
* You must grant your Azure AI Foundry resource and project system-assigned managed identity the following permissions on your key vault: get key, wrap key, unwrap key.
* Only RSA and RSA-HSM keys of size 2048 are supported. For more information about keys, see Key Vault keys in 

## Limitations

* Agent service does not support customer-managed key encryption in the basic setup. To use customer-managed key encryption, you must [bring your own storage resources using the standard setup](../31-customer-managed-keys-standard-agent/).
* Post-creation Foundry resources can update from Microsoft-managed key encryption to Customer-managed key encryption. However, updates from customer-managed key encryption to Microsoft-managed key encryption is not supported.

## Instructions

Run the command for BICEP:

```bash
az deployment group create \
--name "{DEPLOYMENT_NAME}" \
--resource-group "{RESOURCE_GROUP_NAME}" \
--template-file ./main.bicep \
--parameters aiFoundryName="{FOUNDRY_NAME} \
keyVaultName="{KEY_VAULT_NAME}" \
keyName="{KEY_NAME}" \
keyVersion="{KEY_VERSION}"
```
