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
        credential, "https://ai.azure.com/.default"
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

- Python 3.13+ (the container image and `azure.yaml` hosted runtime both use Python 3.13)
- `az login` / `azd auth login`
- An existing Foundry project with an existing Claude model deployment and an existing toolbox

### Option 1: Azure Developer CLI (`azd`)

```bash
mkdir my-claude-toolbox-agent && cd my-claude-toolbox-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/25-claude-foundry-toolbox/azure.yaml
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
2. In the service project directory, install uv and sync the committed lockfile:
   ```bash
   cd src/claude-foundry-toolbox-responses
   pipx install uv==0.11.7
   uv sync --frozen --python 3.13
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
   azd env get-value AZURE_SUBSCRIPTION_ID
   azd env get-value AZURE_RESOURCE_GROUP
   azd env get-value AZURE_AI_ACCOUNT_NAME
   ```
3. Assign the `Foundry User` role at **account** scope (role definition ID `53ca6127-db72-4b80-b1b0-d745d6d5456d`) using the values from the active azd environment and the principal ID — do not leave the placeholders below unreplaced:
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

## Cloud E2E coverage

This sample is excluded from the shared cloud E2E matrix because that matrix supplies
a shared non-Claude model deployment and does not grant the runtime identity the
account-scope `Foundry User` role required by this sample. The behavior contract
defines the expected answer and toolbox-call evidence for a separately configured
test environment with an existing Claude deployment and toolbox.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [`04-foundry-toolbox`](../04-foundry-toolbox/) — an OpenAI-model counterpart of this pattern, including full toolbox-creation instructions
- [`claude-agent-sdk`](../../../bring-your-own/invocations/claude-agent-sdk/) — a minimal Claude Agent SDK sample with the same account-scope RBAC requirement, without Foundry Toolbox
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
