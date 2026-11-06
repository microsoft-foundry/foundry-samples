// Audit baseline: assign every control in Audit mode. Nothing is blocked;
// non-compliant agents, models and tools show up in Azure Policy compliance
// and in Foundry (Manage > Govern) so you can see the impact first.
//
// Replace the example values (contoso, publishers, tool types) with your own
// before deploying. Keep the same controls in both profiles: switching from
// enforce back to this file then sets every assignment back to Audit.
using 'main.bicep'

param assignmentPrefix = 'fg'
param enforcementMode = 'Default'

param agents = {
  effect: 'Audit'
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
  effect: 'Audit'
  allowedPublishers: [
    'OpenAI'
    'Microsoft'
  ]
  denyPreviewModels: true
}

param tools = {
  effect: 'Audit'
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
  filterName: 'Jailbreak'
}
