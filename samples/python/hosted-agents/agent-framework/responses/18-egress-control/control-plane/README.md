# Administrator egress guardrails with Azure Policy (control plane)

An administrator permits the exact hostname `httpbin.org`. A developer tries to save an RAI
egress policy that allows `example.com/get`. **Azure Resource Manager rejects
that RAI-policy write with `RequestDisallowedByPolicy`.** No hosted agent or
outbound network request is needed to demonstrate this.

[`policy-definition.json`](policy-definition.json) is a **small teaching
example**, not the full egress-governance definition or a published built-in.
It demonstrates three checks when an RAI policy has an egress section:

1. Runtime mode must be `Enforced` and default action must be `Deny`.
2. Rules must use `Fqdn` and action `Allow` or `Deny`.
3. Each Allow rule must name an administrator-approved exact host.

Transform, Rewrite, unknown actions and wildcard Allow hosts are rejected
rather than left as ways around the hostname check. A Deny rule may restrict
any host. **Paths, credential references and advanced egress patterns are not
governed by this example.** Standalone RAI policies without egress remain allowed.

## Two different policies

| Artifact | Author | Purpose |
|---|---|---|
| Azure Policy definition and assignment | Administrator | Restrict which RAI egress configurations may be saved within the assignment scope. |
| RAI policy (`Microsoft.CognitiveServices/accounts/raiPolicies`) | Developer | Describe the outbound traffic rules used when a hosted agent is bound to that RAI policy. |

Three independent settings use similar enforcement terminology:

| Setting | Purpose |
|---|---|
| Azure Policy definition `effect` | Chooses what the definition does when its rule matches, such as `Deny`, `Audit` or `Disabled`. |
| Azure Policy assignment `enforcementMode` | Controls whether Azure applies the selected effect. `Default` applies it; `DoNotEnforce` evaluates compliance without applying it. |
| RAI `egressPolicy.mode` | Controls runtime egress behavior after an RAI policy is attached to a hosted agent. It does not control whether ARM accepts the RAI-policy resource. |

For this definition, the important assignment combinations are:

| Definition effect | Assignment enforcement mode | Result for a noncompliant RAI-policy write |
|---|---|---|
| `Deny` | `Default` | ARM rejects the create or update with `RequestDisallowedByPolicy`. |
| `Deny` | `DoNotEnforce` | ARM allows the write. Azure Policy can still report the resource as noncompliant, but it does not apply the deny effect or write a deny event to the Activity Log. |
| `Audit` | `Default` | ARM allows the write and applies the audit effect. |
| `Disabled` | `Default` | The definition's checks are disabled. |

The steps below test **ARM create/update enforcement only**. They do not test
APES, enforce hosted-agent attachment, govern inline agent egress settings, or
revoke traffic for already-running agents. The parent sample's `azd` deployment
and runtime probes are separate. Reading an existing RAI policy or successfully
creating a hosted agent does not prove Azure Policy enforcement.

## Prerequisites and scope

