########## Which built-in policies to assign, with which parameters.
########## An empty list means "don't assign that policy" — never an allow-list
########## policy with an empty list, which with Deny would block everything.

locals {
  builtin = "/providers/Microsoft.Authorization/policyDefinitions"

  planned = concat(
    # Agents: kinds and hosted-agent container images
    length(var.agents.allowed_agent_kinds) == 0 ? [] : [{
      key          = "agent-kinds-allow"
      display_name = "Agents use only allowed agent kinds"
      policy_id    = "85455646-5d02-433e-a42d-265151140427"
      parameters = jsonencode({
        effect            = { value = var.agents.effect }
        allowedAgentKinds = { value = var.agents.allowed_agent_kinds }
      })
    }],
    length(var.agents.denied_agent_kinds) == 0 ? [] : [{
      key          = "agent-kinds-deny"
      display_name = "Agents do not use denied agent kinds"
      policy_id    = "b6ca2367-8597-4a3f-ab19-48f58d6d9278"
      parameters = jsonencode({
        effect           = { value = var.agents.effect }
        deniedAgentKinds = { value = var.agents.denied_agent_kinds }
      })
    }],
    length(var.agents.allowed_container_images) == 0 ? [] : [{
      key          = "agent-images-allow"
      display_name = "Hosted agents use only allowed container images"
      policy_id    = "d0d9ac6c-628b-46c1-a177-eb22b12ce588"
      parameters = jsonencode({
        effect                 = { value = var.agents.effect }
        allowedContainerImages = { value = var.agents.allowed_container_images }
      })
    }],
    length(var.agents.denied_container_images) == 0 ? [] : [{
      key          = "agent-images-deny"
      display_name = "Hosted agents do not use denied container images"
      policy_id    = "215c2c77-3afb-4f55-be2f-709b60dc8d53"
      parameters = jsonencode({
        effect                = { value = var.agents.effect }
        deniedContainerImages = { value = var.agents.denied_container_images }
      })
    }],

    # Models
    length(var.models.allowed_publishers) == 0 && length(var.models.allowed_asset_ids) == 0 ? [] : [{
      key          = "models-approved"
      display_name = "Model deployments use only approved models"
      policy_id    = "aafe3651-cb78-4f68-9f81-e7e41509110f"
      parameters = jsonencode({
        effect            = { value = var.models.effect }
        allowedPublishers = { value = var.models.allowed_publishers }
        allowedAssetIds   = { value = var.models.allowed_asset_ids }
      })
    }],
    !var.models.deny_preview_models && !var.models.only_allow_direct_from_azure ? [] : [{
      key          = "models-eligibility"
      display_name = "Model deployments meet eligibility requirements"
      policy_id    = "8791d062-ba96-4c34-b604-8538f7e30ca0"
      parameters = jsonencode({
        effect                   = { value = var.models.effect }
        denyPreviewModels        = { value = var.models.deny_preview_models }
        onlyAllowDirectFromAzure = { value = var.models.only_allow_direct_from_azure }
      })
    }],

    # Tools (agents and toolboxes)
    length(concat(var.tools.approved_tool_types, var.tools.approved_mcp_endpoints, var.tools.approved_mcp_connectors)) == 0 ? [] : [{
      key          = "tools-approved"
      display_name = "Agents and toolboxes use only approved tools"
      policy_id    = "e7352ad2-6c86-4a07-9573-47f67b557ba8"
      parameters = jsonencode({
        effect                = { value = var.tools.effect }
        approvedToolTypes     = { value = var.tools.approved_tool_types }
        approvedMcpEndpoints  = { value = var.tools.approved_mcp_endpoints }
        approvedMcpConnectors = { value = var.tools.approved_mcp_connectors }
      })
    }],
    length(concat(var.tools.denied_tool_types, var.tools.denied_mcp_endpoints, var.tools.denied_mcp_connectors)) == 0 ? [] : [{
      key          = "tools-denied"
      display_name = "Agents and toolboxes do not use denied tools"
      policy_id    = "7740c22b-07ef-4bac-9f5a-e38d188f80b7"
      parameters = jsonencode({
        effect              = { value = var.tools.effect }
        deniedToolTypes     = { value = var.tools.denied_tool_types }
        deniedMcpEndpoints  = { value = var.tools.denied_mcp_endpoints }
        deniedMcpConnectors = { value = var.tools.denied_mcp_connectors }
      })
    }],

    # Agent safety (audit-only)
    !var.safety.enabled ? [] : [{
      key          = "agent-prompt-filter"
      display_name = "Agents keep the ${var.safety.filter_name} prompt filter on"
      policy_id    = "9224c1cc-34fc-44f1-ad08-5c4b079c9ce6"
      parameters = jsonencode({
        effect                   = { value = var.safety.effect }
        filterName               = { value = var.safety.filter_name }
        entityKind               = { value = var.safety.entity_kinds }
        allowedEnabledForPrompt  = { value = ["true"] }
        allowedBlockingForPrompt = { value = ["true"] }
      })
    }],
  )

  assignments = { for a in local.planned : a.key => a }
  description = "Assigned by the Microsoft Foundry governance template (06-foundry-governance)."
  metadata    = jsonencode({ source = "foundry-samples/06-foundry-governance" })
}

########## Scope

data "azurerm_subscription" "current" {}

data "azurerm_resource_group" "target" {
  count = var.resource_group_name == null ? 0 : 1
  name  = var.resource_group_name
}

########## Assignments — subscription scope (resource_group_name = null)

resource "azurerm_subscription_policy_assignment" "this" {
  for_each = var.resource_group_name == null ? local.assignments : {}

  name                 = "${var.assignment_prefix}-${each.key}"
  subscription_id      = data.azurerm_subscription.current.id
  policy_definition_id = "${local.builtin}/${each.value.policy_id}"
  display_name         = "${var.display_name_prefix}: ${each.value.display_name}"
  description          = local.description
  enforce              = var.enforce
  not_scopes           = var.not_scopes
  parameters           = each.value.parameters
  metadata             = local.metadata
}

########## Assignments — resource group scope (resource_group_name set)

resource "azurerm_resource_group_policy_assignment" "this" {
  for_each = var.resource_group_name == null ? {} : local.assignments

  name                 = "${var.assignment_prefix}-${each.key}"
  resource_group_id    = data.azurerm_resource_group.target[0].id
  policy_definition_id = "${local.builtin}/${each.value.policy_id}"
  display_name         = "${var.display_name_prefix}: ${each.value.display_name}"
  description          = local.description
  enforce              = var.enforce
  not_scopes           = var.not_scopes
  parameters           = each.value.parameters
  metadata             = local.metadata
}
