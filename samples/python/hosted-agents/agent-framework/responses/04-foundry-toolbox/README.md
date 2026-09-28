# Agent with Foundry Toolbox (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery, hosted on Microsoft Foundry using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Creating a Foundry Toolbox
The sample bundles a [`toolbox.yaml`](src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml) that defines the tools.

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

#### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.27.1 or later)
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

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-toolbox-agent && cd my-toolbox-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one. Initializing also sets the selected project as the active project for the `azd ai` commands that follow.

#### Creating Connections

Before creating the toolbox, create project connections for any tools that require authentication. The connection defines the authentication details and credentials for the tool, and the toolbox references the connection to authenticate tool invocations at runtime.

To add a tool that is not included in this sample, use the [Toolbox tool types](#toolbox-tool-types) table above to find the detailed setup guide for its tool type and authentication mode.

To run this sample as provided, create the following connections. They are already referenced in `toolbox.yaml`.

For `ghmcppat`, run the following command to create a PAT-based connection to the GitHub MCP server:

```powershell
azd ai connection create ghmcppat --kind remote-tool --target https://api.githubcopilot.com/mcp --auth-type custom-keys --custom-key "Authorization=Bearer <github_pat>" -p https://<account>.services.ai.azure.com/api/projects/<project>
```

For `ghmcpoauth`, create an OAuth2-based connection to the GitHub MCP server:

```powershell
azd ai connection create ghmcpoauth --kind remote-tool --target https://api.githubcopilot.com/mcp --auth-type oauth2 --connector-name foundrygithubmcp -p https://<account>.services.ai.azure.com/api/projects/<project>
```

> This sample uses `ghmcppat` by default, but you can switch to `ghmcpoauth` in the `toolbox.yaml` file.

For `langmcpconn`, create an agent-identity-based connection to the Azure Language MCP server:

```powershell
azd ai connection create langmcpconn --kind remote-tool --target https://<language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview --auth-type project-managed-identity --audience https://cognitiveservices.azure.com/ -p https://<account>.services.ai.azure.com/api/projects/<project>
```

For `foundrymcpconn`, create an Entra pass-through connection to the Microsoft Foundry MCP server:

```powershell
azd ai connection create foundrymcpconn --kind remote-tool --target https://mcp.ai.azure.com --auth-type user-entra-token --audience https://mcp.ai.azure.com -p https://<account>.services.ai.azure.com/api/projects/<project>
```

For details on finding the correct `--audience` value for another MCP server, see [Finding the Entra audience for an MCP server](#finding-the-entra-audience-for-an-mcp-server).

#### Create the toolbox with `azd ai`

To create a toolbox with tools that are not included in this sample, use the [Toolbox tool types](#toolbox-tool-types) table above to find the detailed setup guide for each tool and authentication mode.

To run this sample as provided, create its toolbox from the included `toolbox.yaml` after creating the connections above:

```bash
azd ai toolbox create agent-tools --from-file ./src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project>
```

The first version becomes the default automatically. Use `azd ai toolbox list`, `azd ai toolbox show agent-tools`, and `azd ai toolbox version list agent-tools` to inspect, and `azd ai toolbox delete agent-tools --force` to remove it.

To stage incremental changes safely, use `azd ai toolbox connection add/remove` and `azd ai toolbox skill add/list/remove`; each creates a new toolbox version that carries forward existing connections and skills but **doesn't** change the default. Promote a version with `azd ai toolbox publish agent-tools <version>` when you're ready to make it active.

`azd ai toolbox create` prints the toolbox's versioned MCP endpoint. Copy that endpoint and store it in your `azd` environment so the agent connects to it:

```bash
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/agent-tools/versions/1/mcp?api-version=v1"
```

#### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

#### Run the agent locally

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

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
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
   pipx install uv==0.11.7
   uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

#### Create the toolbox

The toolbox must exist in your Foundry project before you run the agent. This sample expects a
toolbox named **`agent-tools`**. Create it with the VS Code Foundry Toolkit extension:

1. In the **Foundry Toolkit** view (signed in), open **Tool Catalog** → **Catalog** tab → **Toolboxes** → **Create Your Toolbox**.

   Or, if you're reading this README in VS Code, directly click [[Create in VS Code]](vscode://ms-windows-ai-studio.windows-ai-studio/open_tools).

2. In the **Included** panel click **+ Add ▾** → **Add tools** to open the **Select a tool** dialog. Pick the tool you want, then fill in the config dialog — see the tool's **Guide** in the [Toolbox tool types](#toolbox-tool-types) table above for the exact fields and auth mode.
3. For most tool types, follow the config dialog's flow and default values to complete the setup.

   Only [**OAuth Identity Passthrough**](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-custom.md), [**Microsoft Entra (Agent Identity / Project Managed Identity)**](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md), and [**OpenAPI**](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/openapi.md) require you to provide extra info and complete additional auth setup — follow that tool's detailed page for the exact fields and auth mode.
4. Back on **Build a Custom Toolbox**, click **Publish**. The toolbox appears on the **Toolboxes** tab. Use the copy icon in the **Endpoint URL** column to copy the versioned MCP endpoint into `TOOLBOX_ENDPOINT` in your `.env`:

   ```dotenv
   TOOLBOX_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/agent-tools/versions/1/mcp?api-version=v1"
   ```

#### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

#### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

#### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.


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
- If a source is persistently unavailable, temporarily remove its tool entry (and connection) from `toolbox.yaml`, recreate the toolbox, and update `TOOLBOX_ENDPOINT`.
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