- Bash, OpenSSL (for unique test names),
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), and
  [jq](https://jqlang.org/download/). The same commands work for the Python and
  .NET samples; neither runtime, a model deployment, nor `azd` is needed here.
- A **disposable Foundry account** in a test subscription supporting RAI egress
  with API version `2026-09-01`. Use an account you own, not a shared account.
  This walkthrough does not create or delete the account.
- Administrator permission to create a subscription-level custom definition and
  an account-scoped assignment, for example Resource Policy Contributor at the
  appropriate scopes. Contributor alone does not grant policy assignment
  permission. No assignment managed identity or role assignment is needed for
  Audit/Deny.
- Developer permission to read/write/delete the account's RAI policies.
- Custom **control-plane** definitions do not need the custom data-plane
  allowlisting used by APES.

> Assigning this definition to an account affects **all applicable RAI-policy
> writes on that account**, not only the two names used below. Do not run the
> parent sample's policy catalog or runtime scenario suite on this account while
> the assignment is active: some catalog entries intentionally violate these
> administrator restrictions.

Run from this sample's `control-plane` directory in one Bash session. If your
scaffolding tool did not copy this directory, obtain it from the sample source.

## 1. Select the account

```bash
az login
export SUBSCRIPTION_ID="<test-subscription-id>"
export RESOURCE_GROUP="<test-resource-group>"
export ACCOUNT_NAME="<disposable-foundry-account>"
az account set --subscription "$SUBSCRIPTION_ID"

export ACCOUNT_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME"
export ARM_ENDPOINT="$(az cloud show --query endpoints.resourceManager -o tsv)"
export ARM_AUDIENCE="$ARM_ENDPOINT"
export ARM_ENDPOINT="${ARM_ENDPOINT%/}"
export RAI_API_VERSION="2026-09-01"
```

Use the standard ARM endpoint for your Azure cloud and the **same endpoint
throughout**, including cleanup. This sample has not established sovereign-cloud
availability.

```bash
az rest --method get --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID?api-version=$RAI_API_VERSION" \
  --query '{id:id,location:location,kind:kind}'

export RUN_ID="$(date -u +%Y%m%d%H%M%S)-$(openssl rand -hex 4)"
export DEFINITION_NAME="sample-egress-$RUN_ID"
export ASSIGNMENT_NAME="egress-$(openssl rand -hex 6)"
export ALLOWED_NAME="sample-allowed-$RUN_ID"
export DENIED_NAME="sample-denied-$RUN_ID"
export DEFINITION_ID="/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Authorization/policyDefinitions/$DEFINITION_NAME"
export ASSIGNMENT_ID="$ACCOUNT_ID/providers/Microsoft.Authorization/policyAssignments/$ASSIGNMENT_NAME"
export OUTPUT_DIR="$(mktemp -d)"
```

**Stop if the account GET fails.** Using an existing disposable account avoids
creating another account.

Retain the identifiers so cleanup is possible if the terminal closes:

```bash
declare -p ACCOUNT_ID ARM_ENDPOINT ARM_AUDIENCE RAI_API_VERSION \
  DEFINITION_ID ASSIGNMENT_ID ALLOWED_NAME DENIED_NAME OUTPUT_DIR \
  > "$OUTPUT_DIR/session.sh"
printf 'Session and response files: %s\n' "$OUTPUT_DIR"
```

These identifiers are not credentials. Never put tokens or real header secrets
in sample files, captured responses, or shell tracing.

## 2. Administrator: author and assign the custom definition

The definition contains parameters and a policy rule. Its default effect is
**Audit**. [`assignment-parameters.json`](assignment-parameters.json) explicitly
selects **Deny** for this demonstration and permits only `httpbin.org`.
The custom-create body intentionally contains only `properties`: copying a
built-in's top-level `id` or `name` would conflict with your chosen definition
name and cause `MismatchedPolicyDefinitionName`.

```bash
az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$DEFINITION_ID?api-version=2023-04-01" \
  --body @policy-definition.json > "$OUTPUT_DIR/definition.json"

jq --arg definitionId "$DEFINITION_ID" \
  '{properties: {
     displayName: "Sample: administrator RAI egress restrictions",
     policyDefinitionId: $definitionId,
     enforcementMode: "Default",
     parameters: .
  }}' assignment-parameters.json > "$OUTPUT_DIR/assignment-request.json"

az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ASSIGNMENT_ID?api-version=2024-04-01" \
  --body @"$OUTPUT_DIR/assignment-request.json" \
  > "$OUTPUT_DIR/assignment.json"

az rest --method get --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ASSIGNMENT_ID?api-version=2024-04-01" \
  --query 'properties.{scope:scope,enforcementMode:enforcementMode,parameters:parameters}'
```

Stop on any error. Check that the scope is exactly `ACCOUNT_ID`, the effect is
`Deny`, and enforcement mode is `Default`. Successful definition/assignment
creation means ARM accepted the configuration; it is **not** proof that a RAI
write has been evaluated yet.

Assignments take time to propagate. There is no fixed sleep that proves
readiness. Wait several minutes before the next step and use the actual denied
write as the check. Do not treat an initial successful forbidden write as
enforcement success or an immediate policy defect.

## 3. Developer: save an allowed RAI policy

[`rai-policy-allowed.json`](rai-policy-allowed.json) is a **different JSON
document** from the administrator's definition: it is the resource being
governed. It sets runtime mode `Enforced`, default action `Deny`, and an Allow
rule for `httpbin.org` with the exact path `/get`. The developer chooses this
narrower path; the administrator's sample policy checks the host only.

```bash
az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$ALLOWED_NAME?api-version=$RAI_API_VERSION" \
  --body @rai-policy-allowed.json > "$OUTPUT_DIR/allowed-create.json"

az rest --method get --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$ALLOWED_NAME?api-version=$RAI_API_VERSION" \
  > "$OUTPUT_DIR/allowed-before.json"
```

Expected: the PUT succeeds (HTTP 200/201), and GET shows the saved egress
configuration. Azure CLI prints JSON, not the HTTP status by default. This
does not contact `httpbin.org` or run a hosted agent.

If demonstrating separate identities, the administrator performs step 2 and the
developer performs steps 3-4 with their own Azure login. Keep the same resource
identifiers; do not grant new permissions just to make a failed test pass.

## 4. Developer: attempt a forbidden create

[`rai-policy-denied.json`](rai-policy-denied.json) changes **only the match
host** to `example.com`. Its valid Enforced/default-Deny baseline means the
destination restriction is the intended reason for rejection.

```bash
az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$DENIED_NAME?api-version=$RAI_API_VERSION" \
  --body @rai-policy-denied.json
```

Expected: Azure CLI exits nonzero with HTTP **403** and error code
**`RequestDisallowedByPolicy`**. The error's policy details must identify
**your `ASSIGNMENT_ID` and `DEFINITION_ID`**, not an unrelated inherited policy.
A typical response has this shape (other fields are omitted):

```json
{
  "error": {
    "code": "RequestDisallowedByPolicy",
    "message": "Resource was disallowed by policy.",
    "additionalInfo": [
      {
        "type": "PolicyViolation",
        "info": {
          "policyAssignmentId": "<your assignment resource ID>",
          "policyDefinitionId": "<your custom definition resource ID>"
        }
      }
    ]
  }
}
```

If the write succeeds, enforcement has **not** been demonstrated. The test
resource may now exist: delete that exact `DENIED_NAME`, wait, and retry its
creation. Verify deletion with GET before calling a subsequent attempt a
create. If it continues to succeed, stop and inspect assignment scope, effect,
enforcement mode and propagation; do not declare a pass.

After an attributed denial, confirm the forbidden resource was not created:

```bash
az rest --method get --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$DENIED_NAME?api-version=$RAI_API_VERSION"
# Expected: 404 resource not found, not 401/403.
```

At this point, the required walkthrough is complete: one compliant write
succeeded and one noncompliant write was rejected by this assignment. Continue
with the optional checks below, or proceed to cleanup.

## How the definition works

The `if` first selects RAI resources with an egress section. Its `anyOf` finds
an invalid baseline or at least one unsupported/unapproved rule. The
`count.field` iterates `rules[*]`, keeping each action and host in the **same
rule**. The `then` applies the assignment's effect.

To permit another exact host, edit `approvedHosts` in the assignment:

```json
{
  "approvedHosts": { "value": ["httpbin.org", "api.contoso.com"] },
  "effect": { "value": "Deny" }
}
```

Use hostnames only, without schemes, ports, paths or wildcards. Matching is
case-insensitive; subdomains are not implicitly approved. An empty list permits
no Allow rules. The example checks every Allow rule, even after a developer
Deny; it does not simulate runtime first-match ordering.

This intentionally does **not** implement administrator path restrictions,
denied-host carve-outs, wildcard containment, rewrite analysis or credential
validation. Do not simply add Transform/Rewrite to the accepted actions:
supporting those actions requires additional destination and credential checks.
Use a fuller governance policy for those requirements; this sample is not a
replacement for it.

## Optional: verify that a denied update preserves state

Attempt the same forbidden body against the **existing allowed resource**:

```bash
az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$ALLOWED_NAME?api-version=$RAI_API_VERSION" \
  --body @rai-policy-denied.json
# Expected: 403 RequestDisallowedByPolicy attributed to this assignment.

az rest --method get --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$ALLOWED_NAME?api-version=$RAI_API_VERSION" \
  > "$OUTPUT_DIR/allowed-after.json"

jq -S '.properties' "$OUTPUT_DIR/allowed-before.json" > "$OUTPUT_DIR/before-properties.json"
jq -S '.properties' "$OUTPUT_DIR/allowed-after.json" > "$OUTPUT_DIR/after-properties.json"
diff -u "$OUTPUT_DIR/before-properties.json" "$OUTPUT_DIR/after-properties.json"
```

Expected: no diff. A denied update must leave the previous configuration intact.
This optional check tests PUT, not PATCH.

## Optional: compare `Default` with `DoNotEnforce`

The required test used assignment `enforcementMode: Default`, so the definition's
`Deny` effect blocked the forbidden write. Change only the assignment enforcement
mode to evaluate the same definition without applying its deny effect:

```bash
jq '.properties.enforcementMode = "DoNotEnforce"' \
  "$OUTPUT_DIR/assignment-request.json" \
  > "$OUTPUT_DIR/assignment-request-do-not-enforce.json"

az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ASSIGNMENT_ID?api-version=2024-04-01" \
  --body @"$OUTPUT_DIR/assignment-request-do-not-enforce.json" \
  > "$OUTPUT_DIR/assignment-do-not-enforce.json"

az rest --method get --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ASSIGNMENT_ID?api-version=2024-04-01" \
  --query 'properties.enforcementMode'
```

Expected: the query returns `DoNotEnforce`. Assignment changes take time to
propagate, so wait several minutes before retrying the previously forbidden
create:

```bash
az rest --method put --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$DENIED_NAME?api-version=$RAI_API_VERSION" \
  --body @rai-policy-denied.json \
  > "$OUTPUT_DIR/denied-create-do-not-enforce.json"
```

Expected: the write succeeds because Azure Policy evaluated the definition
without applying its `Deny` effect. The resulting resource can later appear as
noncompliant, but compliance reporting is asynchronous. A successful write or
an empty compliance page alone does not prove that evaluation occurred. Unlike
`Default` with `Deny`, `DoNotEnforce` does not produce a policy-denial Activity
Log event.

Azure Policy `effect: Audit` and RAI `egressPolicy.mode: Audit` are also
different settings. Changing the definition effect to `Audit` makes the
administrator's checks nonblocking; this definition still classifies RAI
runtime `Audit` mode as noncompliant. To investigate the Azure Policy Audit
effect, correlate the RAI write with an Activity Log event
`Microsoft.Authorization/policies/audit/action` identifying the assignment.

## Optional: run the accepted policy with the hosted agent

After the ARM checks pass, you can separately exercise the accepted RAI policy
using this sample's Python or .NET agent. First complete the parent sample's
deployment prerequisites in an environment targeting **this same account and
project**, including its model deployment. Confirm that environment before
changing `RAI_POLICY_ID`.

From the parent sample directory, in the session that has `ACCOUNT_ID` and
`ALLOWED_NAME`:

```bash
azd env set RAI_POLICY_ID "$ACCOUNT_ID/raiPolicies/$ALLOWED_NAME"
```

For the .NET sample only, `azure.ai.agents` 1.0.0-beta.16 does not interpolate
`${RAI_POLICY_ID}` in `policies.raiPolicyName`. Run
`azd env get-value RAI_POLICY_ID`, then replace `${RAI_POLICY_ID}` in the
generated `azure.yaml` with that full ARM resource ID before deploying.

```bash
azd deploy
azd ai agent invoke "test egress to https://httpbin.org/get"
azd ai agent invoke "test egress to https://example.com/get"
azd ai agent invoke "test egress to https://httpbin.org/anything"
```

Do not run `azd provision` or `azd up` with the restrictive assignment active:
the parent sample's catalog includes policies this assignment intentionally
rejects. Wait until the newly deployed version is active and receives traffic.

Expected tool-reported outbound statuses are **200, 403, 403**, respectively.
The last request checks the **developer-authored RAI policy's** `/get` path
restriction. Azure Policy in this sample does not require that path: another
RAI policy allowing all paths on `httpbin.org` would also comply. Keep TLS
verification enabled. The invocation API itself may return
HTTP 200 while the tool reports an outbound HTTP 403; that is different from
the ARM `RequestDisallowedByPolicy` failure demonstrated above. A model error,
TLS failure, timeout, or inactive agent is not a successful egress-denial test.

These are runtime egress-proxy checks, **not APES checks**. Remove the test
agent/version through the parent sample's lifecycle before removing its RAI
policy. Active or idle sessions can block agent deletion; stop those test
sessions first, or explicitly cascade-delete only an agent created for this
test. Do not repoint an existing production agent or delete shared
infrastructure to clean up this demonstration.

## Cleanup

Run cleanup even if a test failed or a forbidden write unexpectedly succeeded.
If needed, restore the saved variables with `source /path/to/session.sh`.
If one identity has both permission sets, it can run every command below. When
using separate identities, switch the Azure CLI login as labeled and run
`az account set --subscription "$SUBSCRIPTION_ID"` after each login.

Using the **administrator identity**, remove the assignment first and then the
custom definition:

```bash
az rest --method delete --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ASSIGNMENT_ID?api-version=2024-04-01"

az rest --method delete --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$DEFINITION_ID?api-version=2023-04-01"
```

Using the **developer identity**, remove the two test RAI policies:

```bash
az rest --method delete --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$ALLOWED_NAME?api-version=$RAI_API_VERSION"
az rest --method delete --resource "$ARM_AUDIENCE" \
  --url "$ARM_ENDPOINT$ACCOUNT_ID/raiPolicies/$DENIED_NAME?api-version=$RAI_API_VERSION"
```

A 404 on an exact test resource is acceptable during cleanup; do not ignore
authorization or other errors. A 202 means deletion is still in progress.
Repeat GET for the assignment, definition and
both RAI-policy IDs and confirm each is absent. Do **not** delete the account,
resource group, parent sample's policies or other users' resources. Retain the
local response files if diagnosing a failure.

## Troubleshooting and boundaries

| Observation | Meaning / next check |
|---|---|
| Definition creation reports an unknown alias | The required alias rollout is not available on that endpoint yet. Stop; do not remove policy checks to make it pass. |
| RAI API reports an unsupported API version or egress field | Account/RP support is missing. Alias registration alone does not enable the resource API. |
| 403 `AuthorizationFailed` | Access/RBAC issue, **not** the expected policy denial. |
| 403 `RequestDisallowedByPolicy` names another assignment | An inherited or separate policy blocked the write; this is not proof of the sample assignment. |
| Forbidden write succeeds | Check propagation, exact scope, `effect: Deny`, and `enforcementMode: Default`. Clean up the unexpected resource. |
| A pre-existing RAI policy violates the assignment | Assignment does not automatically repair existing resources. Compliance reporting can be delayed. |
| A hosted agent still creates or sends traffic | Those are outside this control-plane test. This assignment does not add APES checks or revoke running workloads. |
| Transform/Rewrite or runtime Audit scenario provisioning fails | This teaching definition intentionally rejects these configurations. Use separate accounts or remove this demo assignment first. |

Custom definitions are not automatically upgraded when a built-in becomes
available. This teaching example is not equivalent to the full policy; review
the published definition and parameters before migrating an assignment.

Public references:
[Azure Policy definitions](https://learn.microsoft.com/azure/governance/policy/concepts/definition-structure-basics),
[assignment scope](https://learn.microsoft.com/azure/governance/policy/concepts/scope),
[Deny effect](https://learn.microsoft.com/azure/governance/policy/concepts/effect-deny),
[Audit effect](https://learn.microsoft.com/azure/governance/policy/concepts/effect-audit).
