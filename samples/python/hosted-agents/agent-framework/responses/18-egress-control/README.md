# Egress Control Test Agent (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent for testing **managed egress proxy policies** on Azure AI Foundry hosted agents. The agent accepts text commands, makes outbound HTTP requests through the egress proxy, and returns the full response — enabling validation of Allow, Deny, Transform, and Rewrite rules defined via [RAI egress policies](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/egress).

## Administrator policy authoring (control plane)

To restrict **which RAI egress policies developers may save**, use the
[control-plane Azure Policy walkthrough](control-plane/README.md). It includes
a small exact-host policy definition, assignment parameters, and allowed/denied RAI
requests. No published built-in, model deployment, or running agent is required.
The walkthrough demonstrates an ARM policy denial, not APES or runtime traffic
enforcement. Run it on a disposable account separately from the runtime scenarios
below; the administrator restrictions intentionally reject some scenario policies.

## How it works

The agent uses the Agent Framework with `FoundryChatClient` and exposes an `egress_test` tool. When you send a command, the LLM routes it to the tool, which makes outbound HTTP requests via `aiohttp` and returns the result (status code, headers, body). Every outbound request includes marker headers (`X-Test-Marker`, `User-Agent`) that are useful for verifying Transform operations.

> **Note:** Each invocation goes through the configured model deployment (e.g., `gpt-4.1`), which decides to call the `egress_test` tool. A valid model deployment is required in the Foundry project. Be aware of model rate limits when running tests in quick succession — add 10–15 second delays between invocations to avoid 429 errors.

> **TLS verification:** Outbound requests verify TLS certificates by default. When testing an egress proxy in **Full inspection** mode (the proxy terminates TLS with its own certificate), set `EGRESS_TEST_VERIFY_TLS=false` so requests accept the proxy's certificate. Leave it enabled otherwise.

### Supported commands

Send any of these plain-text commands to the agent (as the user message on an `azd ai agent invoke` call). The LLM interprets the command and calls the `egress_test` tool to make the corresponding outbound request:

| Command | Description |
|---------|-------------|
| `test egress to <url>` | GET request — returns status + body |
| `test headers to <url>` | GET request — returns echoed request headers + body (use with httpbin.org/headers) |
| `test response headers from <url>` | GET request — returns response headers only |
| `test post to <url> <json>` | POST with JSON body |
| `test connectivity` | Probe httpbin.org, example.com, google.com |
| `help` | Show the help message |

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the AI agent extension:
   ```bash
   azd ext install microsoft.foundry
   ```
3. Authenticate:
   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from `azure.yaml`:

```bash
mkdir my-egress-agent && cd my-egress-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/18-egress-control/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources

Provision the Foundry project and the dependent egress policy layer:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "test connectivity"
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "test egress to https://httpbin.org/get"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.azure-ai-foundry)** extension installed.
2. Sign in to Azure in VS Code.

### Create the project

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Create Hosted Agent**.
2. Select this sample from the gallery. The extension scaffolds the project into a new workspace and generates `azure.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically.
3. Complete the **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one).

### Run and debug the agent

Press **F5** to start the agent in debug mode. The agent host will start on `http://localhost:8088`.

### Test with Agent Inspector

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector**.
2. The Inspector connects to the running agent. Send messages to chat and view streamed responses.

### Deploy to Foundry

Run `azd up` in the integrated terminal so the Foundry and egress infrastructure layers are provisioned before the guarded agent is deployed. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Deploy the egress guardrail

The steps above deploy the agent itself. To deploy it **with a managed egress guardrail** — so outbound traffic is restricted at deploy time rather than only during testing — use the layered infrastructure configured in `azure.yaml`.

The guardrail is **not** application code; it's a definition-level setting. `azd` first provisions the Foundry layer, then the dependent egress Bicep layer in [infra/egress](infra/egress). The Bicep layer provisions a **catalog** of RAI egress policies — one per guardrail pattern shown below — and exports the full Azure Resource Manager (ARM) resource ID of the one attached to the agent as `RAI_POLICY_ID`. The agent's `policies` list uses that output automatically.

