<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A **Bring Your Own** hosted agent using the **Responses protocol** with **Azure AI Foundry Toolbox MCP** integration in Python. It shows how to connect to a Foundry toolbox at startup, discover available tools via MCP, and let the model call them during conversation through an agentic tool-calling loop.

## Creating a Foundry Toolbox

To use your own tools, choose the tool type and authentication mode from the table below, then follow the linked guide to configure that tool in your toolbox.

The [`azure.yaml`](azure.yaml) declares **`my-toolbox`** with **Web Search** and the public **Microsoft Learn MCP** server. `azd up` creates the project, toolbox, and agent in dependency order.

### Toolbox tool types

| Type | Variant | Description | Guide |
|------|---------|-------------|-------|
| **Built-in** | Web search, code interpreter, ... | Ready-to-use tools hosted by Foundry with no external MCP server to connect. | [Built-in tools guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/built-in-tools.md) |
| **MCP** | Unauthenticated | Anonymous — you provide nothing. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-unauthenticated.md) |
| **MCP** | Key-based | A shared static key you provide as a header (e.g. `Authorization: Bearer <token>`). | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-key-auth.md) |
| **MCP** | Microsoft Entra<br>(Agent Identity / Project Managed Identity) | • Accesses MCP as the **agent/project** itself.<br>• Need grant the agent/project's identity access on the MCP.<br>• No user sign-in or consent. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md) |
| **MCP** | OAuth Identity Passthrough | • Accesses MCP as the signed-in **user**.<br>• Need register the OAuth app.<br>• User consents on first use. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-custom.md) |
| **MCP - Foundry Catalog** | OAuth Identity Passthrough<br>(Managed) | • Accesses MCP as the signed-in **user**.<br>• No OAuth app to set up — Foundry uses its own.<br>• User consents on first use.<br>• Only some catalog MCP support it. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-managed.md) |
| **MCP - Foundry Catalog** | OAuth Identity Passthrough<br>(User Entra Token) | • Accesses MCP as the signed-in **user**.<br>• No OAuth app to set up — Foundry uses its own.<br>• No user consent needed.<br>• Only some catalog MCP support it. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-user-entra-token.md) |
| **OpenAPI** | External REST API | Any REST API with an OpenAPI 3.x spec. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/openapi.md) |
| **A2A** | Remote agent (Agent-to-Agent) | Call another remote agent. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/a2a.md) |

This sample combines:
- The [`azure-ai-agentserver-responses`](https://pypi.org/project/azure-ai-agentserver-responses/) SDK for the Responses protocol
- The [Foundry SDK (`azure-ai-projects`)](https://pypi.org/project/azure-ai-projects/) for model access via the Responses API
- Direct MCP (JSON-RPC over HTTP) for toolbox tool discovery and invocation

Conversation history is automatically managed by the platform via `previous_response_id`. The handler calls `context.get_history()` to retrieve prior turns.

## How It Works

### Toolbox Integration

At startup, the agent connects to the toolbox MCP endpoint, runs `initialize` + `tools/list`, and converts the discovered tools into function definitions for the Responses API. When the model requests a tool call, the agent executes it via MCP `tools/call` and feeds the result back to the model.

### Model Integration

The agent uses the Foundry SDK Responses API with tool definitions. Because this sample demonstrates toolbox-grounded answers, the first model round uses `tool_choice: "required"`, guaranteeing at least one toolbox call for every request. Follow-up rounds use `tool_choice: "auto"`, so the model can call additional tools or produce the final text answer.

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer Responses SDK](https://pypi.org/project/azure-ai-agentserver-responses/), which provisions a REST API endpoint compatible with the Azure AI Responses protocol.

### Agent Deployment

The hosted agent can be developed and deployed to Microsoft Foundry using the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd).

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.32.0 or later) and the unified Foundry CLI extension bundle: `azd ext install microsoft.foundry` (if you previously installed `azure.ai.agents` or `azure.ai.toolboxes`, run `azd ext uninstall <name>` first).
   - Authenticated: `azd auth login`

2. **Azure CLI**
   - Installed and authenticated: `az login`

3. **Python 3.12 or later**
   - Verify your version: `python --version`

4. **Provisioned remote dependencies**
   - Run `azd up` from the initialized project directory before local development. `azd ai agent run` starts the agent locally but does not create the remote toolbox.

### Configure the toolbox

> [!TIP]
> If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, the following skill references describe the same endpoint contract (env var, headers, MCP protocol, citation patterns, and troubleshooting) that the agent must implement:
>
> - [Foundry Toolbox — Concept, API Shape & Schema](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/toolbox/toolbox.md) — toolbox creation and lifecycle, supported tool and authentication types, composition rules, versioning, MCP endpoint formats, testing, and troubleshooting.
> - [Use a Toolbox from Your Agent Code](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md) — framework-specific integration paths, `TOOLBOX_ENDPOINT`, local and deployed validation, BYO MCP authentication, OAuth consent, approvals, citations, and troubleshooting.

