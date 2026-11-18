# Enforce: block non-compliant agents, models and tools (Deny).
# Agent safety stays Audit — that policy doesn't support Deny.
# Tip: run with enforce = false first to check the assignments without blocking anyone.
# Replace the example values (subscription, contoso, publishers, tool types).

subscription_id     = "<subscription-id>"
resource_group_name = null # or "<resource-group>"
assignment_prefix   = "fg"
enforce             = true

agents = {
  effect                   = "Deny"
  allowed_agent_kinds      = ["prompt", "hosted", "workflow"]
  allowed_container_images = ["contoso.azurecr.io/*"]
}

models = {
  effect              = "Deny"
  allowed_publishers  = ["OpenAI", "Microsoft"]
  deny_preview_models = true
}

tools = {
  effect                 = "Deny"
  approved_tool_types    = ["web_search", "file_search", "code_interpreter", "azure_ai_search", "function"]
  approved_mcp_endpoints = ["https://learn.microsoft.com/api/mcp*"]
  denied_tool_types      = ["browser_automation", "browser_automation_preview"]
}

safety = {
  enabled     = true
  effect      = "Audit"
  filter_name = "Jailbreak"
}
