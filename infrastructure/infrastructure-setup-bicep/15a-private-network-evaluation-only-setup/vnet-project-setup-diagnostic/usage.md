# Using the VNet project setup diagnostic

Inspect an existing Foundry VNet project without running an evaluation or changing
Azure resources. Run the script directly; Copilot is not required.

## Contents

- [Files and prerequisites](#files-and-prerequisites)
- [Quick start](#quick-start)
- [Select additional checks](#select-additional-checks)
- [Run from an existing jump host](#run-from-an-existing-jump-host)
- [Parameters](#parameters)
- [Read the output](#read-the-output)
- [Troubleshooting and limits](#troubleshooting-and-limits)

## Files and prerequisites

When this diagnostic is included with template 15a, open the diagnostic bundle
directory containing this `usage.md`. The entry point is relative to that directory:

```text
scripts\Invoke-VNetProjectDiagnostics.ps1
```

Keep the **whole diagnostic bundle directory** when copying it to another machine. The entry
point loads sibling helper scripts and `references\requirements.json`; copying
only the entry-point file will not work. No Copilot installation or particular
repository location is required.

Prepare:

- PowerShell **7.2 or newer**, not Windows PowerShell 5.1.
- **Az.Accounts 5.3.3 or later** for the AzurePowerShell provider, with an existing
  authorized Azure PowerShell login. Azure CLI is not required for this path.
  Version 5.3.3 is the locally inspected command-contract baseline and the
  deliberately enforced prerequisite, not a claim about the earliest compatible
  release. Older versions are not qualified. Azure CLI remains an optional provider.
- An existing Foundry account/project ARM ID, or its subscription, resource group,
  account name, and project name.
- Reader or equivalent read permissions on the resources to inspect. Include
  other resource groups containing shared DNS, networks, storage, or monitoring
  dependencies. Owner and RBAC Administrator are not diagnostic prerequisites.

This version supports **AzureCloud**. Other Azure clouds are explicitly rejected.
The script does not install tools, sign in, change the default subscription, or
grant permissions. Establish prerequisites separately with appropriate approval.

This is **CLI-free**, not dependency-free. Establish the Az.Accounts installation
separately if needed; the diagnostic never installs modules.
The login identity reads configuration. It is **not** automatically treated as
the project managed identity or the intended evaluation caller.

## Quick start

Run these examples in a **PowerShell 7 session**, starting from the directory
containing this `usage.md`.
Replace the example identifiers with your existing resources.

Sign in separately as the intended customer identity and explicitly choose the
tenant and project subscription. This is a prerequisite, not a diagnostic action:

```powershell
Import-Module Az.Accounts -MinimumVersion 5.3.3
Connect-AzAccount -Tenant '<tenant-guid>' -Subscription '<subscription-guid>' `
    -Environment AzureCloud -Scope Process
```

The diagnostic captures that AzureCloud context once and requires its subscription
to match the project. It passes the captured context explicitly for ARM token
acquisition; it does not switch identity/subscription, prompt for credentials,
sign in, or fall back to Azure CLI on failure.

```powershell
$script = '.\scripts\Invoke-VNetProjectDiagnostics.ps1'
$project = @{
    SubscriptionId = '<subscription-guid>'
    ResourceGroup  = '<resource-group>'
    AccountName    = '<foundry-account>'
    ProjectName    = '<project>'
}

& $script @project `
    -AuthenticationProvider AzurePowerShell `
    -Mode Configuration `
    -OutputDirectory '.\reports\configuration'
$LASTEXITCODE
```

This runs the default **Core** profile: account/project state and identities,
capability-host metadata, project-asset and Blob configured grants, storage,
network injection/subnets, private endpoints, and private DNS configuration.

Alternatively, supply the full project ARM ID instead of the four individual
resource parameters. Do not mix the two forms.

```powershell
& $script `
    -AuthenticationProvider AzurePowerShell `
    -ProjectResourceId '/subscriptions/<subscription-guid>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>' `
    -OutputDirectory '.\reports\configuration'
```

Add local DNS, address-mapping, TCP 443, and TLS observations with:

```powershell
& $script @project `
    -AuthenticationProvider AzurePowerShell `
    -Mode ConfigurationAndNetwork `
    -OutputDirectory '.\reports\network'
```

Run network mode from a machine with the customer's existing private connectivity.
An outside-VNet machine may resolve public addresses even when the private DNS
configuration is correct. The report keeps that observation inconclusive.
Optional DNS-only/CNAME and selected-route detail commands run only with
`-AdvancedNetworkDetails`; they are not necessary for the basic network checks.

## Select additional checks

Core is always included. Select only scenarios relevant to the project:

| Profile | Additional assessment |
|---|---|
| `Models`, `Graders` | Connection target/authentication, model deployment metadata, and API-key policy or intended Entra configured grants. No keys or inference requests. |
| `Traces` | App Insights connection/component/backing workspace, private-query policy, and configured read grants for the project MI selected by this tool. No log queries. |
| `Scheduled`, `Continuous` | Project-MI identity selection for applicable checks. Does not create schedules/rules or automatically enable model/trace profiles. |
| `Agent` | Discoverable agent dependency metadata. Full agent authorization/topology remains explicitly incomplete. |

For a model/grader connection, pass its **connection name**, not a secret:

```powershell
& $script @project `
    -AuthenticationProvider AzurePowerShell `
    -Profiles @('Core', 'Models', 'Graders') `
    -ModelConnectionName '<connection-name>' `
    -ModelDeploymentName '<deployment-name>' `
    -ModelAuthentication Auto `
    -OutputDirectory '.\reports\models'
```

For trace dependencies:

```powershell
& $script @project `
    -AuthenticationProvider AzurePowerShell `
    -Profiles @('Core', 'Traces') `
    -MonitoringConnectionName '<monitoring-connection-name>' `
    -Mode ConfigurationAndNetwork `
    -OutputDirectory '.\reports\traces'
```

Omit a connection selector when discovery is unambiguous. Connection aliases are
resolved to actual resource IDs; they are not assumed to be Azure resource names.
Template 15a does not require Search/Cosmos/ACR for Core. An older template without
monitoring is not invalidated by Core; selecting Traces exposes that coverage gap.

Supply `-EvaluationCallerObjectId '<object-guid>'` only when that intended caller
is known and caller-specific assessment is wanted. Without it, caller access is
`NotAssessed` informational coverage and does not make Core inconclusive. With it,
unreadable/incomplete required caller grants remain Unknown and can return exit 2.
This assesses role metadata; it does not run anything as that principal.
Do not substitute the jump-host identity merely to eliminate a coverage note.
For trace-read configuration checks, this tool selects the discovered **project
MI**, independently of this caller parameter and of monitoring ingestion
credentials. It does not verify the actual identity used by a service operation.
When workspace policy explicitly permits resource-context permissions and the
component grant passes without deny uncertainty, workspace RBAC alternative reads
are skipped. The report records Inventory/NotApplicable, not a warning or a
fabricated workspace pass. Otherwise the fallback assessment still runs.

## Run from an existing jump host

1. Confirm the host is attached to the intended VNet or established private path.
2. Copy the complete diagnostic bundle directory using an approved transfer mechanism.
3. Ensure PowerShell and Az.Accounts (or the selected Azure CLI alternative) are
   available. Obtain approval before installing
   missing tools; do not modify shared tool installations or another user's login.
4. Use an existing authorized login. For the CLI-free path on a host supporting
   managed identity, explicitly sign in as the approved system-assigned identity
   using `Connect-AzAccount -Identity -Subscription '<subscription-guid>' -Scope Process`
   before diagnosis. For the CLI alternative, use the intended existing CLI login
   (`az login --identity` only when that identity is intended).
   Never copy a user's bearer token onto the VM or use an
   unrelated attached identity to bypass denied access.
5. Run the entry point with `-AuthenticationProvider AzurePowerShell -Mode ConfigurationAndNetwork`
   (or explicitly select `AzureCli` when using CLI credentials).
6. Retain both report files and the exit code, recording the execution host and
   identity. Keep reports from different attempts separate.

VM execution and any prerequisite Reader assignment require separate operator
authorization; the diagnostic never performs them. Account-only roles on the VM
do not necessarily permit reading the surrounding VNet, DNS, storage, or RBAC.
RG Reader does not guarantee visibility into subscription/management-group or
cross-resource-group metadata.

Windows and Linux can perform basic DNS, TCP, and TLS checks. In this version,
optional DNS-only/CNAME and selected-route observations rely on Windows commands;
they are disabled by default. With `-AdvancedNetworkDetails`, missing commands on
Linux are `NotAssessed`/Info, not project-health warnings. A supported command that
fails or times out remains explicitly Unknown (optional, nonblocking), distinct
from unsupported functionality. Collected host interfaces/resolvers are informational
inventory, not a warning merely because the tool cannot prove VNet membership.
Private-link aliases are DNS evidence, not separate
TLS targets: the original service hostname is used for certificate validation.

## Parameters

| Parameter | Meaning/default |
|---|---|
| `ProjectResourceId` | Full Foundry project ARM ID; alternative to the four resource parameters. |
| `SubscriptionId`, `ResourceGroup`, `AccountName`, `ProjectName` | Identify the existing target explicitly. |
| `Profiles` | Array of selected profiles; default `Core`. |
| `Mode` | `Configuration` by default; optionally `ConfigurationAndNetwork`. |
| `AuthenticationProvider` | `AzurePowerShell` for installed Az.Accounts and a captured customer context; no CLI dependency. `AzureCli` remains the default for backward compatibility. No automatic fallback. |
| `AdvancedNetworkDetails` | Optional DNS-only/CNAME and selected-route details. Requires `ConfigurationAndNetwork`; unsupported commands are informational `NotAssessed`. |
| `EvaluationCallerObjectId` | Optional known evaluation-caller object ID. Omitted means caller access is not assessed, not a required Unknown. Supplied caller checks remain required. |
| `StorageConnectionName`, `ModelConnectionName`, `MonitoringConnectionName` | Disambiguate discovered dependencies using connection aliases. |
| `ModelDeploymentName` | Select the existing deployment to inspect. |
| `ModelAuthentication` | `Auto`, `ApiKey`, or `Entra`; default `Auto` uses connection metadata. |
| `PrivilegedTraceContent` | Select additional privileged-content coverage reporting; requires `Traces`. Does not read content or certify runtime access. |
| `OutputDirectory` | Local report directory; default `vnet-project-diagnostic-report` under the current directory. Use a new directory to preserve previous results. |
| `RequestTimeoutSeconds` | Per-attempt deadline including token acquisition and HTTP for AzurePowerShell, or CLI subprocess startup/read. Default 25 seconds, allowed 5-120; up to three attempts for 429/503/504 only. |
| `AzureCliExecutable` | AzureCli provider only: executable name/path; default `az`. Do not supply with live AzurePowerShell runs. |
| `AzureCliPrefixArguments` | AzureCli provider only: empty by default; supported override `@('-IBm', 'azure.cli')` for an existing CLI Python installation. |
| `FixturePath` | Offline development only, with `Configuration` mode. Invokes neither auth provider nor network; not live qualification. |

### Optional original Azure CLI path

Existing commands without `AuthenticationProvider` retain their Azure CLI behavior.
To select it explicitly, with a pre-existing customer CLI login:

```powershell
& $script @project -AuthenticationProvider AzureCli `
    -OutputDirectory '.\reports\cli-configuration'
```

If that provider's normal Windows CLI launcher is broken, use the existing CLI installation's
Python executable. This is not a command string and must not contain credentials:

```powershell
& $script @project `
    -AuthenticationProvider AzureCli `
    -AzureCliExecutable 'C:\path-to-existing-azure-cli\python.exe' `
    -AzureCliPrefixArguments @('-IBm', 'azure.cli') `
    -OutputDirectory '.\reports\configuration'
```

## Read the output

The console prints an implemented-check result, explicit coverage summary,
grouped actionable findings when present, and two file paths, for example:

```text
Passed for selected implemented checks; findings=33; passed=33; exit=0. No evaluation was run.
Coverage: Incomplete; not assessed: coverage.runtime, rbac.assets.evaluationCaller. Inventory=4.
JSON: <output-directory>\diagnostics.json
Report: <output-directory>\diagnostics.md
```

This is an illustrative shape, not a fixed count. Inventory and coverage do not
inflate finding counts. Repeated NSG/UDR observations with the same check ID,
resource and principal are deduplicated; actual errors remain in the details and
grouped actionable summary. A private project can pass all implemented checks
while clearly retaining incomplete tool coverage.

- `diagnostics.json` contains the structured assessment and check objects.
- `diagnostics.md` contains the readable evidence, limitations, and guidance.

Each check identifies its principal/resource, whether it is required, expected
condition, observed evidence, status, collection time, and limitations.
`Configuration` and `ObservedNetwork` evidence are distinguished.
Schema **2** adds `classification` and the statuses `Observed` and `NotAssessed`:

| Classification | Meaning |
|---|---|
| `Finding` | Implemented configuration/connectivity assessment. Required Failed/Unknown findings determine exits 1/2. |
| `Inventory` | Resource/host metadata, normally `Observed`/Info. Not proof of health; read/probe errors retain their status and appear in the actionable summary. |
| `Coverage` | Unselected or unimplemented assessment, normally `NotAssessed`/Info. Nonblocking, never a substitute for a passing prerequisite. |

`summary` reports `findingCount`, `passedFindingCount`, `inventoryCount`,
`coverageStatus`, `notAssessedCount`, `notAssessed`, and `actionableGroups` alongside
`status`/`exitCode`. Markdown separates actionable summary, finding details,
coverage, and inventory. Consumers of earlier reports must check `schemaVersion`;
historical reports are not rewritten or reinterpreted as schema 2.
`authenticationProvider` identifies `AzurePowerShell`, `AzureCli`, or `OfflineFixture`.
No account credential, profile object, or bearer token is included in reports.

| Exit | Meaning |
|---:|---|
| `0` | Required selected **implemented** checks passed. Coverage can still be incomplete; no whole-VNet, effective-permission or evaluation verification is claimed. |
| `1` | At least one required selected check has a proven configuration failure. |
| `2` | Required evidence is inconclusive. This is a diagnostic outcome, not a script crash. |
| `3` | Input, bootstrap, assessment, or local report-writing error; inspect the reported stage/source. |

A required Finding Unknown makes the result Inconclusive unless a required
failure already determines the outcome. Actual required resource/RBAC/DNS 403s,
timeouts, missing required metadata and inconclusive network paths remain visible.
Optional errors do not alone force failure. Unsupported probes and unimplemented
private-monitoring/agent/privileged-policy coverage do not manufacture health
warnings. Remediation text is guidance, not an action the script took.

## Troubleshooting and limits

| Observation | Interpretation/action |
|---|---|
| AzurePowerShell prerequisite error | Verify installed Az.Accounts and establish the intended AzureCloud context separately. No auto-login, context switch or CLI fallback is attempted. |
| ARM/token status 401 | The captured identity could not supply valid authorization. Re-establish the intended login separately; do not bypass using another identity. |
| Caller access is NotAssessed | Optional caller was omitted. Supply it only if that assessment is wanted; do not assume the operator or VM identity is the caller. |
| Explicit caller check is Unknown | Actual selected caller evidence is insufficient; it remains a required finding, not an optional coverage note. |
| Resource read is 403 | The diagnostic identity could not read that metadata. Check its identity and precise scope; do not infer the project MI lacks runtime permissions or automatically grant broader roles. |
| Ancestor role read is 408 | The bounded authentication/read attempt timed out. This is not proof of absent assignments. A larger bounded timeout may help; retain visibility limitations. |
| DNS resolves public IPs | Check execution location, resolver, and expected PE mappings. Do not enable public access as a workaround. |
| DNS succeeds but TCP/TLS fails | These are separate host/path observations. Check routing and certificate/hostname evidence; never disable certificate verification. |
| Private monitoring path is NotAssessed | This is an explicit implementation limit, not evidence of broken configuration. AMPLS association metadata does not prove AMPLS/DNS/query reachability. Missing actual query-policy metadata remains a separate required Unknown. |
| DNS-server list is empty | On a successfully read VNet, missing/null/empty DNS-server lists mean Azure-provided DNS, not custom DNS. Unreadable VNet metadata remains Unknown. |
| Expected DNS record IPs are unavailable | The diagnostic uses exact PE FQDN-to-NIC evidence, or the sole address of a single-address PE. It never assigns every multi-host NIC IP to one hostname. Insufficient mapping or additional potentially valid PE addresses remain Unknown; proven missing/contradictory expected addresses still fail. |
| Role assignment exists but result is Unknown | Conditions, potential denies, group/PIM visibility, access policy, or unreadable scopes can prevent a conclusion. Assignment existence alone does not prove effective access. |

The script does not validate NSG/NVA behavior end-to-end, mint target-identity
tokens, query customer data, retrieve or test API keys, write/delete blobs or
datasets, call setup-validation/evaluation APIs, warm containers, change DNS/RBAC,
or certify service-side execution and network paths. Public-network access
disabled is normal for a private setup. Service-managed runtime resources are
outside the diagnostic's coverage.

Treat reports as private resource metadata. Do not publish them publicly or add
credentials to parameters, fixtures, or reports. See [requirements.md](references/requirements.md)
for public references, the check catalog, and detailed certainty boundaries.

AzurePowerShell uses controlled HTTPS GETs with redirects disabled and per-page
ARM host/path/version validation. Tokens remain transient in memory, including
current Az.Accounts SecureString output. Payloads are projected to allowlisted
metadata before caching; errors never print raw response bodies. Both providers
share one diagnostic engine and report model.
