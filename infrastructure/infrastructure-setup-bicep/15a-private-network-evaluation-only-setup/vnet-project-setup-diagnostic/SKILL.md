---
name: vnet-project-setup-diagnostic
description: "Assess existing Foundry VNet setup, RBAC, private DNS, and template15a configuration using customer ARM reads. Use for project setup diagnostics or validation WITHOUT running evaluations, inference, provisioning, or repair."
---

# Foundry VNet project setup diagnostic

Use PowerShell 7.2+ and the customer's existing login. Select
`-AuthenticationProvider AzurePowerShell` for a CLI-free path using installed
Az.Accounts 5.3.3+; authenticate separately with `Connect-AzAccount` as described
in the guide. `AzureCli` remains the default for existing invocations. Do not request Owner,
impersonate an identity, change the default subscription, or run an evaluation.
Reader on the project and its dependencies is normally sufficient; inaccessible
shared scopes produce **Unknown**, not missing resources or absent grants.

## Run

Read [the usage guide](usage.md) for prerequisites, copy-and-run commands,
parameter descriptions, jump-host guidance, and report troubleshooting.

Use the bundled entry point against an **existing** project:

```powershell
& .\scripts\Invoke-VNetProjectDiagnostics.ps1 `
  -AuthenticationProvider AzurePowerShell `
  -ProjectResourceId '/subscriptions/SUB/resourceGroups/RG/providers/Microsoft.CognitiveServices/accounts/ACCOUNT/projects/PROJECT' `
  -OutputDirectory .\diagnostic-report
```

Alternatively supply `-SubscriptionId`, `-ResourceGroup`, `-AccountName`, and
`-ProjectName`. Supply `-EvaluationCallerObjectId` only when the intended caller
is known and caller-specific checks are wanted. Omission is informational
`NotAssessed` coverage, not a required health check. Never substitute the operator.

Select `-Profiles Core,Models,Graders,Traces,Agent,Scheduled,Continuous` as needed
(Core is always included). Use `-StorageConnectionName`, `-ModelConnectionName`,
`-ModelDeploymentName`, and `-MonitoringConnectionName` to disambiguate dependencies.
Use `-ModelAuthentication ApiKey` only for an explicitly intended API-key path;
`Auto` uses connection metadata and does not fetch credentials. Scheduled and
Continuous select the project MI for this tool's configured-grant assessment; they
do not silently select tracing or models. Traces assesses the discovered project
MI's configured read grants separately from caller and connection credentials.
These are tool assessment choices, not verification of service execution identity. Private
monitoring query paths remain explicit `NotAssessed` coverage when not implemented;
unreadable required query-policy metadata still produces an actionable Unknown.
The assessment considers the App Insights component: resource-context grants can suffice
when allowed by workspace policy, so workspace grants are not universally required.
Add `-PrivilegedTraceContent` only when that access is required.

For local host observations, select `-Mode ConfigurationAndNetwork`. Run from the
customer's existing private connectivity; do not configure VPN, DNS, hosts files,
or invoke VM RunCommand. DNS, expected PE address mapping, TCP 443, and validated
TLS are independent findings. Outside/unknown VNet location can yield inconclusive
host observations, not proof that Azure DNS is broken. Keep recognized private-link
aliases as DNS evidence; probe TLS only with the discovered canonical service
hostname. Inspect `denyEvidence` for relevant and provably ignored deny assignments;
an extra conditional allow does not negate sufficient unconditional grants.
Basic network mode does not run optional DNS-only/route detail commands. Select
`-AdvancedNetworkDetails` for those; unsupported commands are informational
`NotAssessed`, while an attempted probe failure remains visible.

Neither provider installs tools, logs in, switches context or falls back to another
provider. AzurePowerShell captures an existing AzureCloud context for the selected
project subscription; it never discovers or invokes Azure CLI. Its token/HTTP
transport has bounded deadlines, disables redirects and projects metadata in process.

For the optional AzureCli provider, if `az.cmd` is broken, pass the executable and non-secret prefix explicitly from
PowerShell (not as a single shell command):

```powershell
& .\scripts\Invoke-VNetProjectDiagnostics.ps1 @projectArguments `
  -AuthenticationProvider AzureCli `
  -AzureCliExecutable 'C:\your-cli-install\python.exe' `
  -AzureCliPrefixArguments @('-IBm', 'azure.cli')
```

Do not put credentials in parameters. Only an empty prefix or the Python Azure
CLI module prefix is accepted. The script never logs raw CLI errors or resource
payloads. Keep metadata reports private.

## Interpret

Read `diagnostics.json` and `diagnostics.md` in the output directory; both use the
same schema-v2 check objects, classified as `Finding`, `Inventory`, or `Coverage`.
The console and report lead with grouped actionable findings and a separate
coverage summary; routine inventory is not a count of health probes.
Exit codes: **0** selected implemented checks passed, **1** proven required
configuration defect, **2** required evidence inconclusive, **3** invalid input or
bootstrap failure. Required unreadable evidence never counts as Passed.
Coverage gaps can coexist with exit 0; `NotAssessed` does not mean Passed.
Passed means selected implemented configuration/host checks, **not evaluation
verified, effective permissions certified, or the whole VNet healthy**.

Do not call setup-validation APIs: they are outside this tool's read-only allowlist. Never run
evals, sync_evals, model/agent calls, listKeys/listSecrets, deployment, role changes,
capability-host mutations, container warming, or data-plane probes. Remediation
text is advisory, not permission to execute a change.

Use [the requirement catalog](references/requirements.md) for public references,
scenario boundaries, assessment rules, and interpretation limitations. Service-side
execution and network paths, effective authorization, and
API-key validity are outside the customer ARM assessment.

## Offline development

Run `pwsh -NoProfile -File .\tests\Test-Diagnostics.ps1`. Synthetic fixtures cover
evaluation with monitoring, evaluation with private monitoring, and minimal
evaluation with custom DNS. They are not live inventories.
`-FixturePath` is an offline-only transport: neither auth provider nor network is invoked,
and reports are explicitly labelled fixtures. Never treat fixture results as live
qualification. No additional test framework is required.

Developer-only projection parity tests use `tests\Test-Projections.py` with Python
and JMESPath (an existing CLI-bundled Python can also supply it), passing
`projections.json` from the offline output directory. This is not a customer
prerequisite and does not log in or contact Azure. Synthetic HTTP handlers test the
Az.Accounts path offline; real-module checks inspect signatures only. Live provider
qualification must be reported separately.
