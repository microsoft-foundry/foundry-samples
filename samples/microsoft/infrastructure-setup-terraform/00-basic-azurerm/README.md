---
description: This set of templates demonstrates how to set up Azure AI Foundry in the basic configuration with public network setup and Microsoft-managed storage resources using AzureRM provider.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: foundry-basic
languages:
- hcl
---

# Azure AI Foundry: Basic setup with public networking (AzureRM)
 
## Key Information
  
This infrastructure-as-code (IaC) solution deploys Azure AI Foundry with public networking and uses Microsoft-managed storage for file upload experience. It supports getting started scenarios, for typically non-enterprise scenarios. This variant shows AzureRM Terraform provider.

## Prerequisites

1. **Active Azure subscription(s) with appropriate permissions**
  It's recommended to deploy these templates through a deployment pipeline associated to a service principal or managed identity with sufficient permissions over the the workload subscription (such as Owner or Role Based Access Control Administrator and Contributor). If deployed manually, the permissions below should be sufficient.

  - **Workload Subscription**
    - **Role Based Access Control Administrator**: Needed over the resource group to create the relevant role assignments
    - **Network Contributor**: Needed over the resource group to create virtual network and Private Endpoint resources
    - **Azure AI Account Owner**: Needed to create a cognitive services account and project 
    - **Owner or Role Based Access Administrator**: Needed to assign RBAC to the required resources (Cosmos DB, Azure AI Search, Storage) 
    - **Azure AI User**: Needed to create and edit agents

2. **Register Resource Providers**

   ```bash
   az provider register --namespace 'Microsoft.CognitiveServices'
   ```

3. Sufficient quota for all resources in your target Azure region

4. Azure CLI installed and configured on your local workstation or deployment pipeline server

5. Terraform CLI version v1.11.4 or later on your local workstation or depoyment pipeline server. This template requires the usage of both the AzureRm and AzApi Terraform providers.

### Variables

The variables listed below [must be provided](https://developer.hashicorp.com/terraform/language/values/variables#variable-definition-precedence) when performing deploying the templates. The file example.tfvars provides a sample Terraform variables file that can be used.

- **location** - The Azure region the resources will be deployed to. This must be the same region where the pre-existing virtual network has been deployed to.

The variables listed below are optional and if not specified will use the defaults as included in the variables.tf file.

## Deploy the Terraform template

1. Fill in the required information for the variables listed in the example.tfvars file and rename the file to terraform.tfvars.

2. If performing the deployment interactively, log in to Az CLI with a user that has sufficient permissions to deploy the resources.

```bash
az login
```

3. Ensure the proper environmental variables are set for [AzApi](https://registry.terraform.io/providers/Azure/azapi/latest/docs) and [AzureRm](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs) providers. At a minimum, you must set the ARM_SUBSCRIPTION_ID environment variable to the subscription the resoruces will be deployed to. You can do this with the commands below:

Linux/MacOS
```bash
export ARM_SUBSCRIPTION_ID="YOUR_SUBSCRIPTION_ID"
terraform apply
```

Windows
```cmd
set ARM_SUBSCRIPTION_ID="YOUR_SUBSCRIPTION_ID"
terraform apply
```

4. Initialize Terraform

```bash
terraform init
```

5. Deploy the resources
```bash
terraform apply
```

## Module Structure

```text
code/
├── data.tf                                         # Creates data objects for active subscription being deployed to and deployment security context
├── locals.tf                                       # Creates local variables for project GUID
├── main.tf                                         # Main deployment file        
├── outputs.tf                                      # Placeholder file for future outputs
├── providers.tf                                    # Terraform provider configuration 
├── example.tfvars                                  # Sample tfvars file
├── variables.tf                                    # Terraform variables
├── versions.tf                                     # Configures minimum Terraform version and versions for providers
```


## References

- [Learn more about Azure AI Foundry architecture](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/architecture)
- [Azure AI Foundry reference docs for Terraform](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/create-resource-terraform)