// Enforce: block non-compliant agents, models and tools (Deny).
// Agent safety stays Audit — that policy doesn't support Deny.
//
// Start with audit-baseline.bicepparam, review compliance, then switch to this
// profile. Tip: deploy with enforcementMode = 'DoNotEnforce' first to check the
// assignments without blocking anyone.
//
// Replace the example values (contoso, publishers, tool types) with your own.
using 'main.bicep'

param assignmentPrefix = 'fg'
param enforcementMode = 'Default'

param agents = {
  effect: 'Deny'
  allowedAgentKinds: [
    'prompt'
    'hosted'
    'workflow'
  ]
  allowedContainerImages: [
    'contoso.azurecr.io/*'
  ]
}

param models = {
  effect: 'Deny'
  allowedPublishers: [
    'OpenAI'
    'Microsoft'
  ]
  denyPreviewModels: true
}

param tools = {
  effect: 'Deny'
  approvedToolTypes: [
    'web_search'
    'file_search'
    'code_interpreter'
    'azure_ai_search'
    'function'
  ]
  approvedMcpEndpoints: [
    'https://learn.microsoft.com/api/mcp*'
  ]
  deniedToolTypes: [
    'browser_automation'
    'browser_automation_preview'
  ]
}

param safety = {
  enabled: true
  effect: 'Audit'
  filterName: 'Jailbreak'
}
