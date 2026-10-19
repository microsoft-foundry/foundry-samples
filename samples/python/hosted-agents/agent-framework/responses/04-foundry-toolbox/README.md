# Agent with Foundry Toolbox (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery, hosted on Microsoft Foundry using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Foundry Toolbox configuration
The [`azure.yaml`](azure.yaml) declares the `agent-tools` toolbox and its authenticated connections as separate services. `azd up` deploys them before the agent and passes the versioned MCP endpoint to `TOOLBOX_ENDPOINT`.

To use your own tools, choose the tool type and authentication mode from the table below, then follow the linked guide to configure that tool in your toolbox.

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


## How it works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via `FoundryToolbox` — a thin convenience wrapper over `MCPStreamableHTTPTool` that authenticates every request with the credential and forwards the platform per-request call-id — which discovers and invokes the toolbox's tools over MCP at runtime. `FoundryToolbox` resolves the endpoint from the `TOOLBOX_ENDPOINT` environment variable. If that variable isn't set, it builds the endpoint from `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_NAME`.

See [main.py](src/agent-framework-agent-with-foundry-toolbox-responses/main.py) for the full implementation.

## Running the agent

### Option 1: Azure Developer CLI (`azd`)

#### Before you initialize

This sample connects to GitHub MCP, Azure Language MCP, and Microsoft Foundry MCP. Before running `azd ai agent init`, prepare the GitHub PAT and Azure Language MCP endpoint; init can prompt for both values:

