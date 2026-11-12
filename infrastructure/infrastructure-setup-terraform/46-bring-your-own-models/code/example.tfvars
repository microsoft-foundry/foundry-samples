# Rename to terraform.tfvars, or pass with `-var-file=example.tfvars`.
# Do NOT commit real API keys or subscription IDs to source control.

# --- Subscription targeting (two subs, one per tier) ---
platform_subscription_id    = "00000000-0000-0000-0000-000000000000"
development_subscription_id = "11111111-1111-1111-1111-111111111111"

# Required by azapi provider (does not auto-detect tenant). Get with:
# az account show --query tenantId -o tsv
tenant_id = "33333333-3333-3333-3333-333333333333"

# --- Common ---
location    = "swedencentral"
name_prefix = "contoso-byom"

# --- APIM publisher metadata (required by APIM at create time) ---
apim_publisher_name  = "Contoso Platform Team"
apim_publisher_email = "platform@contoso.example.com"

# --- Foundry backend model (Sub A) ---
foundry_model_name     = "gpt-4.1"
foundry_model_version  = "2025-04-14"
foundry_model_capacity = 40

# --- Non-Microsoft provider keys (Sub A → Key Vault). Get free keys at:
# Gemini: https://aistudio.google.com/apikey
# Groq:   https://console.groq.com/keys
gemini_api_key = "REPLACE_ME_WITH_GOOGLE_AI_STUDIO_KEY"
groq_api_key   = "REPLACE_ME_WITH_GROQ_KEY"

# --- Optional model overrides ---
# gemini_model_name = "gemini-2.5-flash"
# gemini_alias      = "gemini-flash"
# groq_model_name   = "llama-3.3-70b-versatile"
# groq_alias        = "llama-3-70b"

# --- Governance knobs ---
quota_tokens_per_minute = 167   # ~10K tokens/hour per project — demo-friendly

# --- Developer group (Sub B) ---
# Object ID of the Entra group whose members will get read/use access on
# both governed projects. Members cannot deploy models.
developer_group_object_id = "22222222-2222-2222-2222-222222222222"

# Override only if you deliberately want a different role. Default is the
# Foundry-native user role (currently displayed as "Foundry User"; formerly
# "Azure AI User"; same GUID either way).
# developer_role_definition_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
