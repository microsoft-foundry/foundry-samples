# Govern Microsoft Foundry agents, models and tools with Azure Policy (Terraform)

Terraform version of [`06-foundry-governance`](../../infrastructure-setup-bicep/06-foundry-governance/). It assigns Microsoft Foundry **built-in Azure Policy definitions** — evaluated by Foundry whenever an agent, toolbox or model deployment is created or updated — at **subscription** or **resource group** scope.

See the Bicep README for the full [controls table](../../infrastructure-setup-bicep/06-foundry-governance/README.md#controls), [examples](../../infrastructure-setup-bicep/06-foundry-governance/README.md#examples) and [things to know](../../infrastructure-setup-bicep/06-foundry-governance/README.md#things-to-know). The variables mirror the Bicep parameters in snake_case.

## Quick start

Prerequisites: Terraform 1.10+, Azure CLI signed in, and **Owner** or **Resource Policy Contributor** on the target scope.

```bash
cd code
cp audit-baseline.tfvars my.tfvars   # replace subscription_id and the example values
terraform init
terraform plan  -var-file=my.tfvars
terraform apply -var-file=my.tfvars
```

- Set `resource_group_name = "<resource-group>"` to assign to one resource group instead of the whole subscription.
- Wait about 15 minutes for assignments to take effect; compliance can take up to 24 hours to report.
- Then apply `enforce.tfvars` (Deny). Set `enforce = false` first to stage it without blocking.

## Variables

| Variable | Default | Description |
|---|---|---|
| `subscription_id` | — | Subscription to assign in. |
| `resource_group_name` | `null` | Resource group to scope to. `null` = whole subscription. |
| `assignment_prefix` | `fg` | Assignment names are `<prefix>-<control>`. |
| `display_name_prefix` | `Foundry governance` | Shown to developers when Foundry blocks a request. |
| `enforce` | `true` | `false` = DoNotEnforce (report only). |
| `not_scopes` | `[]` | Resource IDs inside the scope to exclude. |
| `agents` | `{}` | `effect`, `allowed_agent_kinds`, `denied_agent_kinds`, `allowed_container_images`, `denied_container_images` |
| `models` | `{}` | `effect`, `allowed_publishers`, `allowed_asset_ids`, `deny_preview_models`, `only_allow_direct_from_azure` |
| `tools` | `{}` | `effect`, `approved_tool_types`, `approved_mcp_endpoints`, `approved_mcp_connectors`, `denied_tool_types`, `denied_mcp_endpoints`, `denied_mcp_connectors` |
| `safety` | `{}` | `enabled` (`false`), `effect` (`Audit`), `filter_name` (`Jailbreak`), `entity_kinds` (`["prompt", "hosted"]`) |

Every `effect` defaults to `Audit`. **An empty list means the policy isn't assigned** — never an allow-list with an empty list, which with Deny blocks everything.

## Notes

- Assignments use `azurerm_subscription_policy_assignment` / `azurerm_resource_group_policy_assignment`. These resources don't expose a definition version; Azure fills in the major-version selector (`1.*.*-preview` for preview built-ins, `1.*.*` for GA), and `terraform plan` stays clean on re-runs.
- Parameters are passed as JSON, so the assignment matches what the Azure portal and Foundry create.

`Tags: Azure Policy, Governance, Microsoft.CognitiveServices`
