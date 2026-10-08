<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# LangGraph Toolbox Agent (Responses Protocol)

A LangGraph ReAct agent that connects to an **toolbox in Microsoft Foundry** via MCP and
serves responses over the Foundry Responses Protocol.

## How It Works

1. On startup the agent calls `client.get_tools()` against the Toolbox MCP endpoint.
2. A `create_react_agent` is built from the loaded tools and an Azure OpenAI LLM.
3. Incoming requests are handled by `ResponsesAgentServerHost` on port `8088`.
4. The agent is initialized **lazily** (once, on the first request) and reused for all
   subsequent turns — the MCP client is kept alive to prevent session garbage-collection.
5. If a toolbox tool requires OAuth consent, the MCP server returns error code `-32006`.
   The agent detects this, logs the consent URL, and surfaces it to the caller via a
   fallback tool instead of crashing.

## Prerequisites

- Python 3.12+
- A Microsoft Foundry project with a toolbox created from the bundled
  [`toolbox.yaml`](src/toolbox-langgraph/toolbox.yaml) — see [Create the toolbox with `azd ai`](#4-create-the-toolbox-with-azd-ai)
- Azure CLI installed and logged in:

  ```bash
  az login
  ```

## Quick Start (Local)

**Linux/macOS:**
```bash
cd src/toolbox-langgraph

# 1. Copy and fill in the environment file
cp .env.example .env  # skip if .env already exists
# Edit .env — set FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME,
#              and TOOLBOX_ENDPOINT at minimum

# 2. Install dependencies
pipx install uv==0.11.7
uv sync --frozen --python 3.12

# 3. Start the agent
uv run --no-sync python main.py

# 4. Invoke
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What tools do you have?"}'
```

**Windows (PowerShell):**
```powershell
cd src/toolbox-langgraph

# 1. Copy and fill in the environment file
Copy-Item .env.example .env  # skip if .env already exists
# Edit .env — set FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME,
#              and TOOLBOX_ENDPOINT at minimum

# 2. Install dependencies
pipx install uv==0.11.7
uv sync --frozen --python 3.12

# 3. Start the agent
uv run --no-sync python main.py

# 4. Invoke
Invoke-RestMethod -Method POST http://localhost:8088/responses `
  -ContentType "application/json" `
  -Body '{"input": "What tools do you have?"}'
```

<details>
<summary><h3>Using the Foundry Toolkit VS Code Extension</h3></summary>

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

**Set up the Python virtual environment**

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/toolbox-langgraph

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/toolbox-langgraph/.venv`.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/toolbox-langgraph`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

</details>

## Deploy as a Hosted Agent

### Setup

#### 1. Install Azure Developer CLI (`azd`)

**Linux/macOS:**
```bash
curl -fsSL https://aka.ms/install-azd.sh | bash
```

**Windows (PowerShell):**
```powershell
winget install microsoft.azd
```

See the [full installation docs](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) for other options.

#### 2. Install the unified Foundry CLI extension bundle

```bash
# If you previously installed individual extensions, uninstall them first:
#   azd ext uninstall azure.ai.agents
#   azd ext uninstall azure.ai.toolboxes

# Install the unified bundle (provides azd ai agent, connection, inspector,
# project, routine, skill, and toolbox). Requires azd 1.27.1 or later.
azd ext install microsoft.foundry
```

To upgrade the extension later:

```bash
azd ext upgrade microsoft.foundry
```

#### 3. Log in to Azure

```bash
azd auth login
```

#### 4. Create the toolbox with `azd ai`

> [!TIP]
> If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, the following skill references describe the same endpoint contract (env var, headers, MCP protocol, citation patterns, and troubleshooting) that the agent must implement:
>
> - [Toolbox reference](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/foundry-agent/create/references/toolbox-reference.md) — endpoint format, MCP protocol, OAuth consent handling, citation patterns, and troubleshooting.
> - [Use toolbox in a hosted agent](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md) — endpoint resolution, env-var contract, payload shape, code integration patterns, and tracing.

This sample exposes the toolbox tools to a LangGraph ReAct loop. `azure.yaml`
provisions `toolbox-langgraph-tools`, containing `web_search` plus the public
Microsoft Learn MCP server, when you deploy the sample. For local development
against an existing project, you can instead create the same toolbox from the
bundled [`toolbox.yaml`](src/toolbox-langgraph/toolbox.yaml):

```bash
azd ai toolbox create my-toolbox --from-file ./src/toolbox-langgraph/toolbox.yaml
```

The first version becomes the default automatically. Manage with `azd ai toolbox list`, `azd ai toolbox show my-toolbox`, `azd ai toolbox version list my-toolbox`, and `azd ai toolbox delete my-toolbox --force`.

To stage incremental changes safely, use `azd ai toolbox connection add/remove` and `azd ai toolbox skill add/list/remove` &mdash; each creates a new toolbox version that carries forward existing connections and skills but **doesn't** change the default. Promote a version with `azd ai toolbox publish my-toolbox <version>` when you're ready to make it active.

`azd ai toolbox create` prints the toolbox's versioned MCP endpoint. For local
runs, either set `TOOLBOX_ENDPOINT` to that endpoint or set `TOOLBOX_NAME` to
the created toolbox name.

> [!NOTE]
> To attach tools that need credentials (MCP servers with API keys or OAuth, Azure AI Search, Bing Custom Search, and more), create a project connection with `azd ai connection create` and reference it from `toolbox.yaml` by `project_connection_id`.

#### 5. Fix git CRLF setting (Windows only)

```bash
git config --global core.autocrlf false
```

### Quick Start (Deploy with azd)

> **IMPORTANT:** The `-m` (or `--manifest`) flag is **required** for `azd ai agent init`.
> It tells the command where to find your agent definition and source files.
>
> `-m` can point to either:
> - **A specific `azure.yaml` file** — init copies all files from the same directory as the manifest
> - **A folder containing `azure.yaml`** — init copies all files from that folder

```bash
# 1. Create a new directory and initialize the agent project
mkdir my-langgraph-agent && cd my-langgraph-agent
PROJECT_ID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
azd ai agent init \
  -m /path/to/samples/python/hosted-agents/bring-your-own/responses/langgraph-toolbox/azure.yaml \
  --project-id $PROJECT_ID \
  --no-prompt \
  -e my-env

# 2. Set required environment variables
azd env set enableHostedAgentVNext "true" -e my-env
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "gpt-4o" -e my-env  # must match the deployment name in azure.yaml

# 3. Provision infrastructure and deploy the container
azd up -e my-env

# 4. Invoke the deployed agent (run from the scaffolded project directory)
azd ai agent invoke --new-session "What tools do you have?" --timeout 120
```

### Post-Init Checklist

After `azd ai agent init`, perform these steps before `azd up` will work:

| # | Action | Why |
|---|--------|-----|
| 1 | `azd env set enableHostedAgentVNext "true"` | Without this, container health probes fail |
| 2 | Edit `src/<agent>/agent.yaml`: replace all `${{VAR}}` with `${VAR}` | Init scaffolds broken double-brace syntax that is NOT resolved at deploy time |
| 3 | Verify `azure.yaml` uses **flat format** (`kind: hosted` at root) | The nested `template:` format silently fails during deploy |
| 4 | `azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<deployment-name>"` | Must match the deployment `name` in `azure.yaml`; platform injection is unreliable without this (container crashes on startup) |
| 5 | Verify `main.py` checks `FOUNDRY_PROJECT_ENDPOINT` first | Platform injects this var, NOT `AZURE_AI_PROJECT_ENDPOINT` |
| 6 | **If using existing project with AppInsights already connected:** `azd env set ENABLE_MONITORING "false"` | Provision fails with duplicate App Insights connection error |
| 7 | **If model region ≠ RG region:** edit generated `infra/main.parameters.json` — change `aiDeploymentsLocation` value from `${AZURE_LOCATION}` to `${AZURE_AI_DEPLOYMENTS_LOCATION}`, then `azd env set AZURE_AI_DEPLOYMENTS_LOCATION "<region>"` | Init templates map model deployment location to `AZURE_LOCATION` which is wrong when model is in a different region |

### What `azd ai agent init` Does

`azd ai agent init` copies all source files (main.py, Dockerfile, pyproject.toml, uv.lock, etc.) **verbatim** from the manifest directory into `src/<agent-name>/` in the scaffolded project. It does NOT generate or modify main.py — it copies the exact file from your manifest.

The init command also:
- Creates `azure.yaml` with service config, connections, and toolbox definitions
- Creates `infra/` directory with Bicep templates
- Creates `.azure/<env>/.env` with environment variables

### Project Structure

After `azd ai agent init`, you get:

```
my-project/
├── .azure/
│   └── <env-name>/
│       ├── .env              # Environment variables (auto-populated by azd)
│       └── config.json       # Subscription + location config
├── infra/
│   ├── main.bicep            # Top-level Bicep template
│   ├── main.parameters.json  # Parameters (references .env values)
│   └── core/ai/
│       ├── ai-project.bicep  # Project + connection deployment
│       └── connection.bicep  # Connection resource template
├── src/
│   └── <agent-name>/
│       ├── agent.yaml        # Agent definition (env vars, protocols)
│       ├── main.py           # Agent code
│       ├── Dockerfile        # Container build
│       ├── pyproject.toml     # Project and direct dependencies
│       └── uv.lock            # Reproducible dependency lock
└── azure.yaml                # azd service + toolbox configuration
```

> **Tip:** `azd ai agent invoke` must be run from the scaffolded project directory
> (the directory where `azure.yaml` was created by `azd ai agent init`).  
> The `--timeout 120` flag is recommended — agent cold starts can take up to 60 seconds.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | **Yes** | Project endpoint URL — platform-injected at runtime |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | **Yes** | Model deployment name (e.g. `gpt-4.1`) |
| `TOOLBOX_ENDPOINT` | No | Full toolbox MCP endpoint URL. Takes precedence when set. |
| `TOOLBOX_NAME` | **Yes, unless `TOOLBOX_ENDPOINT` is set** | Toolbox name. The deployed sample uses the provisioned `toolbox-langgraph-tools`. |

Set `TOOLBOX_ENDPOINT` to the full MCP URL. Two forms are supported:
```
# Latest version:
https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<name>/mcp?api-version=v1

# Pinned to a specific version:
https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<name>/versions/<version>/mcp?api-version=v1
```
The version number is the integer toolbox version (e.g. `1`). Use the versioned form to pin to a known-good version.

## Supported Toolbox Tools

See [../SUPPORTED_TOOLBOX_TOOLS.md](../SUPPORTED_TOOLBOX_TOOLS.md) for all supported
tool and auth types. For runnable SDK creation examples, see
[../sample_toolboxes_crud.py](../sample_toolboxes_crud.py).

## Protocol

This sample uses the **Responses Protocol** (`azure-ai-agentserver-responses`):
- OpenAI-compatible `/responses` endpoint on port `8088`
- Streaming SSE output
- Multi-turn conversation (history fetched automatically)
- 240-second per-request timeout

## Troubleshooting

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error calling Azure OpenAI: Error code: 401 - {'error': {'code': 'PermissionDenied', 'message': 'The principal <principal-id> lacks the required data action Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action to perform POST /openai/deployments/{deployment-id}/chat/completions operation.'}}
```

This sample uses its own LangChain (`ChatOpenAI`) client to call the project's Chat Completions endpoint directly, so the agent's managed identity needs the **Foundry User** role on the project — an ["Agent access beyond defaults"](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-permissions#agent-access-beyond-defaults) case:

- **Foundry User**

Use the Azure CLI to assign it:

```bash
# Set your variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="<your-resource-group>"
ACCOUNT_NAME="<your-ai-foundry-account-name>"
PROJECT_NAME="<your-ai-foundry-project-name>"
PRINCIPAL_ID="<principal-id-from-error-message>"

# Assign "Foundry User" role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Foundry User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME/projects/$PROJECT_NAME"
```

> **Note:** It may take a few minutes for role assignments to propagate. Retry the request after waiting.

### Agent starts but returns no tools

Check that `TOOLBOX_NAME` identifies a toolbox in the configured project, or
that `TOOLBOX_ENDPOINT` is set to a valid URL containing `?api-version=v1`.

### OAuth consent required

If a toolbox connection requires OAuth, the agent logs:
```
OAuth consent required. Open the following URL in a browser to authorize...
```
Open the URL, complete the OAuth flow, then restart the agent. Until consent is granted,
the agent returns a `oauth_consent_required` tool message to callers.

### Tool call failures don't crash the agent

`handle_tool_error = True` is set on all loaded tools, so MCP tool errors are returned
as tool messages rather than raising exceptions that would break conversation state.

### Tool schemas rejected by OpenAI

The agent sanitizes malformed schemas from MCP servers (missing `properties` on
`object`-type schemas). If you see `400 Invalid tool schema` errors, check the raw
tool schema returned by your MCP server.

### `FOUNDRY_PROJECT_ENDPOINT` vs `AZURE_AI_PROJECT_ENDPOINT`

The platform injects `FOUNDRY_PROJECT_ENDPOINT`. The code also accepts
`AZURE_AI_PROJECT_ENDPOINT` for backward compatibility, but always prefer the `FOUNDRY_`
variable in new deployments.

## Tracing

The `azure-ai-agentserver-core[tracing]` package is part of the dependency graph locked in `uv.lock` and
provides OpenTelemetry auto-instrumentation for LLM calls, MCP tool invocations, and
server spans. Traces can be exported to Azure Monitor (Application Insights).

### Enable Azure Monitor export

**Locally:** set `APPLICATIONINSIGHTS_CONNECTION_STRING` in `.env`:

```bash
# Get the connection string from your Application Insights resource in the Azure Portal
# (Settings → Properties → Connection String)
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=<key>;IngestionEndpoint=...
```

**When deployed:** the platform automatically injects `APPLICATIONINSIGHTS_CONNECTION_STRING`
from the Application Insights resource linked to your Foundry project. No additional
configuration is required.

### View traces in Azure Monitor

Once `APPLICATIONINSIGHTS_CONNECTION_STRING` is set:

1. Go to the [Azure Portal](https://portal.azure.com) and open your Application Insights resource.
2. Navigate to **Investigate** → **Transaction search** to see individual traces.
3. Use **Investigate** → **Application map** for an end-to-end dependency view.

Traces include LLM calls, tool invocations (including MCP calls to the toolbox), and
server spans. Each conversation turn produces a linked trace tree rooted at the
incoming `/responses` request.

### agent.yaml Format

```yaml
kind: hosted          # MUST be at root level
name: toolbox-langgraph-agent
protocols:
  - protocol: responses
    version: 2.0.0
environment_variables:
  - name: AZURE_OPENAI_ENDPOINT
    value: ${AZURE_OPENAI_ENDPOINT}     # Single-brace syntax
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
```

> **WARNING:** Do NOT use the nested `template:` format — `azd deploy` silently ignores it.  
> Do NOT use `${{VAR}}` double-brace syntax — the container receives the literal string.

### Toolbox Configuration

The toolbox is configured in `azure.yaml` (generated by `azd ai agent init`). You can add toolbox definitions under `config.toolboxes` in `azure.yaml`. See the [azd README](../azd/README.md) for supported toolbox scenarios.

### Monitoring

```powershell
# View container logs
azd ai agent monitor --tail 50
```

### Known Issues

See [../azd/KNOWN_ISSUES.md](../azd/KNOWN_ISSUES.md) for all known issues with azd toolbox deployments.

## Additional Files

- `main.py` — agent entry point (env loading, agent name detection, telemetry, and LangGraph agent)
- `../sample_toolboxes_crud.py` — SDK samples for creating, listing, and deleting toolbox resources

## Contributing

This project welcomes contributions and suggestions.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.
