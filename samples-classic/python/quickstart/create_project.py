# source: https://github.com/Azure/agent-first-sdk/blob/main/tests/management_sdk/manage_ai_foundry.ipynb

# <create_client>
from azure.identity import DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient

subscription_id = 'your-subscription-id'
resource_group_name = 'your-resource-group-name'
foundry_resource_name = 'your-foundry-resource-name'
foundry_project_name = 'your-foundry-project-name'
location = 'eastus'

client = CognitiveServicesManagementClient(
    credential=DefaultAzureCredential(), 
    subscription_id=subscription_id,
    api_version="2025-04-01-preview"
)
# </create_client>
# TODO: add code to create create a new resource group

# <create_resource_project>
# Create resource
resource = client.accounts.begin_create(
    resource_group_name=resource_group_name,
    account_name=foundry_resource_name,
    account={
        "location": location,
        "kind": "AIServices",
        "sku": {"name": "S0",},
        "identity": {"type": "SystemAssigned"},
        "properties": {
            "allowProjectManagement": True,
            "customSubDomainName": foundry_resource_name
        }
    }
)

# Wait for the resource creation to complete
resource_result = resource.result()

# Create default project
project = client.projects.begin_create(
    resource_group_name=resource_group_name,
    account_name=foundry_resource_name,
    project_name=foundry_project_name,
    project={
        "location": location,
        "identity": {
            "type": "SystemAssigned"
        },
        "properties": {}
    }
)
# </create_resource_project>
# TODO: code to do role assignment to give user project manager role on the account

# <create_additional>
# Create additional project
new_project_name = 'your-new-project-name'

project = client.projects.begin_create(
    resource_group_name=resource_group_name,
    account_name=foundry_resource_name,
    project_name=new_project_name,
    project={
        "location": location,
        "identity": {
            "type": "SystemAssigned"
        },
        "properties": {}
    }
)
# </create_additional>
# <show_project>
# Get project
project = client.projects.get(
    resource_group_name=resource_group_name,
    account_name=foundry_resource_name,
    project_name=foundry_project_name
)
print(project)
# </show_project>
