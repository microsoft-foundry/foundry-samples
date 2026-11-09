# Foundry private network diagnostic

When evaluations or agent runs fail on a Foundry project that uses your own virtual network, this tool checks
the setup end to end and tells you what's wrong, who can fix it, and what to do. It also saves an evidence
file you can send to Microsoft support, so support can see your setup without access to your network.

It only reads. It changes nothing in Azure.

## What it checks

The project and account, the agent subnet, private endpoints, private DNS, NSGs, routing (route tables,
peerings, Virtual WAN, NAT), Azure Firewall and other network appliances, the storage and Application Insights
connections, Azure Monitor private link, model connections, and role assignments. From the machine it runs on,
it resolves and connects to each endpoint the agent uses, including the Azure Monitor query hosts.
The full list is in [references/checks.md](references/checks.md).

## Before you start

- PowerShell 7.2 or later.
- Reader access to the project, its connected resources, and the network resources (VNet, NSGs, route tables,
  private DNS zones, firewalls). Without access, those checks show **Could not check**.
- Either the Az.Accounts module (`Install-Module Az.Accounts`), or an Azure VM whose managed identity has Reader.
- Best results: run it on a VM in the agent's virtual network, so the network tests take the same path as the agent.

## Run it

```powershell
Connect-AzAccount            # skip on an Azure VM that uses its managed identity
./scripts/Diagnose.ps1 -ProjectResourceId /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
```

It takes about a minute. The console lists problems first, then anything it couldn't check, and ends with the
output folder. By default that's a new `foundry-diagnostic-<UTC time>` folder in the current directory; use
`-OutputDirectory <path>` to choose another.

To read the report, open `report.md` from that folder in any Markdown viewer, for example:

```powershell
code ./foundry-diagnostic-<UTC time>/report.md   # VS Code: press Ctrl+Shift+V for the formatted view
```

## Results

Each check is **OK**, **Problem** (High, Medium or Low) or **Could not check**. A *Blocking* "could not check"
means a problem could be hiding there, usually because of missing read access.

The output folder has:

- `report.md`: problems, likely causes and next steps.
- `details.md`: every check and what it saw.
- `results.json`: the same, for tools.
- `evidence.json`: the data the checks used.

Exit code `0` means no problems, `1` problems, `2` important checks couldn't run, `3` an input or script error.

Run it from a VM in the agent's virtual network when you can. From any other machine (a laptop, a Cloud PC), the
Azure configuration checks still apply, but that machine's own DNS and connection tests are listed separately under
**From this machine** and don't count as problems.

## Sending results to support

Send `evidence.json` (and `report.md` if you like). It holds resource IDs, network settings, role assignments and
connection test results. It has no keys, tokens or connection strings. To replace your resource names with tokens
first, run with `-Mask`.

Support can re-run the checks on it with `./scripts/Diagnose.ps1 -EvidencePath ./evidence.json`.
