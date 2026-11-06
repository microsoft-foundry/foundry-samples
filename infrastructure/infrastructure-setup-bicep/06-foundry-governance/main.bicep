// =============================================================================
// Microsoft Foundry governance – built-in Azure Policy controls for Foundry
// agents, models, tools and agent safety, assigned as code.
//
// Deploy at subscription scope:
//   az deployment sub create --location <region> --template-file main.bicep \
//     --parameters audit-baseline.bicepparam
//
// Deploy to one resource group (set resourceGroupName):
//   az deployment sub create --location <region> --template-file main.bicep \
//     --parameters audit-baseline.bicepparam resourceGroupName=<resource-group>
//
// Rule of thumb: an empty list means "don't assign that policy". The template
// never assigns an allow-list policy with an empty list, because with Deny
// that would block every agent, model or tool.
// =============================================================================

targetScope = 'subscription'

metadata description = 'Assigns Microsoft Foundry built-in Azure Policy controls for agents, models, tools and agent safety at subscription or resource group scope.'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

@description('Effect for controls that can block requests.')
type effect = 'Audit' | 'Deny' | 'Disabled'

@description('Agent kind and hosted-agent container image controls.')
type agentControls = {
  @description('Audit (default), Deny or Disabled.')
  effect: effect?

  @description('Only these agent kinds are allowed, for example ["prompt", "hosted", "workflow"]. Empty = not assigned.')
  allowedAgentKinds: string[]?

  @description('These agent kinds are denied, for example ["external"]. Empty = not assigned.')
  deniedAgentKinds: string[]?

  @description('Hosted agents may only use these images, for example ["contoso.azurecr.io/*"]. Empty = not assigned.')
  allowedContainerImages: string[]?

  @description('Hosted agents may not use these images, for example ["docker.io/*"]. Empty = not assigned.')
  deniedContainerImages: string[]?
}

@description('Model deployment controls.')
type modelControls = {
  @description('Audit (default), Deny or Disabled.')
  effect: effect?

  @description('Approved model publishers, for example ["OpenAI", "Microsoft"]. Use the publisher name from the model card.')
  allowedPublishers: string[]?

  @description('Approved model asset IDs or prefixes, for example ["azureml://registries/azure-openai/models/gpt-4.1/"]. Matched with "contains".')
  allowedAssetIds: string[]?

  @description('Block models whose lifecycle status is Preview.')
  denyPreviewModels: bool?

  @description('Only allow models that are distributed directly from Azure.')
  onlyAllowDirectFromAzure: bool?
}

@description('Tool controls for agents and toolboxes.')
type toolControls = {
  @description('Audit (default), Deny or Disabled.')
  effect: effect?

  @description('Approved tool types, for example ["web_search", "file_search", "code_interpreter"]. Adding "mcp" approves every MCP server.')
  approvedToolTypes: string[]?

  @description('Approved MCP server URLs. Case-insensitive; one "*" per value, for example "https://learn.microsoft.com/api/mcp*".')
  approvedMcpEndpoints: string[]?

  @description('Approved MCP connector IDs.')
  approvedMcpConnectors: string[]?

  @description('Denied tool types, for example ["browser_automation", "browser_automation_preview"].')
  deniedToolTypes: string[]?

  @description('Denied MCP server URLs, for example ["https://mcp.example.com/*"].')
  deniedMcpEndpoints: string[]?

  @description('Denied MCP connector IDs.')
  deniedMcpConnectors: string[]?
}

@description('Agent safety: audit that agents keep a required prompt content filter on. Audit-only.')
type safetyControls = {
  @description('Assign the agent prompt content filter policy. Default: false.')
  enabled: bool?

  @description('Audit (default) or Disabled. This policy does not support Deny.')
  effect: ('Audit' | 'Disabled')?

  @description('Prompt content filter that must be enabled and blocking. Default: Jailbreak.')
  filterName: ('Jailbreak' | 'Indirect Attack' | 'Indirect Attack Spotlighting' | 'Profanity')?

  @description('Agent entity kinds evaluated by the policy. Default: ["prompt", "hosted"].')
  entityKinds: string[]?
}

@description('One planned policy assignment.')
type plannedAssignment = {
  key: string
  displayName: string
  policyDefinitionId: string
  @description('Major-version selector: 1.*.*-preview for preview built-ins, 1.*.* for GA built-ins.')
  definitionVersion: string
  parameters: object
}

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@description('Optional. Resource group in this subscription to scope the assignments to. Empty = whole subscription.')
param resourceGroupName string = ''

