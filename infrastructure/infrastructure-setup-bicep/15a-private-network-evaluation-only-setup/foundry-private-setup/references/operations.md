# Setup commands and recovery

## Contents

Toolchain; plan and run; advanced per-node control; approvals/status; drift; timings and limits.

## Toolchain

Run from the extracted skill directory using `pwsh -NoProfile` with PowerShell 7.2+.
`assets\toolchain.json` records the known-tested Windows profile (PowerShell 7.6.7,
CLI-owned Python 3.14.7, Azure CLI 2.91.0, Bicep 0.42.1) for reproduction, **not**
exact customer version requirements. Compatible version differences are accepted.
The check loads required CLI commands/flags locally and records installed versions;
the selected bundled asset must compile using the installed Bicep.

```powershell
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Toolchain
```

Missing required capabilities stop with an actionable offline error. Have the operator
preinstall compatible tools using their approved offline mechanism; do not
download, pip-install, edit source, mutate global packages/profiles or copy auth caches.
CLI discovery uses the installed `az` launcher, preferring its own isolated Python
when the Windows MSI launcher is selected; a supported native launcher is the
fallback, not another global Python. Bicep is discovered on PATH, then in the usual
user-local Azure binary directory. Explicit supported paths can be selected in the
current process with `FOUNDRY_SETUP_AZURE_CLI` and `FOUNDRY_SETUP_BICEP`. No install
path or OS-version lock is imposed; the tested platform is Windows.
Native children use CLI-owned Python `-I -B` where available, scrub PYTHON*/PIP_* variables, disable
dynamic extension installation/version checks/telemetry and use no shell profiles.
Use the customer's existing AzureCloud login and matching active subscription. Helpers
never log in, switch subscription or grant additional operator access.

## Plan and run

Put customer files under `C:\work\setup`, outside the package. One input file holds
everything; `privateNetworking` is optional (see scenarios). Planning is local.

```powershell
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Plan -ConfigPath C:\work\setup\input.json -OutputPath C:\work\setup\plan.json
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Run -GraphPath C:\work\setup\plan.json -StateDirectory C:\work\setup\state -ApprovePlan <planHash>
# After explicit confirmation of the account-wide injection change:
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Run -GraphPath C:\work\setup\plan.json -StateDirectory C:\work\setup\state -ApprovePlan <planHash> -AcknowledgeAccountWideImpact
```

`Run` requires the exact `planHash` printed by `Plan`, records progress in
`run.json`, and binds the state directory to that plan. Each wave previews every
ready node (real what-if), stops before any write if a preview is not ready, then
applies with each node's own preview hash. If an apply is refused only because a
sibling in the same wave changed state its preview was bound to (NotSubmitted, nothing
written), the run takes one fresh preview of that node; repeated drift stops the run.
Run status values: `InProgress` (only while running), `Completed`,
`AwaitingAccountWideConfirmation`, `Stopped` (with `reason`). Rerunning resumes and
performs one read-only reconcile of any Running/OutcomeUnknown attempt; it never
replays a write. A changed plan needs a new state directory.

## Advanced per-node control

The same engine can be driven node by node with explicit approvals:

```powershell
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Preview -GraphPath C:\work\setup\plan.json -Nodes ResourceGroup -StateDirectory C:\work\setup\operations
```

Preview results give each exact `previewPath` and `approvalHash`. Build an approval
JSON **only for specifically authorized operations**, for example:

```json
{
  "ResourceGroup": {
    "planPath": "C:\\work\\setup\\operations\\ResourceGroup\\<operation-id>.preview.json",
    "approvalHash": "<exact-reviewed-hash>"
  }
}
```

```powershell
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Apply -GraphPath C:\work\setup\plan.json -Nodes ResourceGroup -ApprovalsPath C:\work\setup\approved.json -StateDirectory C:\work\setup\operations
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Preview -GraphPath C:\work\setup\plan.json -Nodes Network,Storage,Account -Concurrency 3 -StateDirectory C:\work\setup\operations
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Apply -GraphPath C:\work\setup\plan.json -Nodes Network,Storage,Account -Concurrency 3 -ApprovalsPath C:\work\setup\approved.json -StateDirectory C:\work\setup\operations
```
Each selection is explicit, concurrency is 1–3, and no agent/workflow is spawned.
Apply serializes overlapping write scopes (including shared PE subnet/DNS/Foundry
scopes). Preview/reconciliation are read-only. Do not run multiple competing apply processes with different state directories.
Unselected ancestors need no old global ledger, but current material prerequisites
must actually exist. A dependent resource cannot be previewed as if an unexecuted
parent preview had created it.

| Node | Actual ordered prerequisites |
|---|---|
| ResourceGroup | none; existing mode is GET/reference |
| Network, Storage, Account, optional Monitoring | RG; branches independent |
| Project | Succeeded account; existing paired mode GET/reference |
| FoundryConnectivity | account + network |
| StorageConnectivity | storage + network |
| MonitorConnectivity | monitoring's actual component/LAW + network |
| Connections | project + storage + optional monitoring |
| GrantAccount / GrantStorage / GrantInsights / GrantWorkspace | project + exact target |
| Injection | project/network, selected connectivity, connections and applicable grants |
| AccountHost | matching account injection |
| ProjectHost | explicit requested intent + matching Succeeded account host |

