# Foundry private setup (evaluation-only)

Sets up a private-network Microsoft Foundry environment for evaluation and
data-generation from one JSON input. Every component is either **created** by the
setup or **brought by you** (BYO, `mode: existing`), so the same tool covers a new
environment and an existing account/project.

The setup plans locally, asks you to approve the plan once, then deploys the bundled
Bicep in dependency order with a what-if preview before every write. A stopped run
resumes safely by rerunning the same command.

This folder is an agent skill. You can either:

- **Use it with an AI agent:** add this folder unchanged to your agent's skills
  directory (for GitHub Copilot, for example `.github/skills/foundry-private-setup`)
  and ask it to set up a private Foundry evaluation environment. The agent follows
  [SKILL.md](SKILL.md) and asks you before it approves the plan or confirms the
  account-wide step.
- **Run it yourself** with the commands below.

Input rules are in [references/scenarios.md](references/scenarios.md); running or
re-checking individual steps is in [references/operations.md](references/operations.md).

## Before you start

| Requirement | Notes |
|---|---|
| PowerShell | 7.2 or later (`pwsh`) |
| Azure CLI with Bicep | Signed in (`az login`) to the target tenant. Nothing is downloaded or installed by the script. |
| Permissions | Read and deploy rights on every scope you select, plus `Microsoft.Authorization/roleAssignments/write` (for example Role Based Access Control Administrator) where the project identity is granted access. Contributor alone cannot create role assignments. |
| Region | The account, project, VNet and created resources use one region (`location`). |
| Time | About 30 minutes in total, with one planned pause for confirmation. |

## Run it yourself

Keep this folder unchanged and keep your input, plan and state next to it, not
inside it. If files inside this folder change, Run refuses the plan.

```text
my-setup\
  foundry-private-setup\   this folder, unchanged
  input.json               your input (copy an example from foundry-private-setup\assets)
  plan.json                written by Plan
  state\                   written by Run
```

From `my-setup`:

```powershell
pwsh -NoProfile -File .\foundry-private-setup\scripts\Setup.ps1 -Action Toolchain
pwsh -NoProfile -File .\foundry-private-setup\scripts\Setup.ps1 -Action Plan -ConfigPath .\input.json -OutputPath .\plan.json
# Review the printed plan, then approve it by its planHash:
pwsh -NoProfile -File .\foundry-private-setup\scripts\Setup.ps1 -Action Run -GraphPath .\plan.json -StateDirectory .\state -ApprovePlan <planHash>
# The run pauses before agent network injection (an account-wide change). After reviewing it:
pwsh -NoProfile -File .\foundry-private-setup\scripts\Setup.ps1 -Action Run -GraphPath .\plan.json -StateDirectory .\state -ApprovePlan <planHash> -AcknowledgeAccountWideImpact
```

| Example input | Use when |
|---|---|
| `assets/input.example.json` | Everything new, with private monitoring |
| `assets/input.no-monitoring.example.json` | Everything new, no monitoring |
| `assets/input.existing.example.json` | Existing account/project, network, storage and DNS zones |

### What to expect

1. **Plan** reads Azure, changes nothing, and prints every step with the exact
   resources it may write (`writeScopes`) and a `planHash`. Check that every write
   scope is a resource you expect the setup to touch before approving.
2. **First Run** (about 20 minutes) completes everything up to agent network
   injection and stops with status `AwaitingAccountWideConfirmation`.
3. **Second Run** with `-AcknowledgeAccountWideImpact` (about 10 minutes) finishes
   with status `Completed` and every step `Succeeded`.

Each Run prints a JSON summary with the status of every step. Details, previews and
any error for each step are kept in the state folder (`state\run.json`).

### Recovering from a stopped run

Rerunning the same Run command is always the first step. It never replays completed
writes and never resubmits a write whose outcome is unconfirmed.

- Transient Azure read failures are retried automatically. If one persists, the error
  says the read changed nothing; fix the cause and rerun.
- After you fix the cause shown in a step's error, rerunning retries a Failed
  deployment once.
- If a private endpoint this setup created is left in a Failed state, the error prints
  the exact `az network private-endpoint delete` command; delete it, then rerun.
- If Run says package files changed, it names the added, removed or changed files.
  Restore this folder unchanged and run Plan again.
## What is mandatory, optional, and bring-your-own

**Mandatory** components are always part of the setup: you either let the setup
create them or supply your own. **Optional** components can be turned off entirely.

