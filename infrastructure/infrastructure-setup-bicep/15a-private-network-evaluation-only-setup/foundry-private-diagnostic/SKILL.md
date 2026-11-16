---
name: foundry-private-diagnostic
description: "Read-only diagnostic for Foundry projects on a private network (BYO VNet). Use when evaluations or agent runs fail on a private-network project and you need to find whether DNS, private endpoints, NSGs, routing, firewalls, appliances, Monitor private link, storage or role assignments are the cause, or to collect evidence for support. Never changes Azure resources."
---

# Foundry private network diagnostic

Runs `scripts/Diagnose.ps1`. It reads the project's Azure configuration with REST calls, tests the network
path from the machine it runs on, and reports each finding as **OK**, **Problem** or **Could not check**.
It needs only PowerShell 7.2+. Azure CLI is not used.

## Guardrails

- Read-only. It sends GET requests to Azure Resource Manager and one Resource Graph query type (POST, read-only).
  It never creates, changes or deletes anything, and never starts an evaluation.
- Don't sign in for the user, change their subscription context, or ask for more than Reader access.
  Missing access gives **Could not check**, not a false Problem.
- Don't read token caches, connection strings or keys. The evidence file never contains secrets.
- Don't suggest fixes that the report doesn't support. A **Could not check** result is not a Problem.

## Run

1. Pick where to run it. For network results that match the agent, run on a VM in the agent's VNet
   (or a peered VNet that uses the same DNS and routes). Anywhere else, the Azure checks still run, and
   `runner.match` says how far the network results can be trusted.
2. Sign in. Either `Connect-AzAccount` (Az.Accounts module), or nothing at all on an Azure VM whose
   managed identity has Reader access. A signed-in Az session is used first.
3. Run:

   ```powershell
   ./scripts/Diagnose.ps1 -ProjectResourceId /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
   ```

   Or pass `-SubscriptionId -ResourceGroup -AccountName -ProjectName`.

| Parameter | Use |
|---|---|
| `-ConnectionName` | Check one project connection instead of all of them. |
| `-OutputDirectory` | Where to write the files. Default: `./foundry-diagnostic-<UTC time>`. |
| `-Mask` | Replace customer-chosen resource names with stable tokens before writing `evidence.json`. |
| `-EvidencePath` | Re-run the checks offline on a saved `evidence.json`. No sign-in or network needed. |

## Read the result

The console shows the problems first, then what couldn't be checked. Files written:

| File | What it is |
|---|---|
| `report.md` | Summary for people: problems, likely cause, who owns the fix, what to do. |
| `details.md` | Every result with what was seen. |
| `results.json` | The same results for tools. |
| `evidence.json` | Everything the checks read. Send this to support; it replays with `-EvidencePath`. |

Exit codes: `0` no problems, `1` problems found, `2` nothing failed but something important couldn't be checked,
`3` input or script error.

If this machine isn't confirmed on the agent network (for example a laptop or Cloud PC), its own DNS and connection
tests are shown under **From this machine** and marked `offPath` in `results.json`. They don't count as problems or
change the exit code, because they describe this machine's network rather than the agent's.

Results have a **layer** (Name, Route, Nsg, Firewall, Tls, Response, Access, Config) that says where on the path the
issue sits, and an **owner** (AzureAdmin, NetworkTeam, ResourceOwner, Customer) that says who can fix it.
Start with High problems, then Blocking gaps. See [references/checks.md](references/checks.md) for every check and
[references/evidence-model.md](references/evidence-model.md) for the evidence format.

## Working on the diagnostic

Offline tests, no Azure access needed:

```powershell
pwsh -NoProfile -File tests/Test-Checks.ps1
pwsh -NoProfile -File tests/Test-Collect.ps1
pwsh -NoProfile -File tests/Test-Report.ps1
```

Checks read only `evidence.json`. A new check adds the reads it needs to the collector allowlist
(`scripts/collect/Requests.ps1`), documents them in `references/evidence-model.md`, and adds scenarios under
`tests/scenarios/`.