Generated node parameters use exact names/IDs; monitoring resolves actual linked LAW,
connections reuse compatible observed metadata, and monitor PE/DNS/AMPLS associations
stay together. Only selected node operations execute. A node blocked by a failed,
unknown or unsubmitted selected parent does not issue a write; independent nodes
may finish and retain their own results.

## Approvals and authoritative status

No `approved:true`, automatic public-access lockdown, BYO subnet PUT, migration or
implicit host operation. Each preview expires after two hours and binds package
hash (canonical `/` relative paths), config, exact request and material state.
The guide cannot grant permission merely by generating an approval hash.

```powershell
# Injection requires its own reviewed hash AND account-wide acknowledgment:
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Apply -GraphPath C:\work\setup\plan.json -Nodes Injection -ApprovalsPath C:\work\setup\approved.json -AcknowledgeAccountWideImpact -StateDirectory C:\work\setup\operations
# Exactly one bounded, read-only status reconciliation of selected attempts:
pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Reconcile -GraphPath C:\work\setup\plan.json -Nodes Storage -ApprovalsPath C:\work\setup\approved.json -StateDirectory C:\work\setup\operations
```

| State | Action |
|---|---|
| PreviewReady | review exact scope, then authorized Apply |
| NotSubmitted | terminal; inspect error/diff and issue a fresh scoped Preview. **No deployment polling**, no replay of that attempt |
| Running | request attributed to an actual running Azure deployment; bounded read-only Reconcile, never another create |
| Succeeded | authoritative setup result; no further polling required |
| Failed | confirmed failure, not success; inspect supported error/status evidence before a new deliberate action |
| OutcomeUnknown | possibly submitted; reconcile exact original request read-only. Missing deployment is not proof of non-submission |
| Blocked | material selected prerequisite not completed; no write attempted |

A fresh same-node Preview is refused while a prior Running, SubmissionAttempted or
OutcomeUnknown attempt remains unresolved. The refusal retains the prior state/ID
and original receipt/preview paths with `ReadOnlyReconcileOriginalAttempt` guidance;
it does not become a new NotSubmitted/fresh-preview loop. Terminal NotSubmitted
attempts do not impose this block and are never polled.

Azure GET `properties.parameters` uses `{type,value}` wrappers. Reconciliation compares
**values**, resolves literal template defaults when legitimately omitted, rejects
unknown/redacted/missing-required/changed values, and also checks unique name,
timestamp and correlation. It never accepts an old same-name deployment as a new
attempt. Bicep's generator hash is diagnostic provenance, **not** the provider's
deployment templateHash contract.

Attribution uses read-only native `deployment group export` and compares the full
deployed template with the approved template. Normalization removes only known Bicep
`_generator` compiler metadata at ARM template-document boundaries and normalizes
declared ARM parameter/output type casing, including nested deployment documents.
Resource definitions, values, array order and custom metadata remain significant.
An exact proof is cached per request/attempt/provider hash/correlation; subsequent
inconsistency is rejected rather than adopted, and normal polling does not repeatedly
export the same template.

Unavailable/unauthorized export or real content mismatch remains OutcomeUnknown with
a specific sanitized attribution cause and, for mismatch, expected/actual content
hashes. Templates/secret payloads are not printed or copied into receipts. Do not
ignore this guard or add permissions automatically. Reconcile the original request
read-only; no blind retry, grant-batch replay, resource adoption or arbitrary resume.

## Scoped drift

PE operations bind the selected target's material identity/access settings, subnet
ID/CIDR/delegation/policies, exact PE/DNS write paths and linked monitoring resources.
They report unrelated observed NSG/route/tag differences (for example policy-added
NSGs) without re-PUTing or adopting those resources. Network creation and
injection/host preservation retain stricter relevant settings. This is not an
ignore-all-NSG rule or a tag-based policy exemption.

There is no network wait window. If a material prerequisite changes between preview
and apply, apply stops NotSubmitted; rerun to take a fresh preview of current state.
Provider-returned fields that were not submitted (for example account `armFeatures`)
are reported, not treated as a failure.
## Separate measurements and limits

Receipts/node results separate parameter/local preparation,
PreviewWhatIf, SubmissionApply, DeploymentStatusVerification and Reconciliation.
UTC start/end timestamps accompany monotonic elapsed measurements. Azure's reported
ISO duration is recorded separately as `azureDurationMs`; if absent it is null,
never inferred from local preparation/polling time. SelectionWall is actual wall
time across parallel nodes; do not sum overlapping node clocks as deployment time.
Native processes are capped at 120 seconds; deployment/host status waits at 900
seconds within 1200-second node budgets. At a node deadline the executor stops its
local worker and inspects attempt receipts; a possibly submitted cloud write remains
unknown, not canceled or replayed.

Setup status does not prove data access, host internal routing metadata or actual
MT-VNet service route. No evaluation execution, readiness assessment, runtime checks,
client provisioning, automatic repair/cleanup, web lookup or source-editing recipe is
included. Stop at supported setup outcomes and report limitations.

First-release limits remain deliberately bounded: concurrency is 1–3 and budgets
are fixed; conservative shared-scope locks serialize PEs/grants; Storage/monitor
targets retain full relevant snapshots. With monitoring none, a
`privateNetworking.monitorPrivateLink` entry is rejected.

