---
name: foundry-private-setup
description: Set up private-network Microsoft Foundry infrastructure from one JSON input using preinstalled PowerShell, Azure CLI and Bicep. Use for new account/project setup, any supported bring-your-own resource, or a paired existing single-project retrofit. Plans locally, asks for one plan approval, runs dependency waves with per-node previews, and resumes safely. Setup only; no evaluation execution, client provisioning or runtime validation.
---

# Foundry private setup

Use this complete package as-is. Do not modify its source to make a setup pass.
Keep customer inputs, plans and state **outside** the package folder.

## Happy path

1. Copy the matching example from `assets` (`input.example.json`,
   `input.existing.example.json` or `input.no-monitoring.example.json`) and edit
   names/IDs. See [input contract](references/scenarios.md).
2. Check tools: `pwsh -NoProfile -File .\scripts\Setup.ps1 -Action Toolchain`.
3. Plan (local, no Azure calls):
   `Setup.ps1 -Action Plan -ConfigPath input.json -OutputPath plan.json`.
   Show the user the printed summary: every node, whether it creates or reuses,
   its write scopes, and the `planHash`.
4. After the user approves that plan, run it:
   `Setup.ps1 -Action Run -GraphPath plan.json -StateDirectory state -ApprovePlan <planHash>`.
5. The run stops at `AwaitingAccountWideConfirmation` before agent network injection,
   which changes the whole account. Get explicit user confirmation, then rerun the
   same command with `-AcknowledgeAccountWideImpact`.
6. If a run stops, report `status`/`reason`. Rerunning the same command resumes:
   it checks unresolved writes once (read-only) and never replays them.

Each node still runs a real what-if preview before its write; a material difference
from the plan stops the run before anything is written. Existing resources are only
referenced unless the input asks for a specific addition. Hosts are explicit plan
nodes. ARM `Succeeded` does not prove data access or the actual serving route.

Advanced, per-node control (`Preview`, `Apply`, `Reconcile`) is described in
[operations](references/operations.md).

**Out of scope:** automatic repair/cleanup, public-access lockdown, evaluation
execution, runtime validation and validation-client/VM provisioning. Do not add
these as troubleshooting steps.

This is an offline-tested setup candidate, not live qualification.