@description('Prefix for assignment names (<prefix>-<control>).')
@minLength(1)
@maxLength(10)
param assignmentPrefix string = 'fg'

@description('Prefix for assignment display names. Foundry shows the display name when a request is blocked.')
param displayNamePrefix string = 'Foundry governance'

@description('Default enforces the effects. DoNotEnforce evaluates and reports compliance without blocking (what-if mode).')
@allowed([
  'Default'
  'DoNotEnforce'
])
param enforcementMode string = 'Default'

@description('Resource IDs inside the scope to exclude, for example a sandbox resource group or Foundry account.')
param notScopes string[] = []

@description('Agent kind and hosted-agent container image controls.')
param agents agentControls = {}

@description('Model deployment controls.')
param models modelControls = {}

@description('Tool controls for agents and toolboxes.')
param tools toolControls = {}

@description('Agent safety (audit-only) controls.')
param safety safetyControls = {}

// ---------------------------------------------------------------------------
// Rules: which built-in policies to assign, with which parameters
// ---------------------------------------------------------------------------

func builtIn(policyId string) string => '/providers/Microsoft.Authorization/policyDefinitions/${policyId}'

func listOrEmpty(value string[]?) string[] => value ?? []

func agentAssignments(c agentControls) plannedAssignment[] => concat(
  empty(listOrEmpty(c.?allowedAgentKinds))
    ? []
    : [
        {
          key: 'agent-kinds-allow'
          displayName: 'Agents use only allowed agent kinds'
          policyDefinitionId: builtIn('85455646-5d02-433e-a42d-265151140427')
          definitionVersion: '1.*.*-preview'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            allowedAgentKinds: { value: listOrEmpty(c.?allowedAgentKinds) }
          }
        }
      ],
  empty(listOrEmpty(c.?deniedAgentKinds))
    ? []
    : [
        {
          key: 'agent-kinds-deny'
          displayName: 'Agents do not use denied agent kinds'
          policyDefinitionId: builtIn('b6ca2367-8597-4a3f-ab19-48f58d6d9278')
          definitionVersion: '1.*.*-preview'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            deniedAgentKinds: { value: listOrEmpty(c.?deniedAgentKinds) }
          }
        }
      ],
  empty(listOrEmpty(c.?allowedContainerImages))
    ? []
    : [
        {
          key: 'agent-images-allow'
          displayName: 'Hosted agents use only allowed container images'
          policyDefinitionId: builtIn('d0d9ac6c-628b-46c1-a177-eb22b12ce588')
          definitionVersion: '1.*.*-preview'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            allowedContainerImages: { value: listOrEmpty(c.?allowedContainerImages) }
          }
        }
      ],
  empty(listOrEmpty(c.?deniedContainerImages))
    ? []
    : [
        {
          key: 'agent-images-deny'
          displayName: 'Hosted agents do not use denied container images'
          policyDefinitionId: builtIn('215c2c77-3afb-4f55-be2f-709b60dc8d53')
          definitionVersion: '1.*.*-preview'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            deniedContainerImages: { value: listOrEmpty(c.?deniedContainerImages) }
          }
        }
      ]
)

func modelAssignments(c modelControls) plannedAssignment[] => concat(
  empty(listOrEmpty(c.?allowedPublishers)) && empty(listOrEmpty(c.?allowedAssetIds))
    ? []
    : [
        {
          key: 'models-approved'
          displayName: 'Model deployments use only approved models'
          policyDefinitionId: builtIn('aafe3651-cb78-4f68-9f81-e7e41509110f')
          definitionVersion: '1.*.*'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            allowedPublishers: { value: listOrEmpty(c.?allowedPublishers) }
            allowedAssetIds: { value: listOrEmpty(c.?allowedAssetIds) }
          }
        }
      ],
  !(c.?denyPreviewModels ?? false) && !(c.?onlyAllowDirectFromAzure ?? false)
    ? []
    : [
        {
          key: 'models-eligibility'
          displayName: 'Model deployments meet eligibility requirements'
          policyDefinitionId: builtIn('8791d062-ba96-4c34-b604-8538f7e30ca0')
          definitionVersion: '1.*.*'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            denyPreviewModels: { value: c.?denyPreviewModels ?? false }
            onlyAllowDirectFromAzure: { value: c.?onlyAllowDirectFromAzure ?? false }
          }
        }
      ]
)