1. **A GitHub personal access token** for GitHub MCP. [Create a fine-grained PAT](https://github.com/settings/personal-access-tokens/new) and limit repository access and permissions to what the GitHub MCP tools you plan to use require. Keep the token private.
2. **An existing Azure Language resource** and its [Language MCP endpoint](https://learn.microsoft.com/azure/ai-services/language-service/concepts/foundry-tools-agents).
3. **Access to the Microsoft Foundry project** with the account you use to authenticate with `azd`; the Foundry MCP connection uses your Entra token.

#### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.32.0 or later)
2. Install the unified Foundry CLI extension bundle (provides `azd ai agent`, `connection`, `inspector`, `project`, `routine`, `skill`, and `toolbox`):
   ```bash
   # If you previously installed individual extensions, uninstall them first:
   #   azd ext uninstall azure.ai.agents
   #   azd ext uninstall azure.ai.toolboxes
   azd ext install microsoft.foundry
   ```
3. Authenticate:
   ```bash
   azd auth login
   ```

#### Initialize the agent project

No cloning required. Create a project folder, then initialize it from the sample manifest. The `--src` value keeps the agent code in the path declared by `azure.yaml`:

```bash
mkdir my-toolbox-agent
cd my-toolbox-agent

azd ai agent init \
  --template https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox/azure.yaml \
  --src src/agent-framework-agent-with-foundry-toolbox-responses
```

Follow the prompts to select or create a Foundry project and model deployment, and to provide the GitHub PAT and Azure Language MCP endpoint if requested. If you are connecting to an existing Foundry project, pass `--model-deployment <existing-deployment-name>` to select its deployment directly. This also works around the current [existing-project model picker issue](https://github.com/Azure/azure-dev/issues/10519).

Initialization creates the project in `my-toolbox-agent`: its root contains `azure.yaml` and the `.azure` environment, while the agent's Python files are under `src/agent-framework-agent-with-foundry-toolbox-responses`. Do not initialize again after it succeeds. Run `azd` commands from the initialized project root; run Python and `uv` commands from the source directory.

After init creates or selects the Foundry project, grant its project managed identity **Cognitive Services Language Owner** on the Azure Language resource under **Access control (IAM)** before running `azd up`. See the [Microsoft Entra setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md#step-2--authorize-the-identity) for role-assignment details.

#### Configure external dependencies

`azure.yaml` declares `ghmcppat` (GitHub MCP, PAT), `langmcpconn` (Azure Language MCP, project managed identity), and `foundrymcpconn` (Foundry MCP, user Entra token). The toolbox depends on all three connections.

If you need to change a value entered during initialization, set it in the initialized project's azd environment:

```bash
azd env set GITHUB_MCP_PAT "<your-GitHub-MCP-PAT>"
azd env set AZURE_LANGUAGE_MCP_ENDPOINT "https://<language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview"
```

Run these commands from the initialized project root. Keep the PAT out of source control. Calls through the Foundry MCP connection require the calling user's access. For other tool types, consult the [tool type guides](#toolbox-tool-types) and edit the connection and toolbox services in `azure.yaml`. Changing `ghmcppat` from PAT to OAuth requires updating its auth configuration.

#### Provision and deploy

```bash
azd up
```

The agent's `TOOLBOX_ENDPOINT` maps to `TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT` produced by this toolbox deployment. After editing tools, connections, or agent code, run `azd deploy --all`; the agent uses the new toolbox version without publishing it as the default or switching older agents.

#### Run the agent locally

Run `azd up` first: `azd ai agent run` starts the host locally but does not create the remote connections or toolbox.

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

#### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "What tools do you have?"
```

#### Deploy to Foundry

After changing the toolbox or agent, deploy all services together:

```bash
azd deploy --all
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

#### Invoke the deployed agent

```bash
azd ai agent invoke "What tools do you have?"
```

### Option 2: VS Code (Foundry Toolkit)

#### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

#### Set up the Python virtual environment

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/agent-framework-agent-with-foundry-toolbox-responses
  pipx install uv==0.11.7
  uv sync --frozen --python 3.13
  ```
- Open the initialized project root (the directory containing `azure.yaml`) in VS Code so the Foundry Toolkit can read the project configuration. Run `uv sync` from the source directory above, then select that directory's `.venv` with **Python: Select Interpreter**.

#### Prepare remote dependencies

Run `azd up` from the initialized project root before local testing; it creates the remote connections and toolbox that `azd ai agent run` does not create. For F5 or standalone Python, create `.env` in the source directory and set `TOOLBOX_ENDPOINT` to the versioned endpoint returned by `azd env get-value TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT` (run that command from the project root).

#### Run and debug the agent

Press **F5** from the initialized project opened in VS Code to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

#### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

#### Deploy to Foundry

This sample declares the connections, toolbox, and agent together in `azure.yaml`. From the initialized project root, deploy them together so the agent uses the current toolbox configuration:

```bash
azd deploy --all
```

The Foundry Toolkit deploy wizard deploys the agent only; it does not update the toolbox and its connections.


## Use GitHub Copilot for Azure

If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, the following skill references describe the same endpoint contract (env var, headers, MCP protocol, citation patterns, and troubleshooting) that the agent must implement:

- [Foundry Toolbox — Concept, API Shape & Schema](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/toolbox/toolbox.md) — toolbox creation and lifecycle, supported tool and authentication types, composition rules, versioning, MCP endpoint formats, testing, and troubleshooting.
- [Use a Toolbox from Your Agent Code](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md) — framework-specific integration paths, `TOOLBOX_ENDPOINT`, local and deployed validation, BYO MCP authentication, OAuth consent, approvals, citations, and troubleshooting.


## Finding the Entra audience for an MCP server

An Entra pass-through connection requires an **audience** — the Entra resource that the MCP server validates tokens against. For the Microsoft Foundry MCP server (`https://mcp.ai.azure.com`), read it from the server's OAuth protected-resource metadata:

```bash
curl https://mcp.ai.azure.com/.well-known/oauth-protected-resource
```

```jsonc
{
   "resource": "https://mcp.ai.azure.com",
   "authorization_servers": ["https://login.microsoftonline.com/common/v2.0"],
   "scopes_supported": ["https://mcp.ai.azure.com/Foundry.Mcp.Tools"]
}
```

Use the `resource` value (`https://mcp.ai.azure.com`) as the audience.

> For connector-backed MCP servers (for example Microsoft 365 / WorkIQ servers such as Outlook Mail), the audience is instead published in the Foundry Tools Catalog. Look it up with the helper scripts in [`scripts/`](src/agent-framework-agent-with-foundry-toolbox-responses/scripts/): run `./scripts/list-foundry-connectors.ps1 -ConnectorName <name>` (or `./scripts/list-foundry-connectors.sh -n <name>`) and read `AzureActiveDirectoryResourceId` (equivalently `resourceUri`) under `properties.x-ms-connection-parameters`. Run the script with no connector name to list every connector with its name, title, and auth type.

## Troubleshooting

### A single failing MCP source can fail the whole agent

A toolbox aggregates every tool source behind one MCP endpoint. If **any** referenced MCP server fails while the toolbox enumerates tools (`tools/list`), the toolbox fails the entire enumeration, so the agent can't load its tools and every request returns an error (HTTP 500) until that source recovers.

For example, a flaky third-party MCP source can intermittently return `HTTP 502 (Bad Gateway)` during enumeration, which surfaces as:

```
tools/list failed for 1 tool source(s), succeeded for 5 tool source(s)
{"errors":[{"name":"<server_label>","type":"mcp","error":{"code":"HTTP_502", ...}}]}
```

This is an upstream/service hiccup, not a problem with the agent code. Mitigations:

- Retry the request — these failures are usually transient.
- If a source is persistently unavailable, temporarily remove its tool entry (and connection service, if any) from `azure.yaml`, then run `azd deploy --all` to update the toolbox and agent together.
- Inspect deployed agent logs with `azd ai agent monitor` to identify which source failed.

### Entra pass-through forwards the caller's identity

The Foundry MCP tool authenticates with **Entra pass-through** (`foundrymcpconn`): Foundry forwards the
calling user's Entra token to `https://mcp.ai.azure.com`. The token is forwarded both from the Foundry
portal **Agent Playground** (signed-in user) and by `azd ai agent invoke` (the developer's Entra token),
so the tools operate as that user and only act on resources the user can already access. The Foundry MCP
server requires no extra license — just access to the Foundry project.

Because the tool acts as a specific user, running the agent **locally** (`uv run --no-sync python main.py`) or calling the
endpoint with a raw token uses whatever identity that token represents (`az login` user locally, the
agent's managed identity when hosted). If that identity has no access to the target resources, the tool
returns an authorization error even though it is discovered and called correctly.

> Some other Entra pass-through MCP servers add their **own** entitlement checks on top of the token. For
> example, the Microsoft 365 / WorkIQ servers (Outlook Mail, Teams) require the caller to hold a
> **Microsoft 365 Copilot (Business Chat)** license; without it they fail with
> `WorkIQ license check failed. Required service plan(s): [M365_COPILOT_BUSINESS_CHAT]`. That is a
> property of those servers, not of Entra pass-through itself.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Tool catalog](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/tool-catalog) — browse available tools to extend your agent (Bing Search, Azure AI Search, file search, code interpreter, and more)
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
- [Basic agent](../01-basic/) — minimal agent with no tools
- [Add local tools](../02-tools/) — sample with locally-defined Python tool functions
- [Build multi-agent workflows](../05-workflows/) — sample with chained agent pipelines
