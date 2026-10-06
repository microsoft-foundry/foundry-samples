# Claude + Foundry Toolbox (Responses Protocol)

**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that runs an **Anthropic Claude** model through Microsoft Foundry (`AnthropicFoundryClient`) and uses **Foundry Toolbox** for tool discovery (`FoundryToolbox`), hosted with the **Responses protocol**. This sample reuses an **existing** Foundry project, an **existing** Claude model deployment, and an **existing** toolbox (for example one exposing built-in web search) — it does not provision any of those by default.

## How it works

The agent uses `AnthropicFoundryClient` from `agent_framework.foundry` to talk to a Claude deployment through Foundry, and `FoundryToolbox` from `agent_framework_foundry_hosting` to discover and invoke tools from an existing toolbox over MCP. See [main.py](src/claude-foundry-toolbox-responses/main.py) for the full implementation:

```python
credential = DefaultAzureCredential()

client = AnthropicFoundryClient(
    resource=os.environ["AZURE_AI_RESOURCE_NAME"],
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    azure_ad_token_provider=get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    ),
)

toolbox = FoundryToolbox(credential)

agent = Agent(
    client=client,
    instructions="Use configured web search and cite grounded URLs; report tool errors honestly.",
    tools=toolbox,
    default_options={"max_tokens": 2048},
)

await ResponsesHostServer(agent).run_async()
```

### Two different token scopes

This agent talks to two different Foundry surfaces, and each uses its own token scope. Don't reuse one bearer-token provider for both:

| Component | Scope | Why |
|-----------|-------|-----|
| `AnthropicFoundryClient` (model inference) | `https://cognitiveservices.azure.com/.default` | Claude inference runs through the Cognitive Services / AI Services data-plane API. |
| `FoundryToolbox` (tool discovery/invocation) | `https://ai.azure.com/.default` | The toolbox's MCP endpoint is a Foundry (`ai.azure.com`) resource, not a Cognitive Services one. |

`FoundryToolbox(credential)` negotiates its own scope internally from the `DefaultAzureCredential` you pass in; you only need to construct the model client's token provider with the Cognitive Services scope explicitly, as shown above.

### `store` is not supported by Anthropic

Unlike the OpenAI-based samples in this repo (which commonly set `default_options={"store": False}`), Anthropic's API has no `store` option. This sample instead caps generation with `default_options={"max_tokens": 2048}`. Passing `store` to an Anthropic-backed agent is a no-op at best and may raise a validation error depending on SDK version — don't carry it over from OpenAI-based samples.

### Model deployment name is user-configured

`AZURE_AI_MODEL_DEPLOYMENT_NAME` must be the name of **your** existing Claude deployment in your Foundry resource — it is never hardcoded in this sample. Set it to match whatever you named the deployment when you created it (e.g. via the Foundry portal or `az cognitiveservices account deployment create`).

## Reusing an existing toolbox

This sample expects a toolbox to already exist in your Foundry project (for example one that exposes the built-in web search tool) and does not create one. Set `TOOLBOX_ENDPOINT` to that toolbox's versioned MCP endpoint:

```bash
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<toolbox-name>/versions/<version>/mcp?api-version=v1"
```

If you don't yet have a toolbox, see [`04-foundry-toolbox`](../04-foundry-toolbox/) for how to create one with `azd ai toolbox create`, including the [built-in tools guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/built-in-tools.md) for web search.

`FoundryToolbox` authenticates every request with the credential and transparently forwards the platform's per-request call-id (`x-agent-foundry-call-id`) to the toolbox, so toolbox-side logs can be correlated back to the originating agent request.

## Running the agent

### Prerequisites

- Python 3.12+ (the container image uses `python:3.12-slim`; `azure.yaml` declares the hosted runtime as `python_3_13`)
- `az login` / `azd auth login`
- An existing Foundry project with an existing Claude model deployment and an existing toolbox

### Option 1: Azure Developer CLI (`azd`)

