---
ms.custom: doc-kit-assisted
ai-usage: ai-assisted
---

# Agent Controls samples (preview)

This repository contains complete Agent Controls examples for Microsoft Foundry. The samples include policy request bodies, Rego rules and tests, PowerShell management scripts, and a Node.js evaluation client.

The client is a sample helper, not a product SDK. Your application remains responsible for calling the required intervention points and enforcing each verdict before executing a tool or releasing content.

## Prerequisites

For local tests, use:

- Node.js 22 or later with npm.
- Open Policy Agent (OPA) 1.x for `rego.v1` policies.
- PowerShell 7 or later.

For live evaluation, you also need:

- An Azure subscription.
- An Azure AI Content Safety account enabled for the Agent Controls preview in a region enabled for your preview access.
- Permission to create policy and Rego resources, for example `Contributor` at the account's scope.
- The `Cognitive Services User` role on the serving account for runtime calls.
- Azure CLI for sign-in when using the management scripts.

Additional role-assignment permission is required only when granting roles. Classifier and LLM-judge examples also require those capabilities to be enabled on the serving account.

## Get started

1. Clone or download this repository. Keep the README, scripts, template directories, and request fixtures together.
1. Open PowerShell in the directory containing `readme.md` and the management scripts.
1. Run `npm ci` to install the dependencies recorded in the lock file. Stop if installation fails.

The samples use ARM API version `2026-11-15-preview`, Unified Moderate API version `2026-10-15-preview`, and hosted ACS manifest version `0.4.0-alpha.1`. Account creation alone doesn't enable the preview.

## Configure live access