To use another tool type, follow its [setup guide](#toolbox-tool-types) and edit the `my-toolbox` service in [`azure.yaml`](azure.yaml). The agent service depends on the toolbox and maps the versioned `TOOLBOX_MY_TOOLBOX_MCP_ENDPOINT` produced by this deployment to `TOOLBOX_ENDPOINT`. Run `azd deploy --all` after editing tools: the agent uses the newly created toolbox version without publishing it as the default or switching older agents.

> [!NOTE]
> To attach tools that need credentials, declare a separate `azure.ai.connection` service in `azure.yaml`, reference it from the toolbox tool with `connection`, and add it to the toolbox's `uses`.

### Environment Variables

See [`.env.example`](src/toolbox-python-responses/.env.example) or `.env` for the full list of environment variables this sample uses.

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name — must match your Foundry project deployment. Declared in `azure.yaml`. |
| `TOOLBOX_ENDPOINT` | Yes | Versioned toolbox MCP endpoint. The agent service maps it from `TOOLBOX_MY_TOOLBOX_MCP_ENDPOINT` on deployment. For standalone local Python/VS Code runs, set it in `.env` using the endpoint from the provisioned project. |
| `TOOLBOX_NAME` | Optional | Toolbox name. If `TOOLBOX_ENDPOINT` isn't set, the agent builds the latest-version endpoint from this and `FOUNDRY_PROJECT_ENDPOINT`. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

Set `TOOLBOX_ENDPOINT` to the full MCP URL. Two forms are supported:
```
# Latest version:
https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<toolbox-name>/mcp?api-version=v1

# Pinned to a specific version:
https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<toolbox-name>/versions/<version>/mcp?api-version=v1
```
The deployed agent gets this endpoint from `azure.yaml`; a standalone local process needs it in `.env`. `azd ai agent run` reads the initialized project's environment but does not provision missing resources.

### Running the Sample

#### Using `azd`

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088`.

<details>
<summary><h4>Using the Foundry Toolkit VS Code Extension</h4></summary>

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

**Set up the Python virtual environment**

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/toolbox-python-responses

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/toolbox-python-responses/.venv`.

**Prepare remote dependencies**

Run `azd up` from the initialized project directory first. For F5/standalone Python runs, configure `.env` with the resulting project's `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_ENDPOINT` (available via `azd env get-value TOOLBOX_MY_TOOLBOX_MCP_ENDPOINT`). The VS Code deploy wizard deploys the agent but does not create the toolbox declared in `azure.yaml`; use `azd deploy --all` to update both.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/toolbox-python-responses`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

</details>

#### Manual setup

```bash
cd src/toolbox-python-responses

cp .env.example .env  # skip if .env already exists
# Edit .env and fill in your values, then:
export $(grep -v '^#' .env | xargs)

pipx install uv==0.11.7
uv sync --frozen --python 3.12
uv run --no-sync python main.py
```

The agent starts on `http://localhost:8088`.

### Testing

```bash
azd ai agent invoke --local "Search the web for Azure AI Foundry news"
```

Or use `curl`:

```bash
# Non-streaming
curl -sS -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "Search the web for Azure AI Foundry news", "stream": false}' | jq .

# Streaming
curl -sS -N -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "What is Azure AI Foundry?", "stream": true}'
```

### Deploying the Agent to Microsoft Foundry

#### Setup

##### 1. Install Azure Developer CLI (`azd`)

**Linux/macOS:**
```bash
curl -fsSL https://aka.ms/install-azd.sh | bash
```

**Windows (PowerShell):**
```powershell
winget install microsoft.azd
```

See the [full installation docs](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) for other options.

##### 2. Install the unified Foundry CLI extension bundle

```bash
# If you previously installed individual extensions, uninstall them first:
#   azd ext uninstall azure.ai.agents
#   azd ext uninstall azure.ai.toolboxes

# Install the unified bundle (provides azd ai agent, connection, inspector,
# project, routine, skill, and toolbox).
azd ext install microsoft.foundry
```

To upgrade the extension later:

```bash
azd ext upgrade microsoft.foundry
```

##### 3. Log in to Azure

```bash
azd auth login
```

##### 4. Fix git CRLF setting (Windows only)

```bash
git config --global core.autocrlf false
```

#### Quick Start (Deploy with azd)

> **IMPORTANT:** The `-m` (or `--manifest`) flag is **required** for `azd ai agent init`.
> It tells the command where to find your agent definition and source files.

```bash
# 1. Create a new directory and initialize the agent project
mkdir my-agent && cd my-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/responses/bring-your-own-toolbox/azure.yaml
azd up

# 2. Invoke the deployed agent (run from the initialized project directory)
azd ai agent invoke "Search the web for Azure AI Foundry news" --timeout 120
```

To change the toolbox tools and deploy a new agent version together, run `azd deploy --all` from the initialized project directory. The agent receives the versioned toolbox endpoint from the same deployment.

To stream logs from the running agent:

```bash
azd ai agent monitor --tail 50
```

> **Tip:** `azd ai agent invoke` must be run from the scaffolded project directory
> (the directory where `azure.yaml` was created by `azd ai agent init`).
> The `--timeout 120` flag is recommended — agent cold starts can take up to 60 seconds.

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

#### Deploying with the Foundry Toolkit VS Code Extension

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a tab-based **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate what it can.
2. If prompted, complete **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one) to deploy to.
3. On the **Basics** tab, configure the core deployment settings:
   - **Deployment Method**: **Code** (upload as a ZIP) or **Container** (Docker image via ACR).
   - For **Code**, pick a packaging option: **Remote** or **Local**.
   - For **Container**, pick a registry option: default ACR, your own ACR, or a prebuilt ACR image.
   - **Hosted Agent Name**: confirm the name to register with the hosting service.
4. On the **Review + Deploy** tab, finalize the runtime and resources:
   - Confirm the auto-detected runtime details (language, entry point, or Dockerfile).
   - Pick a **CPU and Memory** size.
   - Click **Deploy**. Fields are validated inline, and the extension handles the build/upload, agent version creation, and RBAC role assignment.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy --all`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.

---
