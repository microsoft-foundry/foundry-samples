# Audit baseline: every control in Audit mode — nothing is blocked.
# Replace the example values (subscription, contoso, publishers, tool types).

subscription_id     = "<subscription-id>"
resource_group_name = null # or "<resource-group>" to scope to one resource group
assignment_prefix   = "fg"
enforce             = true

agents = {
  effect                   = "Audit"
  allowed_agent_kinds      = ["prompt", "hosted", "workflow"]
  allowed_container_images = ["contoso.azurecr.io/*"]
}

models = {
  effect              = "Audit"
  allowed_publishers  = ["OpenAI", "Microsoft"]
  deny_preview_models = true
}

tools = {
  effect                 = "Audit"
  approved_tool_types    = ["web_search", "file_search", "code_interpreter", "azure_ai_search", "function"]
  approved_mcp_endpoints = ["https://learn.microsoft.com/api/mcp*"]
  denied_tool_types      = ["browser_automation", "browser_automation_preview"]
}

safety = {
  enabled     = true
  filter_name = "Jailbreak"
}