Sign in with Azure CLI before using the management scripts. The [management scripts](#client-and-management-scripts) can create resources and return the account and policy values below.

Set these environment variables before using the Node.js client for live evaluation. `DefaultAzureCredential` supplies its access token.

| Setting | Required | Value |
| --- | --- | --- |
| `AGENT_CONTROL_ENDPOINT` | Yes | The serving account's HTTPS origin. |
| `AGENT_CONTROL_ACCOUNT_ID` | Yes | The full ARM resource ID of the serving account. |
| `AGENT_CONTROL_POLICY_ID` | Yes | The full ARM resource ID of the named policy. |
| `AGENT_CONTROL_PRODUCER_ID` | No | Defaults to `AGENT_CONTROL_ACCOUNT_ID`. |

## Policy templates

These templates are complete starting points: each directory contains an ARM policy request body, a Rego module, and local Rego tests. Review the rule, adapt it to your application, and test the host integration before rollout.

Each template is independent. Selecting one does not automatically include the others.

| Template | Use case | Required points | Additional capability |
| --- | --- | --- | --- |
| [Refund guard](#refund-guard) | Limit individual financial actions. | All eight in the demonstration; restrictions apply at `pre_tool_call`. | None |
| [Approved tools](#approved-tools) | Restrict an agent to selected read operations. | `pre_tool_call` | None |
| [Approved document destinations](#approved-document-destinations) | Restrict document-retrieval URLs. | `pre_tool_call` | None |
| [Content safety](#content-safety) | Inspect harmful-content and prompt-injection signals. | `input`, `output` | Enabled Content Safety classifiers |
| [Data protection](#data-protection) | Block output when PII is detected. | `output` | Enabled PII classifier |
| [Commitment review](#commitment-review) | Review definite promises in customer-support output. | `output` | Enabled customer-owned LLM judge |

Use the matching Rego module and tests to review expected decisions before adapting a template.

## Publish a template

Complete the [prerequisites](#prerequisites) and [live access configuration](#configure-live-access) first. The examples below use OPA 1.x for local tests and Node.js 22 or later with npm for the evaluation client.

Before running the block, set `$AccountId` to the serving account's full ARM resource ID and `$Endpoint` to its HTTPS origin. If you create the account with [`provision.ps1`](./provision.ps1), use its `AccountId` and `Endpoint` output values.

Before each scenario, use the directory named in its **Files** paragraph for the `$Template` assignment in the block below. The supplied assignment selects `approved-tools`; change that selection for another scenario. Publish the selected template and update `AGENT_CONTROL_POLICY_ID` from the returned `$Published.PolicyId` whenever you switch templates.

From the directory containing this README, install the client dependencies, configure the account, and select a template:

```powershell
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Sample dependency installation failed.' }
$env:AGENT_CONTROL_ENDPOINT = $Endpoint
$env:AGENT_CONTROL_ACCOUNT_ID = $AccountId
$env:AGENT_CONTROL_PRODUCER_ID = $AccountId

$Template = 'approved-tools'
opa check --strict --ignore '*.json' ".\$Template"
if ($LASTEXITCODE -ne 0) { throw 'Rego compilation failed.' }
opa test --verbose --ignore '*.json' ".\$Template"
if ($LASTEXITCODE -ne 0) { throw 'Rego tests failed.' }

$Published = .\publish-policy.ps1 -AccountId $AccountId `
    -TemplateDirectory ".\$Template"
$env:AGENT_CONTROL_POLICY_ID = $Published.PolicyId
```

The script creates resources; it does not overwrite existing names. For a new version, pass a new `-PolicyName`. Before publishing `llm-review`, complete its [model and identity setup](#llm-judge-setup) and replace the endpoint and deployment placeholders in a copy.

The following inspection commands call the service but never execute a tool or release output. The inspection client exits with code `0` for an allow or transform, `2` for a deny, and `1` for an evaluation failure. The JSON fixtures have fixed example timestamps and session IDs; a real host builds a fresh context for each action.

### LLM judge setup

Before publishing `llm-review`, confirm that you have:

- LLM-judge execution enabled for the serving account, model and version, region, and processing configuration.
- A customer-owned Azure OpenAI deployment qualified for the judge preview and its structured-output protocol.
- A deployment and serving account that meet the supported tenant and processing-location requirements.
- A system-assigned managed identity on the serving Content Safety account with inference access on the model account.
- A supported network route from the service to the model endpoint.

Replace the endpoint and deployment placeholders in a copy of [`llm-review/policy.json`](./llm-review/policy.json). Use the model account's HTTPS origin without a deployment path or query string, and the exact qualified deployment name. A successful policy upload does not establish model authorization, connectivity, or readiness.

## Refund guard

**Files:** In `refund-guard`: [`policy.json`](./refund-guard/policy.json) (ARM body), [`policy.rego`](./refund-guard/policy.rego) (Rego), and [`policy_test.rego`](./refund-guard/policy_test.rego) (tests).

Allows `lookup_order` and `refund_order`. Refund amounts must be numeric, greater than zero, and no greater than `100`. Unknown tools, invalid types, missing amounts, and amounts outside the limit are blocked.

```powershell
node .\evaluate.mjs .\requests\pre-tool.json
node .\evaluate.mjs .\requests\pre-tool-denied.json
```

With the unmodified policy, the first request can be allowed and the second must be denied. Run `npm run demo` with this selected policy to verify that the denied call never reaches the simulator.

**Adapt:** Change the supported tool names and transaction limit together in the catalog, rule, tests, and host registration. Define the currency and units in your application.

**Boundary:** This is a per-call limit. It does not check order ownership, entitlement, currency conversion, cumulative refunds, or concurrent spending. Enforce those constraints in the authoritative transaction service; a caller-supplied total is not an authoritative ledger.

## Approved tools

**Files:** In `approved-tools`: [`policy.json`](./approved-tools/policy.json) (ARM body), [`policy.rego`](./approved-tools/policy.rego) (Rego), and [`policy_test.rego`](./approved-tools/policy_test.rego) (tests).

Allows only `search_catalog` and `get_order` at the pre-tool point. The catalog and rule both use exact, case-sensitive tool names.

```powershell
node .\evaluate.mjs .\requests\approved-tool.json
```

**Adapt:** Replace the two names with your application's read-only tools. Remove unapproved tools from the application where possible, not just from the policy catalog.

**Boundary:** A tool named `get_order` is not inherently safe or authorized. The registered implementation must actually be read-only and must enforce the calling user's access. This policy does not validate the tool's argument schema.

## Approved document destinations

**Files:** In `approved-domains`: [`policy.json`](./approved-domains/policy.json) (ARM body), [`policy.rego`](./approved-domains/policy.rego) (Rego), and [`policy_test.rego`](./approved-domains/policy_test.rego) (tests).

Allows `fetch_document` only for strict HTTPS URL strings on `learn.microsoft.com` or `docs.example.com`, without an explicit port or fragment. The tests cover lookalike domains, user-info syntax, unapproved schemes, missing URLs, and other invalid inputs.

```powershell
node .\evaluate.mjs .\requests\approved-url.json
```

**Adapt:** Replace the example domains and test the exact URL format emitted by your host. Apply any normalization in trusted host code before evaluation, then dispatch that evaluated value.

**Boundary:** This checks the proposed URL string. It is not a network firewall or a complete SSRF defense.

The fetch implementation must also handle DNS/IP restrictions, redirects, proxies, and the final destination safely. Never follow a redirect to an unevaluated destination just because the original URL was allowed.

## Content safety

**Files:** In `content-safety`: [`policy.json`](./content-safety/policy.json) (ARM body), [`policy.rego`](./content-safety/policy.rego) (Rego), and [`policy_test.rego`](./content-safety/policy_test.rego) (tests).

Requests `Hate`, `SelfHarm`, `Sexual`, `Violence`, and `PromptInjection` observations for input and output. It allows only when all required observations are present, numeric severities are below `4`, and prompt injection is not detected.

```powershell
node .\evaluate.mjs .\requests\input.json
node .\evaluate.mjs .\requests\output.json
```

**Adapt:** Select enabled categories and thresholds appropriate to your application. Evaluate both false positives and false negatives. The severity boundary is an example policy choice, not a recommended universal threshold.

**Boundary:** The numeric scale is ordinal `0`-`7`, not probability. The template checks only its declared points, and content classification does not establish that a tool action is authorized.

## Data protection

**Files:** In `data-protection`: [`policy.json`](./data-protection/policy.json) (ARM body), [`policy.rego`](./data-protection/policy.rego) (Rego), and [`policy_test.rego`](./data-protection/policy_test.rego) (tests).

Requests `PersonallyIdentifiableInformation` detection on output. It allows only an explicit, valid `detected: false` observation. Detection, missing evidence, and invalid evidence remain blocked.

```powershell
node .\evaluate.mjs .\requests\output.json
```

**Adapt:** Confirm PII capability access and evaluate representative data types, languages, and formats. Define a separate process for authorized disclosures if your application needs them.

**Boundary:** This template blocks; it does not redact. It does not guarantee that all personal or confidential information can be detected, and it does not establish regulatory compliance. Keep data minimization and application-level access controls in place.

## Commitment review

**Files:** In `llm-review`: [`policy.json`](./llm-review/policy.json) (ARM body), [`policy.rego`](./llm-review/policy.rego) (Rego), and [`policy_test.rego`](./llm-review/policy_test.rego) (tests).

Uses a customer-owned model to distinguish informational customer-support output from definite promises of refunds, credits, compensation, or delivery dates. The Rego rule allows only completed, applicable `informational` observations below the rubric's threshold. Other results remain blocked.

Complete the [LLM judge setup](#llm-judge-setup) before publishing this template:

```powershell
node .\evaluate.mjs .\requests\output.json
node .\evaluate.mjs .\requests\output-commitment.json
```

**Adapt:** Change the rubric, labels, score interpretation, Rego, and evaluation data together. Define what your application does with a blocked response.

**Boundary:** This is semantic classification, not a factuality or authorization check. The model's score is rubric-defined and might vary. The supplied rule blocks for review; it does not open a review queue or automatically approve a commitment.

## Client and management scripts

Keep these files in the directory containing this README.

| File | Purpose |
| --- | --- |
| [agent-control.mjs](./agent-control.mjs) | Submit an evaluation, validate its receipt, and gate an application action. |
| [agent-control.test.mjs](./agent-control.test.mjs) | Test the client with synthetic responses and a local test server. |
| [demo.mjs](./demo.mjs) | Exercise all eight intervention points and demonstrate a blocked simulated refund. |
| [evaluate.mjs](./evaluate.mjs) | Evaluate a request file without dispatching a tool or releasing output. |
| [arm.ps1](./arm.ps1) | Make authenticated ARM requests with bounded timeouts and explicit error handling. |
| [arm.test.ps1](./arm.test.ps1) | Test conditional account creation and concurrent-creation conflicts with mocked Azure CLI and HTTP calls. |
| [provision.ps1](./provision.ps1) | Create a Content Safety account with a system-assigned identity. Supply `SubscriptionId`, `ResourceGroup`, `AccountName`, and `Location`; returns `AccountId`, `Endpoint`, and `ServingPrincipalId`. |
| [publish-policy.ps1](./publish-policy.ps1) | Create named Rego and policy resources with `AccountId` and `TemplateDirectory`, plus optional `PolicyName`. Returns `PolicyId`, `RegoId`, and ETags, and refuses to overwrite existing names. |
| [remove-policy.ps1](./remove-policy.ps1) | Delete the specified `PolicyId` and `RegoId` with ETag checks and operation polling. |
| [package.json](./package.json) and [package-lock.json](./package-lock.json) | Declare and lock the Node.js dependencies. |

The provisioning script doesn't enable preview access or grant roles.

The `requests` subdirectory contains the input, output, and tool-call fixtures used by the [policy templates](#policy-templates).

The demonstration uses an in-memory tool simulator. It doesn't issue real refunds. An evaluation request can still consume service or model capacity when it calls an enabled account.

## Verify the samples locally

Run the following commands from the directory containing this README:

```powershell
$Templates = @(
    '.\refund-guard', '.\approved-tools', '.\approved-domains',
    '.\content-safety', '.\data-protection', '.\llm-review'
)
opa check --strict --ignore '*.json' @Templates
if ($LASTEXITCODE -ne 0) { throw 'Rego compilation failed.' }
opa test --verbose --ignore '*.json' @Templates
if ($LASTEXITCODE -ne 0) { throw 'Rego tests failed.' }
npm test
if ($LASTEXITCODE -ne 0) { throw 'HTTP client and gate tests failed.' }
pwsh -NoLogo -NoProfile -File .\arm.test.ps1
if ($LASTEXITCODE -ne 0) { throw 'ARM script tests failed.' }
```

The template tests are linked in the [policy catalog](#policy-templates), alongside the [client tests](./agent-control.test.mjs).

The ARM tests mock Azure CLI and HTTP calls. They don't create or delete Azure resources.

These tests use local fixtures and synthetic observations. They don't establish live service access, classifier quality, or model quality. Before rollout, verify enabled account access and capabilities, complete policy loading, the actual classifier/judge results, and enforcement in your application.

## Related content

- [Configure live access](#configure-live-access).
- [Choose a policy template](#policy-templates).
- [Review the client and management scripts](#client-and-management-scripts).
