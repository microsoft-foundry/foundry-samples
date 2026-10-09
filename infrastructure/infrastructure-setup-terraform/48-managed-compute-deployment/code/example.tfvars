subscription_id      = "00000000-0000-0000-0000-000000000000"
resource_group_name  = "your-resource-group"
foundry_account_name = "your-foundry-account"

# Canonical defaults shown explicitly for discoverability.
deployment_name_prefix = "gemma-4-31b-it-a100"
model_id               = "azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5"
deployment_template_id = "azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest"
accelerator_type       = "A100_80GB"
capacity               = 1
version_upgrade_option = "OnceNewDefaultVersionAvailable"
