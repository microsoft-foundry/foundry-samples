---
description: Assign Microsoft Foundry built-in Azure Policy controls for agents, models, tools and agent safety at subscription or resource group scope.
page_type: sample
products:
- azure
- azure-resource-manager
- azure-policy
urlFragment: foundry-governance-builtin-policies
languages:
- bicep
- json
---

# Govern Microsoft Foundry agents, models and tools with Azure Policy

Microsoft Foundry ships **built-in Azure Policy definitions** that Foundry itself evaluates whenever an agent, toolbox or model deployment is created or updated. This sample assigns them as code, so you can decide — for a whole subscription or a single resource group — which:

- **agent kinds** can be created, and which **container images** hosted agents may run;
- **models** can be deployed (approved publishers or model IDs, no preview models, only direct-from-Azure models);
- **tools and MCP servers** agents and toolboxes may use;
- **safety settings** agents must keep (audit only).

Start in **Audit** to see what would be affected, then switch the controls you're confident about to **Deny**.

> These built-ins use the Azure Policy resource-provider mode `Microsoft.CognitiveServices.Data`. In this mode only built-in definitions can be assigned — custom definitions aren't supported yet. For custom rules on Azure resources (connections, account kinds, authentication), see [`05-custom-policy-definitions`](../05-custom-policy-definitions/).

## Controls

| Area | Control | Built-in policy | Effects | Assigned when |
|---|---|---|---|---|
| Agents | Only allowed agent kinds | [85455646-5d02-433e-a42d-265151140427][p-kinds-allow] (preview) | Audit, Deny, Disabled | `agents.allowedAgentKinds` is set |
| Agents | No denied agent kinds | [b6ca2367-8597-4a3f-ab19-48f58d6d9278][p-kinds-deny] (preview) | Audit, Deny, Disabled | `agents.deniedAgentKinds` is set |
| Hosted agents | Only allowed container images | [d0d9ac6c-628b-46c1-a177-eb22b12ce588][p-images-allow] (preview) | Audit, Deny, Disabled | `agents.allowedContainerImages` is set |
| Hosted agents | No denied container images | [215c2c77-3afb-4f55-be2f-709b60dc8d53][p-images-deny] (preview) | Audit, Deny, Disabled | `agents.deniedContainerImages` is set |
| Models | Only approved models (publisher **or** asset ID) | [aafe3651-cb78-4f68-9f81-e7e41509110f][p-models] ([source][g-models]) | Audit, Deny, Disabled | `models.allowedPublishers` or `models.allowedAssetIds` is set |
| Models | Eligibility: no preview models, only direct from Azure | [8791d062-ba96-4c34-b604-8538f7e30ca0][p-elig] ([source][g-elig]) | Audit, Deny, Disabled | `models.denyPreviewModels` or `models.onlyAllowDirectFromAzure` is `true` |
| Tools | Only approved tools (type **or** MCP endpoint **or** MCP connector) | [e7352ad2-6c86-4a07-9573-47f67b557ba8][p-tools-allow] (preview, [source][g-tools-allow]) | Audit, Deny, Disabled | any `tools.approved*` list is set |
| Tools | No denied tools | [7740c22b-07ef-4bac-9f5a-e38d188f80b7][p-tools-deny] (preview, [source][g-tools-deny]) | Audit, Deny, Disabled | any `tools.denied*` list is set |
| Safety | Agents keep a prompt content filter (default **Jailbreak**) enabled and blocking | [9224c1cc-34fc-44f1-ad08-5c4b079c9ce6][p-safety] (preview, [source][g-safety]) | Audit, Disabled | `safety.enabled` is `true` |

