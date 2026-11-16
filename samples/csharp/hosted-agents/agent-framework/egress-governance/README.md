# Govern hosted-agent network egress with Azure Policy (C#)

Assign the published built-ins, then see the difference between rejecting a
network guardrail save and rejecting a hosted-agent version. This is the C#
Agent Framework sample. The host returns a fixed response without calling a model
or an external service. Governance is enforced by Foundry and Azure Policy, not by
the host's code.

## How it works

| Boundary | What is checked | Deny result |
| --- | --- | --- |
| Control plane | Network egress settings when a Responsible AI (RAI) policy resource is saved | `403 RequestDisallowedByPolicy` |
| Data plane | The guardrail referenced by a new hosted-agent version, including missing egress settings or attachment | `403 agent_policy_denied` |
| Runtime | Outbound requests made by a running hosted agent | Separate from this sample; see the [runtime sample](../egress-control/) |

The admin helper uses the same three parameters for separate built-in assignments.
Enter permitted destinations, denied destinations, and allowed rule actions once in
[`parameters.json`](parameters.json), before running `init`. The state file freezes
those values for the run, including later Audit-to-Deny changes. The helper does not create custom definitions,
copy built-in rule bodies, or require custom data-plane definition allowlisting.

| Member | Built-in definition ID | Included |
| --- | --- | --- |
| Control-plane baseline and source endpoints | `0cfd954d-079f-447f-91bf-89889e9d1de0` | Baseline and Full |
| Control-plane rewrite destinations | `64a15c51-9797-4d6b-93a5-16b19e7de23b` | Full |
| Control-plane header/credential safety | `29be091c-88f9-419b-8ad9-82ce5dc452d3` | Full |
| Combined hosted-agent data-plane checks | `d279dbb1-e60e-4ca0-8c2f-cc7a0f46166b` | Baseline and Full |

Full adds earlier rewrite and header validation at guardrail save time.
**Both profiles use the same combined data-plane policy**, including its rewrite
and credential checks. These profiles are sample conveniences, not published
initiatives. Assignments reference `/providers/Microsoft.Authorization/policyDefinitions/<ID>`.

## Prerequisites

- .NET 10 SDK for the C# host, Python 3.10+ for the standard-library-only admin
  helper, and Azure CLI signed in with `az login`. The helper and parameters are
  identical to the Python counterpart; only the hosted image differs.
- `azd` 1.27.1+ with the Foundry extension (`azd ext install microsoft.foundry`),
  or VS Code with Foundry Toolkit.
- A **dedicated disposable public-Azure Foundry account and project**.
  The governance preview is supported in Canada Central, Spain Central, and Korea
  Central. Catalog publication does not establish service-feature availability.
- Administrator permission to assign Azure Policy at the account, such as Resource
  Policy Contributor. Developer permission to manage RAI policies and hosted agents.
  Contributor alone does not grant assignment-write access. No assignment managed
  identity, new role assignment, Key Vault, or actual credential is needed.
- A digest-pinned image built from this sample, accessible to the project. Build
  with your normal hosted-agent deployment flow or the Dockerfile below.

> Account-scoped assignments affect **every applicable resource and project on that
> account**, not just the names created here. Do not run this on a shared account.
> Inherited assignments still apply and are not disabled by this sample. Keep the
> state file until cleanup finishes. An interrupted or unexpectedly successful
> negative test can leave resources that still need cleanup.

## Prepare the probe host

Run from this directory in a repository checkout. No model deployment is needed.

```bash
azd auth login
azd provision
```

Select or create the dedicated project. Do this before assigning Deny: provisioning
or deploying an unguarded agent afterward may itself be rejected.

Build and push `src/egress-governance/Dockerfile` to a registry the project can
pull from, using your existing hosted-agent image-build workflow. For an existing
Azure Container Registry:

```bash
az acr build --registry "<registry-name>" \
  --image egress-governance:v1 src/egress-governance
az acr repository show --name "<registry-name>" \
  --image egress-governance:v1 --query digest --output tsv
```

Use the returned digest in `AGENT_IMAGE` below. The helper registers new versions
directly so that accepted and rejected requests are visible without starting a
session. It never invokes the agent or tests token retrieval.

For an optional local host check:

```bash
cd src/egress-governance
dotnet run
```

Alternatively, run `azd ai agent run` from the sample root. In another terminal,
run `azd ai agent invoke --local "Check the governance probe."`. In VS Code, use
Foundry Toolkit to run the sample and Agent Inspector to send the same message.
Expected text: `Governance sample ready.` A local response proves only the host
works, not that any Azure Policy assignment is being evaluated.

## 1. Administrator: select the target and assign Audit

The commands use Bash. In PowerShell, set the same variables with
`$env:NAME = "value"` and reference them with `$env:NAME`.

```bash
export ACCOUNT_ID="/subscriptions/<subscription>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"
export PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AGENT_IMAGE="<registry>.azurecr.io/egress-governance@sha256:<digest>"

python governance.py init --account-id "$ACCOUNT_ID" --project-endpoint "$PROJECT_ENDPOINT"
python governance.py assign --confirm-account "$ACCOUNT_ID" --profile baseline --effect Audit
```

`init` reads all four public definitions and checks account/project access.
`assign` writes only uniquely named account-scoped assignments. The helper stores
their ownership and the shared parameters in `.egress-governance.json`.