| Component | Mandatory? | Create (new) | Bring your own (`mode: existing`) | BYO requirements |
|---|---|---|---|---|
| Resource group | Yes | `name` | `name` | In the configured subscription. Only read, never updated. |
| Foundry account | Yes | `name`, `publicNetworkAccess` | `resourceId` | Same subscription and region; system-assigned identity; account and project must both be new or both be existing. |
| Foundry project | Yes | `name` | `resourceId` | Must belong to the selected account; the account has exactly one project; system-assigned identity. |
| Storage account | Yes | `name`, `publicNetworkAccess` | `resourceId` | Blob endpoint available. Keys are never listed and network policy is never changed. |
| Virtual network + 2 subnets | Yes | `vnetName`, `addressPrefix`, subnet names and prefixes | `agentSubnetResourceId`, `privateEndpointSubnetResourceId` | Two different subnets in the same VNet and region. Agent subnet /26 or larger, delegated to `Microsoft.App/environments`; private endpoint subnet /28 or larger, not delegated. RFC 1918 address space. Existing subnets are never updated. |
| Private endpoint: Foundry (`pe-foundry`) | Yes | default | `resourceId` | In the private endpoint subnet, targets the account, group `account`. |
| Private endpoint: Storage (`pe-storage`) | Yes | default | `resourceId` | In the private endpoint subnet, targets the storage account, group `blob`. |
| Private DNS zones: `privatelink.services.ai.azure.com`, `privatelink.openai.azure.com`, `privatelink.cognitiveservices.azure.com`, `privatelink.blob.core.windows.net` | Yes | default | `resourceId` per zone | Zone name must match. See DNS notes below. |
| Project connection `dataset-storage` | Yes | default | Reused automatically if compatible, or `connectionSelection.storage` | Same storage account, Entra ID (AAD) auth. |
| Role assignments for the project identity | Yes | Foundry User (formerly Azure AI User) on the account, Storage Blob Data Contributor on storage | Reused if already present | You need permission to create role assignments. |
| Agent network injection on the account | Yes | Set by the setup | Reused if it already matches | Account-wide change; requires `-AcknowledgeAccountWideImpact`. A conflicting existing injection stops the setup. |
| Account capability host | Yes | Created | Reused if compatible | Conflicting, failed or pending hosts stop the setup. |
| Project capability host | Optional (default on) | `workload.projectHost: requested` | Reused if compatible | Set `not-requested` to skip. |
| Application Insights | Optional | `name`, `publicNetworkAccessForIngestion`, `publicNetworkAccessForQuery` | `resourceId` | `mode: none` turns off all monitoring rows below. An existing component keeps its access policies. |
| Log Analytics workspace | With monitoring | `logAnalyticsWorkspace.name` | `logAnalyticsWorkspace.resourceId` (new Application Insights) | For an existing Application Insights, its linked workspace is used automatically. |
| Azure Monitor Private Link Scope (AMPLS) | With monitoring | default `ampls-<account name>` | `privateNetworking.monitorPrivateLink.resourceId` | Existing scope settings are not changed; Application Insights and workspace are associated if missing. |
| Private endpoint: Monitor (`pe-monitor`) | With monitoring | default | `resourceId` | In the private endpoint subnet, targets the AMPLS, group `azuremonitor`. |
| Private DNS zones: `privatelink.monitor.azure.com`, `privatelink.oms.opinsights.azure.com`, `privatelink.ods.opinsights.azure.com`, `privatelink.agentsvc.azure-automation.net` | With monitoring | default | `resourceId` per zone | As for the other zones. |
| Account connection `monitoring` | With monitoring | default | Reused if compatible, or `connectionSelection.monitoring` | Same Application Insights component. |
| Monitoring role assignments | With monitoring | Log Analytics Reader on Application Insights and its workspace | Reused if present | |

"default" means you can omit the entry and the setup creates it. To bring your own
private endpoint, DNS zone or AMPLS, add only that entry under `privateNetworking`:

```json
"privateNetworking": {
  "dnsZones": { "privatelink.blob.core.windows.net": { "mode": "existing", "resourceId": "<zone id>" } },
  "privateEndpoints": { "pe-storage": { "mode": "existing", "resourceId": "<private endpoint id>" } },
  "monitorPrivateLink": { "mode": "existing", "resourceId": "<AMPLS id>" }
}
```

### DNS and private endpoint notes

- A supplied DNS zone is only referenced. It must already be linked to the VNet,
  unless it is in the setup's resource group and you set `"linkVnet": true`.
  Zones in other resource groups (for example a central hub) must be linked by you.
- A supplied private endpoint is only referenced. Set `"addDnsZoneGroup": true` to
  let the setup add the DNS zone group, which works only when the endpoint is in the
  setup's resource group. Otherwise, make sure DNS records already exist.
- If anything you bring conflicts with what the setup needs (wrong target, subnet,
  group, region or connection settings), planning or preview stops. Nothing is
  overwritten to fit.

### Optional input fields

| Field | Default | Purpose |
|---|---|---|
| `workload.intent` | `trace` with monitoring, otherwise `non-trace` | `trace` requires monitoring. |
| `workload.routeGoal` | `direct-private` | `configuration-only` records that no private route is expected. |
| `workload.projectHost` | `requested` | `not-requested` skips the project capability host. |
| `connectionSelection.storage` / `.monitoring` | exact names `dataset-storage` / `monitoring` | Reuse an existing connection with another name (existing account/project only). |

## After setup

Setup only configures resources. To check the result without running an
evaluation, run the read-only [Foundry private network diagnostic](../foundry-private-diagnostic/README.md)
against the project. To prove runtime access, run an evaluation from a client that can
reach the private endpoints, such as a VM in the VNet or a peered network.
## What the setup does not do

- It does not create credentials, keys or SAS tokens, or lock down public access.
- It does not delete, repair or clean up resources.
- It does not run evaluations or prove runtime data access (see [After setup](#after-setup)).
- It does not migrate identities, customer-managed keys, models or multiple projects.

## Tests

Offline tests make no Azure calls. From this folder:

```powershell
pwsh -NoProfile -File .\tests\Test-Offline.ps1 -OutputDirectory (Join-Path $HOME 'foundry-setup-tests')
```