Tool policies apply to both **agents** and **toolboxes**; agent-kind, container-image and safety policies apply to agents. Model policies also govern the models that [model router](https://learn.microsoft.com/azure/foundry/how-to/model-router-policy) can route to.

**More built-in policies for Foundry** (not assigned by this sample — see the [Foundry built-in policy index](https://learn.microsoft.com/azure/ai-services/policy-reference)):

- Agent multi-severity content filters (Hate, Sexual, Violence, Self-harm): [595f98a5-b562-4ab6-b9c8-2ff9f39a3f7c][p-agent-multi].
- Model deployment guardrails — the **[Preview]: Guardrail for Cognitive Services Deployments** initiative [5207647b-3e83-4e28-b836-c382cb5e2a2e][p-guardrail-initiative] (prompt, completion and multi-severity content filters, filter mode).
- Platform security for the Foundry resource: disable key access [71ef260a-8f18-47b7-abcb-62d0673d94dc][p-localauth], restrict network access [037eea7a-bd0a-46c5-9a66-03aea78705d3][p-network], use Private Link [d6759c02-b87f-42b7-892e-71b3f471d782][p-privatelink], customer-managed keys [67121cc7-ff39-4ab8-b7e3-95b84dab487d][p-cmk], diagnostic logs [1b4d1c4e-934c-4703-944c-27c82c06bebb][p-diag].

## Quick start

Prerequisites:

- Azure CLI with Bicep.
- **Owner** or **Resource Policy Contributor** on the target subscription or resource group (to create policy assignments).
- Permission to create deployments at **subscription** scope (`Microsoft.Resources/deployments/write`, for example Contributor on the subscription). `main.bicep` is a subscription-scope template, even when you target one resource group. If you only have rights on a resource group, use the Terraform version or ask a subscription admin to deploy.

1. Copy `audit-baseline.bicepparam` and replace the example values (`contoso.azurecr.io`, publishers, tool types, MCP URLs) with your own.
2. Preview and deploy in Audit mode:

   ```bash
   # Whole subscription
   az deployment sub what-if --location <region> --template-file main.bicep --parameters audit-baseline.bicepparam
   az deployment sub create  --location <region> --template-file main.bicep --parameters audit-baseline.bicepparam

   # One resource group (for example a pilot team)
   az deployment sub create --location <region> --template-file main.bicep \
     --parameters audit-baseline.bicepparam resourceGroupName=<resource-group>
   ```

3. Wait about 15 minutes for the assignments to take effect. Check **Azure Policy › Compliance** and the Foundry portal **Manage › Govern** page. New and updated agents, toolboxes and deployments report compliance; reporting can take up to 24 hours.
4. When you're happy with the impact, deploy `enforce.bicepparam` (Deny) the same way. To stage it, first deploy with `enforcementMode=DoNotEnforce`.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `resourceGroupName` | `''` | Resource group in the subscription to scope to. Empty = whole subscription. |
| `assignmentPrefix` | `fg` | Assignment names are `<prefix>-<control>`, for example `fg-tools-approved`. |
| `displayNamePrefix` | `Foundry governance` | Shown in Azure Policy and, where Foundry surfaces the blocking assignment, to developers — make it meaningful. |
| `enforcementMode` | `Default` | `DoNotEnforce` reports compliance without blocking. |
| `notScopes` | `[]` | Resource IDs inside the scope to exclude, for example a sandbox resource group or Foundry resource. |
| `agents` | `{}` | `effect`, `allowedAgentKinds`, `deniedAgentKinds`, `allowedContainerImages`, `deniedContainerImages` |
| `models` | `{}` | `effect`, `allowedPublishers`, `allowedAssetIds`, `denyPreviewModels`, `onlyAllowDirectFromAzure` |
| `tools` | `{}` | `effect`, `approvedToolTypes`, `approvedMcpEndpoints`, `approvedMcpConnectors`, `deniedToolTypes`, `deniedMcpEndpoints`, `deniedMcpConnectors` |
| `safety` | `{}` | `enabled` (`false`), `effect` (`Audit`), `filterName` (`Jailbreak`), `entityKinds` (`["prompt", "hosted"]`) |

Every `effect` defaults to `Audit`. **An empty list means the policy isn't assigned** — the template never assigns an allow-list with an empty list, because with Deny that blocks everything.

## Examples

### Tools

| Goal | `tools` value | Notes |
|---|---|---|
| Built-in tools only, no MCP | `{ effect: 'Deny', approvedToolTypes: ['web_search', 'file_search', 'code_interpreter'] }` | Every MCP server and any other tool type is blocked. |
| Built-in tools plus approved MCP servers | `{ effect: 'Deny', approvedToolTypes: ['web_search', 'file_search'], approvedMcpEndpoints: ['https://learn.microsoft.com/api/mcp*', 'https://api.githubcopilot.com/mcp/*'] }` | Don't add `mcp` to `approvedToolTypes` — that approves **every** MCP server. |
| Only MCP servers hosted in your Foundry resource | `{ effect: 'Deny', approvedMcpEndpoints: ['https://contoso-foundry.services.ai.azure.com/*'] }` | The host suffix differs per cloud. |
| Block specific tool types | `{ effect: 'Deny', deniedToolTypes: ['browser_automation', 'browser_automation_preview'] }` | Everything else stays allowed. |
| Block one MCP server | `{ effect: 'Deny', deniedMcpEndpoints: ['https://mcp.untrusted.example.com/*'] }` | |

### Agents

- Only prompt and workflow agents: `agents: { effect: 'Deny', allowedAgentKinds: ['prompt', 'workflow'] }`
- Hosted agents only from your registry: `agents: { effect: 'Deny', allowedContainerImages: ['contoso.azurecr.io/*'] }`

### Models

- Only OpenAI and Microsoft models: `models: { effect: 'Deny', allowedPublishers: ['OpenAI', 'Microsoft'] }`
- Only specific models: `models: { effect: 'Deny', allowedAssetIds: ['azureml://registries/azure-openai/models/gpt-4.1/'] }` — matched with *contains*; the trailing `/` stops `gpt-4.1` from also matching `gpt-4.1-mini`.
- No preview models: `models: { effect: 'Deny', denyPreviewModels: true }`

## Finding the values to use

| Need | Where to look |
|---|---|
| Foundry projects in scope | Azure Resource Graph: `resources \| where type =~ 'microsoft.cognitiveservices/accounts/projects'` |
| Agent kinds and tools in use | `GET https://<resource>.services.ai.azure.com/api/projects/<project>/agents?api-version=v1` — `versions.latest.definition.kind` and `.tools[].type` / `.server_url` |
| Toolbox tools | `GET https://<resource>.services.ai.azure.com/api/projects/<project>/toolboxes?api-version=v1` |
| Model publishers and asset IDs | Model card in the Foundry model catalog, or the `model.publisher` / asset ID of existing deployments. Matching isn't case-sensitive. |

## Things to know

1. **Allow-lists are OR rules.** A tool passes if its type **or** its MCP endpoint **or** its connector is approved; a model passes if its publisher **or** asset ID matches.
2. **Matching isn't case-sensitive.** MCP endpoints and container images use `like` with one `*` per value (`https://*.contoso.com/*` doesn't work); publishers use exact (case-insensitive) match; asset IDs use *contains*.
3. **Preview tool types are separate values.** Add both `browser_automation` and `browser_automation_preview` (or `web_search` and `web_search_preview`) when you mean both.
4. **The safety policy audits configuration; it doesn't apply filters** and only supports Audit/Disabled. Configure guardrails in Foundry.
5. **No custom non-compliance messages or per-agent exemptions** for these policies. Use a clear `displayNamePrefix` and exclude whole resources with `notScopes`.
6. **Assign agent-kind policies directly**, not wrapped in your own initiative, so the Foundry create-agent experience can detect them up front.
7. **What a blocked request looks like.** A blocked model deployment fails with `InvalidResourceProperties` and a message that names the policy assignment and the failed condition. Agent and toolbox requests are rejected by Foundry with a policy error that references the assignment.
8. **Preview controls** (agents, container images, tools, safety) are rolling out region by region. Start with the audit baseline and confirm a Deny test in a sandbox resource group before relying on enforcement.
9. **Model router** needs `Microsoft` in `allowedPublishers` (or its asset ID) in addition to the publishers of every model it routes to.

## Change or roll back

Bicep deployments are **incremental**: taking a control out of your parameter file, or changing `assignmentPrefix` or the scope, does **not** delete the assignment that's already there.

- Keep the **same controls** in your audit and enforce parameter files (as the provided profiles do). Switching back to the audit file then sets every assignment back to Audit.
- To turn one control off, set its `effect` to `Disabled` and redeploy, or delete the assignment (see [Clean up](#clean-up)).
- To have removed controls deleted automatically, deploy as a [deployment stack](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks):

  ```bash
  az stack sub create --name foundry-governance --location <region> \
    --template-file main.bicep --parameters audit-baseline.bicepparam \
    --action-on-unmanage deleteResources --deny-settings-mode none
  ```

Terraform tracks the assignments in its state and deletes removed ones on `apply`.

## Coming soon

- Hosted agent egress control — an outbound domain allow-list for hosted agents.
- Custom Azure Policy definitions for Foundry agents, tools and models.

## Clean up

```bash
az policy assignment list --scope <scope> --query "[?starts_with(name, 'fg-')].name" -o tsv |
  xargs -I{} az policy assignment delete --name {} --scope <scope>
```

## Learn more

- [Built-in policies for model deployment](https://learn.microsoft.com/azure/foundry/how-to/model-deployment-policy)
- [Govern model router deployments with Azure Policy](https://learn.microsoft.com/azure/foundry/how-to/model-router-policy)
- [Create custom policies for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/custom-policy-definition)
- [Azure Policy resource provider modes](https://learn.microsoft.com/azure/governance/policy/concepts/definition-structure-basics#mode)

[p-kinds-allow]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F85455646-5d02-433e-a42d-265151140427
[p-kinds-deny]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2Fb6ca2367-8597-4a3f-ab19-48f58d6d9278
[p-images-allow]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2Fd0d9ac6c-628b-46c1-a177-eb22b12ce588
[p-images-deny]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F215c2c77-3afb-4f55-be2f-709b60dc8d53
[p-models]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2Faafe3651-cb78-4f68-9f81-e7e41509110f
[p-elig]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F8791d062-ba96-4c34-b604-8538f7e30ca0
[p-tools-allow]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2Fe7352ad2-6c86-4a07-9573-47f67b557ba8
[p-tools-deny]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F7740c22b-07ef-4bac-9f5a-e38d188f80b7
[p-safety]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F9224c1cc-34fc-44f1-ad08-5c4b079c9ce6
[p-agent-multi]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F595f98a5-b562-4ab6-b9c8-2ff9f39a3f7c
[p-guardrail-initiative]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicySetDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicySetDefinitions%2F5207647b-3e83-4e28-b836-c382cb5e2a2e
[p-localauth]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F71ef260a-8f18-47b7-abcb-62d0673d94dc
[p-network]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F037eea7a-bd0a-46c5-9a66-03aea78705d3
[p-privatelink]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2Fd6759c02-b87f-42b7-892e-71b3f471d782
[p-cmk]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F67121cc7-ff39-4ab8-b7e3-95b84dab487d
[p-diag]: https://portal.azure.com/#blade/Microsoft_Azure_Policy/PolicyDetailBlade/definitionId/%2Fproviders%2FMicrosoft.Authorization%2FpolicyDefinitions%2F1b4d1c4e-934c-4703-944c-27c82c06bebb
[g-models]: https://github.com/Azure/azure-policy/blob/master/built-in-policies/policyDefinitions/Cognitive%20Services/AllowDeployRegistryModels_Audit.json
[g-elig]: https://github.com/Azure/azure-policy/blob/master/built-in-policies/policyDefinitions/Cognitive%20Services/AllowDeploymentModelEligibility_Audit.json
[g-tools-allow]: https://github.com/Azure/azure-policy/blob/master/built-in-policies/policyDefinitions/Cognitive%20Services/AllowAgentAndToolboxTools_Audit.json
[g-tools-deny]: https://github.com/Azure/azure-policy/blob/master/built-in-policies/policyDefinitions/Cognitive%20Services/DenyAgentAndToolboxTools_Audit.json
[g-safety]: https://github.com/Azure/azure-policy/blob/master/built-in-policies/policyDefinitions/Cognitive%20Services/AllowAgentPromptControl_Audit.json

`Tags: Azure Policy, Governance, Microsoft.CognitiveServices`