> An agent binds to a **single** RAI policy (`rai_config` is one policy, not a list). A policy can carry both content filters and an `egressPolicy` with many first-match `rules`, so you compose guardrails *within* one policy rather than attaching several. The catalog lets you provision every pattern up front and pick which one the agent enforces.

1. **Pick the policy to enforce.** [infra/egress/main.bicep](infra/egress/main.bicep) provisions a `Microsoft.CognitiveServices/accounts/raiPolicies` resource for each catalog entry (`allow-httpbin`, `transform-insert-header`, `rewrite-host`, `deny-all`, `wildcard-host`, `audit-deny`, and more — see the rule schema in [Testing egress policies](#testing-egress-policies) below). The `agentPolicyName` parameter (default `allow-httpbin`, which denies all egress except `httpbin.org`) selects which one is attached to the agent. Set `managedIdentityStorageHost` to also provision the managed-identity injection policy.

2. **Provision and deploy.** Run `azd up`. The Foundry layer supplies `AZURE_AI_ACCOUNT_NAME` to the egress layer, and the `RAI_POLICY_ID` output for the selected `agentPolicyName` is bound to the agent before it is deployed.

> The [scenarios](scenarios/README.md) suite creates and tears down its own policies at runtime so it can exercise many rule combinations end-to-end. Use the layered `azd` infrastructure for the deployment story; use the scenarios to validate specific rules.

## Testing egress policies

Once the agent is deployed, you can create RAI egress policies on your Azure AI Services account to control its outbound network access. Below are test scenarios that validate each policy capability. The invocation prompts are taken from the runnable tests in the [scenarios](scenarios/) folder.

### Prerequisites for policy testing

- A **Microsoft Foundry** resource (Azure AI Services / Cognitive Services account) with hosted agents enabled
- The agent deployed to a Foundry project linked to that account
- A **model deployment** (e.g., `gpt-4.1`) available in the project — the agent routes commands through the LLM
- API access to create RAI egress policies (`2026-05-15-preview` or later)

> **Tip:** When attaching or changing an egress policy, create a new agent version with the `rai_config.rai_policy_name` pointing to the policy's full resource ID, then pin traffic to that version. Wait for the version to become `active` before testing.

### Test 1: Allow/Deny enforcement

The layered deployment creates a policy that denies all traffic except to `httpbin.org`. To create additional policies for testing, use the **Cognitive Services (CogSvc) account** `raiPolicies` control-plane API (`2026-05-15-preview` or later). Apply the policy body below with `az rest`:

```bash
az rest --method put \
  --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/<policy-name>?api-version=2026-05-15-preview" \
  --body @policy.json
```

where `policy.json` contains:

```json
{
  "properties": {
    "basePolicyName": "Microsoft.DefaultV2",
    "egressPolicy": {
      "mode": "Enforced",
      "defaultAction": "Deny",
      "rules": [
        {
          "name": "allow-httpbin",
          "ruleType": "Fqdn",
          "match": { "host": "httpbin.org" },
          "action": { "actionType": "Allow" }
        }
      ]
    }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://httpbin.org/get"
# Expected: 200 OK

azd ai agent invoke "test egress to https://example.com"
# Expected: 403 Forbidden
```

> **E2E verified:** httpbin.org returns 200 with `X-Adc-Proxy: 1` header confirming traffic went through the egress proxy. Denied hosts return 403.

> **Schema note:** The examples in Tests 2–12 below show just the **rule object** that goes inside `properties.egressPolicy.rules[]`. Wrap them in the same `properties` → `egressPolicy` structure (with `basePolicyName`, `mode`, and `defaultAction`) shown in Test 1 before applying them with `az rest`.

### Test 2: Transform — Insert header

Insert a custom header on requests to `httpbin.org`:

```json
{
  "name": "insert-custom-header",
  "ruleType": "Fqdn",
  "match": { "host": "httpbin.org" },
  "action": {
    "actionType": "Transform",
    "headers": [
      { "name": "X-Custom-Tag", "value": "my-value", "operation": "Insert" }
    ]
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke -o "raw" "test headers to https://httpbin.org/headers"
# Expected: "X-Custom-Tag": "my-value" in the echoed headers
```

### Test 3: Transform — Set (overwrite) header

Overwrite the `User-Agent` header:

```json
{
  "name": "set-user-agent",
  "ruleType": "Fqdn",
  "match": { "host": "httpbin.org" },
  "action": {
    "actionType": "Transform",
    "headers": [
      { "name": "User-Agent", "value": "policy-override-agent", "operation": "Set" }
    ]
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke -o "raw" "test headers to https://httpbin.org/headers"
# Expected: User-Agent is "policy-override-agent" (not "egress-test-agent/2.0")
```

> **Note**: `Set` always overwrites the header value. `Insert` only adds the header if it doesn't already exist. Since this agent sets `User-Agent` on every request, `Insert` would be a no-op while `Set` overwrites it.

### Test 4: Transform — Remove header

Remove the `X-Test-Marker` header:

```json
{
  "name": "remove-test-marker",
  "ruleType": "Fqdn",
  "match": { "host": "httpbin.org" },
  "action": {
    "actionType": "Transform",
    "headers": [
      { "name": "X-Test-Marker", "operation": "Remove" }
    ]
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke -o "raw" "test headers to https://httpbin.org/headers"
# Expected: X-Test-Marker does not appear in the echoed headers
```

### Test 5: Rewrite — Host rewrite

Rewrite requests to `www.google.com` to go to `www.bing.com` instead:

```json
{
  "name": "rewrite-google-to-bing",
  "ruleType": "Fqdn",
  "match": { "host": "www.google.com" },
  "action": {
    "actionType": "Rewrite",
    "rewrite": { "scheme": "https", "host": "www.bing.com" }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://www.google.com"
# Expected: Bing content (not Google)
```

> **E2E verified:** Response body contains `bing.com` content (Microsoft Bing search page) instead of Google.

### Test 6: Rewrite — Path rewrite

Rewrite the path of requests:

```json
{
  "name": "rewrite-path",
  "ruleType": "Fqdn",
  "match": { "host": "httpbin.org", "path": "/get" },
  "action": {
    "actionType": "Rewrite",
    "rewrite": { "scheme": "https", "host": "httpbin.org", "path": "/ip" }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://httpbin.org/get"
# Expected: the /ip response (origin IP) instead of the /get response
```

### Test 7: Connectivity baseline (no policy)

Without any egress policy attached, verify baseline connectivity:

```bash
azd ai agent invoke "test connectivity"
# Expected: all three targets (httpbin.org, example.com, google.com) return 200
```

> **E2E verified:** All three hosts return 200 when no egress policy is attached.

## Advanced test scenarios

These scenarios test edge cases and rule interactions. Each requires creating a policy with multiple rules — use the CogSvc RP `raiPolicies` API (`2026-05-15-preview`).

### Test 8: First-match rule ordering

Rule order matters — the egress proxy uses first-match semantics. Create a policy with two rules for the same host, in a specific order:

```json
{
  "properties": {
    "basePolicyName": "Microsoft.DefaultV2",
    "egressPolicy": {
      "mode": "Enforced",
      "defaultAction": "Deny",
      "rules": [
        {
          "name": "deny-httpbin-ip",
          "ruleType": "Fqdn",
          "match": { "host": "httpbin.org", "path": "/ip" },
          "action": { "actionType": "Deny" }
        },
        {
          "name": "allow-httpbin-all",
          "ruleType": "Fqdn",
          "match": { "host": "httpbin.org" },
          "action": { "actionType": "Allow" }
        }
      ]
    }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://httpbin.org/get"
# Expected: 200 (matches allow-httpbin-all)

azd ai agent invoke "test egress to https://httpbin.org/ip"
# Expected: 403 (matches deny-httpbin-ip first)
```

### Test 9: Multiple transforms in one rule

Apply Insert, Set, and Remove in a single Transform rule:

```json
{
  "name": "multi-transform",
  "ruleType": "Fqdn",
  "match": { "host": "httpbin.org" },
  "action": {
    "actionType": "Transform",
    "headers": [
      { "name": "X-Custom-Inserted", "value": "hello", "operation": "Insert" },
      { "name": "User-Agent", "value": "policy-agent/1.0", "operation": "Set" },
      { "name": "X-Test-Marker", "operation": "Remove" }
    ]
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke -o "raw" "test headers to https://httpbin.org/headers"
# Expected: X-Custom-Inserted is "hello", User-Agent is "policy-agent/1.0",
# and X-Test-Marker does not appear
```

### Test 10: Combined Rewrite + Transform (first-match)

When a Rewrite rule and Transform rule both could match, only the first one applies:

```json
{
  "properties": {
    "basePolicyName": "Microsoft.DefaultV2",
    "egressPolicy": {
      "mode": "Enforced",
      "defaultAction": "Deny",
      "rules": [
        {
          "name": "rewrite-to-bing",
          "ruleType": "Fqdn",
          "match": { "host": "www.google.com" },
          "action": {
            "actionType": "Rewrite",
            "rewrite": { "scheme": "https", "host": "www.bing.com" }
          }
        },
        {
          "name": "transform-httpbin",
          "ruleType": "Fqdn",
          "match": { "host": "httpbin.org" },
          "action": {
            "actionType": "Transform",
            "headers": [
              { "name": "X-Policy-Tag", "value": "tagged", "operation": "Insert" }
            ]
          }
        }
      ]
    }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://www.google.com"
# Expected: Bing content (rewrite applied)

azd ai agent invoke -o "raw" "test headers to https://httpbin.org/headers"
# Expected: X-Policy-Tag is "tagged" (transform applied)

azd ai agent invoke "test egress to https://example.com"
# Expected: 403 (no matching rule, default Deny)
```

### Test 11: Deny-all (no rules)

A policy with `defaultAction=Deny` and no rules blocks everything:

```json
{
  "properties": {
    "basePolicyName": "Microsoft.DefaultV2",
    "egressPolicy": {
      "mode": "Enforced",
      "defaultAction": "Deny",
      "rules": []
    }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test connectivity"
# Expected: all three targets return 403
```

> **Note:** This scenario requires full traffic inspection, which the Foundry platform enables automatically when `mode=Enforced` and `defaultAction=Deny`.

### Test 12: Wildcard host matching

Test that `*.org` matches subdomains:

```json
{
  "properties": {
    "basePolicyName": "Microsoft.DefaultV2",
    "egressPolicy": {
      "mode": "Enforced",
      "defaultAction": "Deny",
      "rules": [
        {
          "name": "allow-dot-org",
          "ruleType": "Fqdn",
          "match": { "host": "*.org" },
          "action": { "actionType": "Allow" }
        }
      ]
    }
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://httpbin.org/get"
# Expected: 200 (matches *.org)

azd ai agent invoke "test egress to https://example.com"
# Expected: 403 (.com is not matched)
```

## Audit mode testing

In **Audit mode**, the egress proxy evaluates rules and logs decisions without enforcing deny rules. Traffic that would be blocked in Enforced mode passes through in Audit mode, enabling observability without impacting the agent.

> ✅ **Audit passthrough is live (July 2026).** In Audit mode the Foundry platform logs deny decisions without enforcing them, so denied traffic passes through while Transform and Rewrite rules still apply normally.

### Test 13: Audit deny rules (passthrough)

```json
{
  "properties": {
    "basePolicyName": "Microsoft.DefaultV2",
    "egressPolicy": {
      "defaultAction": "Deny",
      "mode": "Audit",
      "rules": [
        {
          "name": "allow-httpbin", "ruleType": "Fqdn",
          "match": { "host": "httpbin.org" },
          "action": { "actionType": "Allow" }
        },
        {
          "name": "deny-example", "ruleType": "Fqdn",
          "match": { "host": "example.com" },
          "action": { "actionType": "Deny" }
        }
      ]
    }
  }
}
```

**Verify with `azd` (audit passthrough — deny rules not enforced):**
```bash
azd ai agent invoke "test egress to https://httpbin.org/get"
# Expected: 200 (allowed by rule)

azd ai agent invoke "test egress to https://example.com"
# Expected: 200 (deny is not enforced in audit)

azd ai agent invoke "test egress to https://www.google.com"
# Expected: 200 (default deny is not enforced in audit)
```

### Test 14: Audit allow-all

With an allow-all rule under audit mode, all hosts should be reachable:

```bash
azd ai agent invoke "test connectivity"
# Expected: all targets return 200 (allow rules work normally in audit)
```

### Test 15: Audit vs Enforced comparison

Deploy the same deny policy under both modes and verify the difference:

```bash
# Invoke after deploying the policy in Audit mode.
azd ai agent invoke "test egress to https://example.com"
# Expected: 200 (passthrough)

# Invoke again after deploying the same policy in Enforced mode.
azd ai agent invoke "test egress to https://example.com"
# Expected: 403 (blocked)
```

### How to observe audit decisions

- Verify the `X-Adc-Proxy: 1` response header — this appears in the response headers the `egress_test` tool returns (visible in the agent's invoke output); it confirms traffic went through the proxy
- In Audit mode, verify NO `403` responses for denied hosts — proves passthrough is working
- For full audit decision logs, enable the `NetworkEgressDecisions` telemetry data type on the agent's observability configuration (exported via OTLP); see [Monitor hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/metrics)

> **Important:** Use `basePolicyName: "Microsoft.DefaultV2"` (not `"Microsoft.Default"`). The wrong base policy name will cause policy creation errors.

## ManagedIdentityRef testing

This section covers testing `managedIdentityRef` — an egress Transform capability where the proxy injects an Azure AD token, acquired from the agent's managed identity, into outbound requests (so the agent code never handles credentials).

The egress proxy injects Azure AD tokens from the deployed agent's instance identity into outbound requests. The agent code never handles credentials — the proxy acquires a token for the specified resource audience and injects it as a request header.

### Prerequisites

1. **Deploy the agent, then find its instance identity principal ID:**
   ```bash
   azd ai agent show --output json \
     | jq -r '.instance_identity.principal_id'
   ```

2. **Create a storage account and container:**
   ```bash
   az storage account create -n myteststorage -g my-rg --sku Standard_LRS
   az storage container create -n egress-test --account-name myteststorage
   ```

3. **Assign RBAC to the agent instance identity:**
   ```bash
   az role assignment create \
     --assignee-object-id <principalId> \
     --assignee-principal-type ServicePrincipal \
     --role "Storage Blob Data Contributor" \
     --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/myteststorage"
   ```

### Test 16: MI token injection to Azure Blob Storage

Create a policy that injects an MI token for the `https://storage.azure.com/` resource:

```json
{
  "name": "mi-storage-token", "ruleType": "Fqdn",
  "match": { "host": "myteststorage.blob.core.windows.net" },
  "action": {
    "actionType": "Transform",
    "headers": [
      {
        "name": "Authorization",
        "operation": "Set",
        "valueRef": {
          "managedIdentityRef": {
            "resource": "https://storage.azure.com/",
            "format": "Bearer {value}"
          }
        }
      },
      {
        "name": "x-ms-version",
        "value": "2023-11-03",
        "operation": "Set"
      }
    ]
  }
}
```

**Verify with `azd`:**
```bash
azd ai agent invoke "test egress to https://myteststorage.blob.core.windows.net/egress-test?restype=container&comp=list"
# Expected: 200 with an XML blob listing (proxy injected the MI token)
```

### Test 17: MI token scoping

The MI token is only injected for hosts matching the Transform rule. Requests to other hosts (e.g., httpbin.org) should NOT carry a Bearer token:

```bash
azd ai agent invoke -o "raw" "test headers to https://httpbin.org/headers"
→ Echoed headers should NOT contain "Authorization: Bearer ..."
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────┐
│  User /      │────▸│  Foundry      │────▸│  Egress Proxy   │────▸│ Internet │
│  Playground  │◂────│  Hosted Agent │◂────│  (Egress Sidecar)│◂────│          │
└─────────────┘     └──────────────┘     └─────────────────┘     └──────────┘
                         │                       │
                         │ main.py               │ Applies:
                         │ 1. LLM (gpt-4.1)       │ • Allow/Deny rules
                         │    routes to tool      │ • Header transforms
                         │ 2. egress_test()       │ • Host/path rewrites
                         │    aiohttp GET/POST    │ • TLS inspection (Full)
                         ▼                       ▼
                    Agent Framework         RAI Egress Policy
                    + ResponsesHostServer   (CogSvc RP)
```

The egress proxy runs as a sidecar container alongside the hosted agent. All outbound HTTP/HTTPS traffic from the agent is routed through the proxy, which applies the egress policy rules before forwarding the request to the internet.

- **Partial inspection** (default/audit): proxy sees SNI + Host header only
- **Full inspection** (enforced + rules): TLS MITM — proxy terminates TLS and can inspect/modify headers and paths

## Troubleshooting

### Pre-deployed agent image required

This sample requires a pre-built container image pushed to your project's ACR. The `azd deploy` or VS Code deploy flow builds and pushes this automatically. If deploying manually:

```bash
# Build the image
docker build -t egress-test-agent:latest src/agent-framework-egress-control-responses

# Get ACR login server (from your Foundry project)
ACR_SERVER=$(az cognitiveservices account show --ids "<account-id>" \
  --query "properties.endpoints.containerRegistryServer" -o tsv)

# Push
az acr login --name "${ACR_SERVER%%.*}"
docker tag egress-test-agent:latest "$ACR_SERVER/egress-test-agent:latest"
docker push "$ACR_SERVER/egress-test-agent:latest"
```

### Permissions checklist

| Permission | Scope | Who needs it | Why |
|-----------|-------|-------------|-----|
| Cognitive Services Contributor | CogSvc account | Your user | Create/manage egress policies and agent versions |
| Storage Blob Data Contributor | Storage account | Deployed agent instance identity | For MI token injection tests (Test 16–17) |
| AcrPush | Container Registry | Your user | Push agent images |

### Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Policy creation failed` | Wrong `basePolicyName` | Use `"Microsoft.DefaultV2"` (not `"Microsoft.Default"`) |
| `Version not active after 100s` | Image not found in ACR | Verify image digest/tag, check ACR permissions |
| `429 rate_limit` or `rate limit exceeded` | Too many LLM calls | Increase `INVOKE_DELAY` env var (default: 15s); scenario invocations retry transient throttling |
| `AuthorizationFailure` on storage | Agent identity lacks RBAC | Assign `Storage Blob Data Contributor` to the deployed agent's `instance_identity.principal_id` |
| `AADSTS500011` for storage | Scope form used as the resource audience | Use `https://storage.azure.com/`, not `https://storage.azure.com/.default` |
| `InvalidAuthenticationInfo` on storage | Wrong format placeholder | Use `Bearer {value}`; `{token}` is not substituted |
| Session creation error with audit policy | Missing `ruleType: "Fqdn"` on rules | Every rule must include `"ruleType": "Fqdn"` |

### Known bugs

| Bug | Description | Workaround |
|-----|-------------|------------|
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` null on version update | When updating the guardrail (RAI policy) on an existing agent version, the environment variable may be null at runtime causing the agent to crash. | The agent now defaults to `gpt-4.1` when the env var is missing. If using a different model, set it explicitly in the agent version definition. |

### Audit mode without OTLP

Until platform OTLP support for `NetworkEgressDecisions` telemetry is generally available, you can verify audit mode by:
1. **Absence of 403**: denied hosts should return 200 (not 403)
2. **`X-Adc-Proxy: 1` header**: confirms requests went through the proxy
3. **Comparison test**: deploy the same policy as Enforced → denied hosts return 403

## Next steps

- [Egress controls overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/egress-controls) — learn about managed egress policies
- [Basic hosted agent](../01-basic/) — minimal agent sample
- [Add tools to your agent](../02-tools/) — sample with local tool functions
- [Downstream Azure services](../10-downstream-azure/) — sample using Azure managed identity