```bash
mkdir my-claude-toolbox-agent && cd my-claude-toolbox-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/23-claude-foundry-toolbox/azure.yaml
```

Follow the prompts to select your existing Foundry project. Then set the environment variables for your existing deployment and toolbox:

```bash
azd env set AZURE_AI_ACCOUNT_NAME "<your-foundry-resource-name>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<your-claude-deployment-name>"
azd env set TOOLBOX_ENDPOINT "<your-toolbox-mcp-endpoint>"
```

Run locally:

```bash
azd ai agent run
```

Invoke locally:

```bash
azd ai agent invoke --local "Search the web for the latest Microsoft Foundry announcement and cite your source."
```

Deploy to Foundry:

```bash
azd deploy
```

> After deployment, configure RBAC — see [⚠️ RBAC configuration after deployment](#️-rbac-configuration-after-deployment) below. This is required before Claude inference will succeed.

Invoke the deployed agent:

```bash
azd ai agent invoke "Search the web for the latest Microsoft Foundry announcement and cite your source."
```

### Option 2: VS Code (Foundry Toolkit)

1. Install the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension (and the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack for debugging).
2. Create/select a Python virtual environment, then install dependencies:
   ```bash
   pip install uv
   uv pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in `AZURE_AI_RESOURCE_NAME`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and `TOOLBOX_ENDPOINT` for your existing project/deployment/toolbox.
4. Press **F5** to start the agent; the **Agent Inspector** opens automatically.
5. To deploy: Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Deploy Hosted Agent**.

## ⚠️ RBAC configuration after deployment

**IMPORTANT!** After `azd deploy` (or any deployment path), you **must** assign the `Foundry User` role at the **account scope** — not just the project scope — to the agent's runtime identity, or Claude inference calls will fail.

### Why

Microsoft Foundry authorizes at two levels:

1. **Project scope** — controls agent orchestration and project operations.
2. **Account scope** — controls model inference API calls.

Project-scope-only `Foundry User` is **not sufficient**: it fails Claude inference with an error indicating the missing action `Microsoft.CognitiveServices/accounts/AIServices/providers/action` (surfaced as an authorization error from the model call, not from agent startup).

### Steps

1. Get the agent's runtime principal ID:
   ```bash
   azd ai agent show
   ```
   Look for `instance_identity.principal_id` in the output.
2. Get your subscription ID, resource group, and account name:
   ```bash
   az account show --query id -o tsv
   az group list --query "[0].name" -o tsv
   azd env get-values   # find AZURE_AI_ACCOUNT_NAME in the output
   ```
3. Assign the `Foundry User` role at **account** scope (role definition ID `53ca6127-db72-4b80-b1b0-d745d6d5456d`) using your actual principal ID, subscription ID, resource group, and account name — do not leave the placeholders below unreplaced:
   ```bash
   az role assignment create \
     --assignee-object-id <PRINCIPAL_ID> \
     --assignee-principal-type ServicePrincipal \
     --role "Foundry User" \
     --scope /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<ACCOUNT_NAME>
   ```
4. Verify both assignments exist (project scope and account scope):
   ```bash
   az role assignment list --assignee-object-id <PRINCIPAL_ID> --all -o table
   ```
5. Wait 2-5 minutes for RBAC propagation, then test:
   ```bash
   azd ai agent invoke --new-session "Search the web for the latest Microsoft Foundry announcement and cite your source."
   ```

See [`claude-agent-sdk`'s RBAC section](../../../bring-your-own/invocations/claude-agent-sdk/README.md#️-critical-rbac-configuration-after-deployment) for the full step-by-step reference this guidance is adapted from (including troubleshooting for a persistent 401).

## Verified prior deployed behavior (not reproduced by this turn's validation)

A prior deployment of this same code/configuration pattern (1 CPU / 2Gi, `python_3_13` remote build, Responses protocol `2.0.0`) was exercised end-to-end against web search after completing the RBAC steps above, and confirmed:

- An actual `function_call` for the web search tool, with a matching `function_call_output` (not just a terminal `response.completed`/HTTP 200 — those alone don't prove the tool call executed or returned real results).
- 34 citations with grounded Microsoft Learn URLs in the final response.

**This repository turn did not re-run that deployment or re-verify it live.** The checks performed for this sample addition were offline only (file structure, syntax/compile checks, and YAML well-formedness) — see [Offline validation performed](#offline-validation-performed-this-turn). Treat the bullets above as a record of prior verified behavior for this code pattern, not as a claim that this exact checked-in copy was itself redeployed and re-tested.

### Known streaming quirk: leading `{}` in function-call arguments

During that prior verified deployment, the streamed `output_item.done` event's function-call `arguments` field was observed to start with an extra, spurious `{}` prefix (i.e. the wire value looks like `"{}{...real JSON...}"`). Naively concatenating/parsing that field as JSON directly fails. The underlying tool call still executed correctly and returned a valid result — this is a presentation/streaming artifact in the emitted arguments string, not a sign that the call failed.

If you add any client-side logic that parses streamed function-call arguments, strip or tolerate this leading `{}` rather than treating the resulting parse error as a tool failure. Any verifier you add for this sample should check for the presence of a matching `function_call` / `function_call_output` pair and should **not** silently repair or normalize this artifact — call it out when detected so it stays visible rather than being hidden by "successful" tolerant parsing.

## Offline validation performed this turn

Because no new deployment or cloud mutation was authorized for this turn, validation was limited to:

- File/directory structure review against the [`04-foundry-toolbox`](../04-foundry-toolbox/) and [`claude-agent-sdk`](../../../bring-your-own/invocations/claude-agent-sdk/) precedents.
- Python syntax/compile checks on `main.py`.
- YAML well-formedness checks on `azure.yaml`.

No live Foundry resources were called, no deployment was performed, and no RBAC/role assignment commands were executed as part of this turn.

## Optional: Work IQ Mail toolbox (not configured by default, not verified end-to-end)

This sample does **not** include Mail tooling by default. If you want to add a separately configured **Work IQ Mail** toolbox as an additional tool source, be aware of the following before doing so:

- It requires catalog authentication consent and a specific Microsoft 365 license (see below) — this is **not** something you get "for free" alongside the default web-search toolbox.
- If you add it, restrict `allowed_tools` to an explicitly discovered, read-only tool name only. Discovery for this connector surfaced a name pattern of the form `<server_label>___SearchMessagesQueryParameters`, which accepts a single `queryParameters` string argument (OData-style), e.g. a minimal read-only query such as `?$top=1&$select=isRead`.
- **Do not** blindly expose the full Mail toolbox — it also contains send/delete-capable tools. Any `allowed_tools` allowlist must be deliberately curated by you based on what discovery actually returns, not assumed.
- **This was not verified to work end-to-end.** Tool discovery succeeded, but the actual deployed execution of the read-only search tool **failed** a license check requiring the `M365_COPILOT_BUSINESS_CHAT` service plan. The model only saw a generic `Error: Function failed.`; the specific license-related cause was only visible in hosted agent logs, not in the model-facing error. Do not claim or assume Mail e2e success from this sample — no email was successfully sent, read, or mutated, and no live mailbox testing passed.
- No email sending or mutation operations should ever be allow-listed for a general-purpose sample like this one.
- A managed-OAuth connection attempt on an internal test environment failed connector resolution during this investigation. Don't present the experimental `user-entra-token` auth mode as a universally supported setup path for this connector — validate connector-specific auth support before relying on it.

Given the above, treat Mail integration as a documented possibility for your own environment, not a supported or tested part of this sample.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [`04-foundry-toolbox`](../04-foundry-toolbox/) — an OpenAI-model counterpart of this pattern, including full toolbox-creation instructions
- [`claude-agent-sdk`](../../../bring-your-own/invocations/claude-agent-sdk/) — a minimal Claude Agent SDK sample with the same account-scope RBAC requirement, without Foundry Toolbox
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