The example permits `httpbin.org/get` and `httpbin.org/headers`, excludes
`unapproved.example.com`, and permits all four rule actions. A rule action named
Deny is not the Azure Policy Deny effect.

## 2. Developer: create the fixtures under Audit

```bash
python governance.py guardrail --fixture good --expect allowed
python governance.py guardrail --fixture no-egress --expect allowed
python governance.py guardrail --fixture bad-source --expect allowed
python governance.py agent --fixture none --image "$AGENT_IMAGE" --expect allowed
```

Audit does not block these writes. After assignment propagation, use
**Azure portal > Policy > Compliance** to inspect the assignments and available
resource/component details. The bad source and unguarded hosted version should be
noncompliant. Reporting is asynchronous: a successful write, empty result set, or
zero-resource summary is not proof of successful Audit evaluation.

## 3. Administrator: switch to Deny, then test both boundaries

```bash
python governance.py assign --confirm-account "$ACCOUNT_ID" --profile baseline --effect Deny
```

Allow **30-60 minutes** for data-plane assignment changes to propagate. Control-plane
assignment changes also take time. Neither waiting nor an assignment GET proves
enforcement; the expected attributed denial is the check. The helper fails rather
than silently retrying an unexpectedly allowed negative case. Inspect the result
and propagation before rerunning. Use `cleanup` if abandoning the run.

```bash
# Saving an approved guardrail succeeds; an unapproved source update is denied.
python governance.py guardrail --fixture good --expect allowed
python governance.py guardrail --fixture bad-source --expect denied --member baseline

# No egress settings still passes the CP checks. DP closes that gap.
python governance.py guardrail --fixture no-egress --expect allowed
python governance.py agent --fixture none --image "$AGENT_IMAGE" --expect denied
python governance.py agent --fixture no-egress --image "$AGENT_IMAGE" --expect denied
python governance.py agent --fixture good --image "$AGENT_IMAGE" --expect allowed
```

Expected denials must identify this run's assignment and the intended built-in.
A generic 403, authentication error, invalid image, or sandbox provisioning error
is not a successful policy test. Every agent command uses a new name, preventing
an identical-version response from masquerading as a fresh admission decision.
The guardrail helper also checks that a denied update preserves the stored resource.

## 4. Optional: add rewrite and header save-time checks

First, while still using Baseline:

```bash
# CP baseline accepts these source endpoints, but DP rejects their unsafe settings.
python governance.py guardrail --fixture bad-rewrite --expect allowed
python governance.py guardrail --fixture bad-headers --expect allowed
python governance.py agent --fixture bad-rewrite --image "$AGENT_IMAGE" --expect denied
python governance.py agent --fixture bad-headers --image "$AGENT_IMAGE" --expect denied

python governance.py assign --confirm-account "$ACCOUNT_ID" --profile full --effect Deny
```

After the new control-plane assignments propagate:

```bash
python governance.py guardrail --fixture bad-rewrite --expect denied --member rewrite
python governance.py guardrail --fixture bad-headers --expect denied --member headers
```

The first fixture rewrites an approved source to an unapproved destination.
The second uses an approved destination but explicitly selects HTTP for a Rewrite
that injects a managed-identity header. Its reference contains a target resource;
no token is acquired and no real credential is supplied. These examples isolate
the two additional CP checks instead of relying on an unrelated source violation.

## Cleanup

```bash
python governance.py cleanup
```

Cleanup removes this run's assignments first, then its agent and guardrail
resources, verifying absence. It does not delete built-ins, account, project,
registry, or other agents. Keep the state file and rerun cleanup if any deletion
fails. No sessions are started here; if you started one manually, stop it before
deleting the agent. Separately remove infrastructure you created for this sample
through its original deployment environment, after checking ownership.

## Troubleshooting and limits

- Azure Policy `effect` (Audit/Deny/Disabled), assignment `enforcementMode`
  (Default/DoNotEnforce), and guardrail runtime mode (Enforced/Audit) are independent.
  This helper keeps assignment enforcement enabled. Assignment Audit does not
  change the guardrail's runtime mode.
- Empty permitted destinations means no traffic-permitting scopes, not unrestricted
  traffic. Each destination list supports at most 100 entries. Use host, host/path,
  or host/path/* without scheme, port, query, or fragment. `*.contoso.com` includes
  the apex and subdomains.
- CP path checks ignore case; DP permitted paths are case-sensitive. Denied overlap
  checks ignore case. A broad permitting scope overlapping a denied subtree fails
  even if a separate runtime Deny rule covers that subtree.
- Assignments do not create or attach guardrails, change runtime rules, or revoke
  existing sessions. Compliant runtime mode is Enforced with default Deny.
- The cloud `test-spec.yml` covers only the model-free host response. The opt-in
  admin/developer walkthrough above is separate evidence; the shared host runner
  does not assign policies or certify these denial scenarios.

## Next steps

- [Runtime egress controls](../egress-control/)
- [Govern hosted-agent egress with Azure Policy](https://learn.microsoft.com/azure/foundry/agents/how-to/govern-hosted-agent-egress-azure-policy)
- [Python counterpart](../../../../python/hosted-agents/agent-framework/responses/26-egress-governance/)
