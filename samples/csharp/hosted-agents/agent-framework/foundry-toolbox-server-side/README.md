# Foundry Toolbox — Server-Side Tools

An agent that consumes a Foundry Toolbox as **server-side tools**. The Agent Framework hosting layer connects to the toolbox's managed MCP proxy at startup, discovers its tools, and injects them into every request. Tool calls are brokered by the Foundry platform's toolbox proxy, so the agent never hard-codes or locally executes the tools.

`AddFoundryToolboxes(toolboxName)` registers the toolbox with the hosting layer. At startup the hosting layer connects to the toolbox's managed MCP proxy (derived from `FOUNDRY_PROJECT_ENDPOINT`), lists its tools, and caches them. Every incoming request then has those tools injected automatically, and the Foundry platform executes the tool calls through the proxy. The agent itself declares no toolbox tools.

## Creating a Foundry Toolbox

To use your own tools, choose the tool type and authentication mode from the table below, then follow the linked guide to configure that tool in your toolbox.

To run this sample as provided, skip the table and continue with the [setup steps](#prerequisites). The sample's [`azure.yaml`](azure.yaml) already defines an `agent-tools` toolbox with `web_search` and `code_interpreter`; `azd provision` creates it for you.

### Toolbox tool types

| Type | Variant | Description | Guide |
|------|---------|-------------|-------|
| **Built-in** | Web search, code interpreter, ... | Ready-to-use tools hosted by Foundry with no external MCP server to connect. | [Built-in tools guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/built-in-tools.md) |
| **MCP** | Unauthenticated | Anonymous — you provide nothing. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-unauthenticated.md) |
| **MCP** | Key-based | A shared static key you provide as a header (e.g. `Authorization: Bearer <token>`). | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-key-auth.md) |
| **MCP** | Microsoft Entra<br>(Agent Identity / Project Managed Identity) | • Accesses MCP as the **agent/project** itself.<br>• Need grant the agent/project's identity access on the MCP.<br>• No user sign-in or consent. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md) |
| **MCP** | OAuth Identity Passthrough | • Accesses MCP as the signed-in **user**.<br>• Need register the OAuth app.<br>• User consents on first use. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-custom.md) |
| **MCP - Foundry Catalog** | OAuth Identity Passthrough<br>(Managed) | • Accesses MCP as the signed-in **user**.<br>• No OAuth app to set up — Foundry uses its own.<br>• User consents on first use.<br>• Only some catalog MCP support it. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-managed.md) |
| **MCP - Foundry Catalog** | OAuth Identity Passthrough<br>(User Entra Token) | • Accesses MCP as the signed-in **user**.<br>• No OAuth app to set up — Foundry uses its own.<br>• No user consent needed.<br>• Only some catalog MCP support it. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-user-entra-token.md) |
| **OpenAPI** | External REST API | Any REST API with an OpenAPI 3.x spec. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/openapi.md) |
| **A2A** | Remote agent (Agent-to-Agent) | Call another remote agent. | [Setup guide](../../../../python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/a2a.md) |

## Prerequisites

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **A Foundry Toolbox** exposing the server-side tools (see [Creating a Foundry Toolbox](#creating-a-foundry-toolbox) above). If declared in the sample's `azure.yaml`, `azd provision` (Option 1) creates it.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.27.1 or later)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir foundry-toolbox-agent && cd foundry-toolbox-agent
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/foundry-toolbox-server-side/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project, model deployment, and toolbox, provision them:

To use a tool type that is not included in this sample, follow its setup guide in the [Toolbox tool types](#toolbox-tool-types) table above and update `azure.yaml` before provisioning.

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, ask the agent about its toolbox tools:

```bash
azd ai agent invoke --local "What tools do you have?"
```

```bash
azd ai agent invoke --local "Find the latest API version for Microsoft.CognitiveServices accounts in the azure-rest-api-specs repo."
azd ai agent invoke --local "Use the code interpreter to compute the 30th Fibonacci number."
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "What tools do you have?"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Create a toolbox

The toolbox must exist in your Foundry project before you run the agent. This sample expects a toolbox named **`agent-tools`**. Create it with the VS Code Foundry Toolkit extension:

1. In the **Foundry Toolkit** view (signed in), open **Tool Catalog** → **Catalog** tab → **Toolboxes** → **Create Your Toolbox**.

   Or, if you're reading this README in VS Code, directly click [[Create in VS Code]](vscode://ms-windows-ai-studio.windows-ai-studio/open_tools).
2. In the **Included** panel, click **+ Add ▾** → **Add tools** to open the **Select a tool** dialog. To run this sample as provided, add **Web Search** and **Code Interpreter**. To use different tools, follow the tool's **Guide** in the [Toolbox tool types](#toolbox-tool-types) table above.
3. Follow the configuration dialog to add each tool.
4. Back on **Build a Custom Toolbox**, name the toolbox **`agent-tools`**, then click **Publish**. The toolbox appears on the **Toolboxes** tab.
5. When you configure the agent below, set `TOOLBOX_NAME=agent-tools` in `.env`. If you publish the toolbox under a different name, use that name instead.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   dotnet restore
   ```

2. Configure the agent: copy `.env.example` to `.env` and fill in the required variables (including `TOOLBOX_NAME`). The sample loads `.env` automatically on startup.

3. Sign in to Azure with the Azure CLI so `DefaultAzureCredential` can authenticate the terminal process (the **F5** path reuses the Azure sign-in from the Foundry Toolkit, so it doesn't need a separate `az login`):

   ```bash
   az login
   ```

4. Start the agent (listens on `http://localhost:8088`):

   ```bash
   dotnet run
   ```

5. Open the Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.