func toolAssignments(c toolControls) plannedAssignment[] => concat(
  empty(listOrEmpty(c.?approvedToolTypes)) && empty(listOrEmpty(c.?approvedMcpEndpoints)) && empty(listOrEmpty(c.?approvedMcpConnectors))
    ? []
    : [
        {
          key: 'tools-approved'
          displayName: 'Agents and toolboxes use only approved tools'
          policyDefinitionId: builtIn('e7352ad2-6c86-4a07-9573-47f67b557ba8')
          definitionVersion: '1.*.*-preview'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            approvedToolTypes: { value: listOrEmpty(c.?approvedToolTypes) }
            approvedMcpEndpoints: { value: listOrEmpty(c.?approvedMcpEndpoints) }
            approvedMcpConnectors: { value: listOrEmpty(c.?approvedMcpConnectors) }
          }
        }
      ],
  empty(listOrEmpty(c.?deniedToolTypes)) && empty(listOrEmpty(c.?deniedMcpEndpoints)) && empty(listOrEmpty(c.?deniedMcpConnectors))
    ? []
    : [
        {
          key: 'tools-denied'
          displayName: 'Agents and toolboxes do not use denied tools'
          policyDefinitionId: builtIn('7740c22b-07ef-4bac-9f5a-e38d188f80b7')
          definitionVersion: '1.*.*-preview'
          parameters: {
            effect: { value: c.?effect ?? 'Audit' }
            deniedToolTypes: { value: listOrEmpty(c.?deniedToolTypes) }
            deniedMcpEndpoints: { value: listOrEmpty(c.?deniedMcpEndpoints) }
            deniedMcpConnectors: { value: listOrEmpty(c.?deniedMcpConnectors) }
          }
        }
      ]
)

func safetyAssignments(c safetyControls) plannedAssignment[] => !(c.?enabled ?? false)
  ? []
  : [
      {
        key: 'agent-prompt-filter'
        displayName: 'Agents keep the ${c.?filterName ?? 'Jailbreak'} prompt filter on'
        policyDefinitionId: builtIn('9224c1cc-34fc-44f1-ad08-5c4b079c9ce6')
        definitionVersion: '1.*.*-preview'
        parameters: {
          effect: { value: c.?effect ?? 'Audit' }
          filterName: { value: c.?filterName ?? 'Jailbreak' }
          entityKind: { value: c.?entityKinds ?? ['prompt', 'hosted'] }
          allowedEnabledForPrompt: { value: ['true'] }
          allowedBlockingForPrompt: { value: ['true'] }
        }
      }
    ]

var plan = concat(agentAssignments(agents), modelAssignments(models), toolAssignments(tools), safetyAssignments(safety))

var assignmentDefinitions = [
  for a in plan: {
    name: '${assignmentPrefix}-${a.key}'
    properties: {
      displayName: '${displayNamePrefix}: ${a.displayName}'
      description: 'Assigned by the Microsoft Foundry governance template (06-foundry-governance).'
      policyDefinitionId: a.policyDefinitionId
      definitionVersion: a.definitionVersion
      enforcementMode: enforcementMode
      notScopes: notScopes
      parameters: a.parameters
      metadata: {
        source: 'foundry-samples/06-foundry-governance'
      }
    }
  }
]

// ---------------------------------------------------------------------------
// Assignments
// ---------------------------------------------------------------------------

resource subscriptionAssignments 'Microsoft.Authorization/policyAssignments@2024-04-01' = [
  for a in (empty(resourceGroupName) ? assignmentDefinitions : []): {
    name: a.name
    properties: a.properties
  }
]

// Bicep needs a module to deploy to a different scope than the file's targetScope.
module resourceGroupAssignments 'modules/assign-to-resource-group.bicep' = if (!empty(resourceGroupName)) {
  name: '${assignmentPrefix}-foundry-governance'
  scope: resourceGroup(empty(resourceGroupName) ? 'unused' : resourceGroupName)
  params: {
    assignments: assignmentDefinitions
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

@description('Scope the policies were assigned to.')
output scope string = empty(resourceGroupName) ? subscription().id : '${subscription().id}/resourceGroups/${resourceGroupName}'

@description('Assignments that were created or updated.')
output assignments array = [
  for a in assignmentDefinitions: {
    name: a.name
    displayName: a.properties.displayName
    policyDefinitionId: a.properties.policyDefinitionId
  }
]
