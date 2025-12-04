# Bring Your Own Azure Storage for Speech and Language capabilities (Preview)

Use this template to associate your Azure Storage account to a new Foundry resource. This template allows you to bring an existing Azure Storage account as the storage for your Speech and Language usecases. Learn more about this feature's restrictions via our public documentation. 

## Advanced implementation details  
### How is this setup different from an Azure Storage connection in Foundry?
This template does not use the Foundry connections API. The [Foundry resource connections API](https://learn.microsoft.com/en-us/rest/api/aifoundry/accountmanagement/account-connections?view=rest-aifoundry-accountmanagement-2025-06-01) and [Foundry project connections API](https://learn.microsoft.com/en-us/rest/api/aifoundry/aiprojects/connections?view=rest-aifoundry-aiprojects-v1) use the Foundry endpoint to store authentication details like API keys and target. The Azure Storage association to a Foundry resource does not use that API. Instead, there is a field under `properties` in the Foundry resource creation step, that sets the Azure Storage resource ID. This field allows for backwards compatibility with how previous Speech Services and Language kinds do.  

### What authentication methods are supported?
This association does not support API key authentication, only RBAC authentication.

