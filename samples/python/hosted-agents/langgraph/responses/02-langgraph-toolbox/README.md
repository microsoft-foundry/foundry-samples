# What this sample demonstrates

A [LangGraph](https://langchain-ai.github.io/langgraph/) ReAct agent wired to a **Foundry Toolbox** in Microsoft Foundry, hosted on Foundry over the **Responses protocol** using [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting). The toolbox exposes `web_search` plus the public **Microsoft Learn MCP** server behind one endpoint — the agent calls the toolbox tools without managing any credentials.

## Creating a Foundry Toolbox

To use your own tools, choose the tool type and authentication mode from the table below, then follow the linked guide to configure that tool in your toolbox.

To run this sample as provided, create a toolbox named **`my-toolbox`** with **Web Search** and the public **Microsoft Learn MCP** server by following either the `azd` or VS Code steps below.

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

## Prerequisites

- Python 3.12+
- A Microsoft Foundry project
- Azure CLI installed and logged in (`az login`)

The sample bundles a [`toolbox.yaml`](src/toolbox-langgraph/toolbox.yaml) that defines the tools.
Neither tool requires a secret. Create the toolbox from this file before running the agent by
following the `azd` or VS Code steps below.

> [!NOTE]
> This sample identifies the toolbox by name (`TOOLBOX_NAME`) and always consumes its current default version. The `AzureAIProjectToolbox` helper builds the MCP endpoint from the toolbox name, so it can't pin the agent to a specific toolbox version. When you publish a new default version, the agent picks it up automatically.

## How It Works

### Toolbox tool loading

[`langchain_azure_ai.tools.AzureAIProjectToolbox`](https://github.com/langchain-ai/langchain-azure/blob/main/libs/azure-ai/langchain_azure_ai/tools/_toolbox.py) opens an MCP session against the toolbox endpoint, authenticates with `DefaultAzureCredential`, sanitizes tool schemas, and returns standard LangChain `BaseTool` instances. The async graph factory loads the tools once when the hosting entrypoint starts; each tool invocation opens its own short-lived MCP session.

### LangGraph Agent

The compiled graph is built with `langchain.agents.create_agent(model, tools=tools, system_prompt=...)`, which returns a compiled LangGraph runnable implementing the standard ReAct loop. The system prompt instructs the agent to ground answers in tool-provided sources and include a brief Sources section when URLs are present.

### OAuth consent handling

If a toolbox connection ever needs additional consent (for example, an MCP server backed by an OAuth connection), the Foundry MCP gateway raises an MCP error with code `-32006` and a URL on `consent.azure-apim.net`. The sample installs a `handle_tool_error` callback on every loaded tool that detects this case and returns a friendly tool message containing the consent URL — the agent surfaces it to the caller, and the conversation continues instead of crashing.

### Tool schema sanitization

Some MCP servers return tools with malformed JSON schemas (e.g. `object`-type schemas with no `properties` field), which the OpenAI tool format rejects. The sample patches missing or empty `properties` before handing the tools to LangGraph.

### Agent Hosting

`langchain_azure_ai.agents.hosting.run` loads the graph factory from
`langgraph.json` and exposes the OpenAI-compatible Responses endpoint at
`/responses`. It handles conversation history, streaming lifecycle events, and
tool-call surfacing automatically.

See [main.py](src/toolbox-langgraph/main.py) for the full implementation.

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
mkdir hosted-langgraph-agent && cd hosted-langgraph-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/02-langgraph-toolbox/azure.yaml
```

### Create the toolbox with `azd ai`

To use a tool type that is not included in this sample, follow its setup guide in the [Toolbox tool types](#toolbox-tool-types) table above and update the bundled [`toolbox.yaml`](src/toolbox-langgraph/toolbox.yaml).

To run this sample as provided, create `my-toolbox` from the bundled configuration:

```bash
azd ai toolbox create my-toolbox --from-file ./src/toolbox-langgraph/toolbox.yaml
```

The agent reads `TOOLBOX_NAME=my-toolbox` and consumes the toolbox's current default version.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment, provision them:

```bash
azd provision
```

If `my-toolbox` does not already exist, create it with the command in
[Creating a Foundry Toolbox](#creating-a-foundry-toolbox) before running
`azd deploy`.

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, send a query to the agent:

```bash
azd ai agent invoke --local "How do I create a Foundry project with the Azure CLI?"
```

Or invoke directly with curl:

```bash
# Tool discovery
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "What tools do you have?"}'

# web_search
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "What is the latest stable Python release?"}'

# Microsoft Learn MCP
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "How do I create a Foundry project with the Azure CLI?"}'
```

### Deploy to Foundry

Deploy the agent to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke "How do I create a Foundry project with the Azure CLI?"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Install uv if it is not already available:

  ```bash
  python -m pip install uv
  ```

- From the sample root, sync the committed environment:

  ```bash
  cd src/toolbox-langgraph
  uv sync --frozen
  ```

- In VS Code, select `src/toolbox-langgraph/.venv` as the Python interpreter.

### Create the toolbox

The toolbox must exist in your Foundry project before you run the agent. This sample expects a toolbox named **`my-toolbox`**. Create it with the VS Code Foundry Toolkit extension:

1. In the **Foundry Toolkit** view (signed in), open **Tool Catalog** → **Catalog** tab → **Toolboxes** → **Create Your Toolbox**.

   Or, if you're reading this README in VS Code, directly click [[Create in VS Code]](vscode://ms-windows-ai-studio.windows-ai-studio/open_tools).
2. In the **Included** panel, click **+ Add ▾** → **Add tools**. Add **Web Search**, then add an unauthenticated MCP server with the URL `https://learn.microsoft.com/api/mcp`. To use different tools, follow the tool's **Guide** in the [Toolbox tool types](#toolbox-tool-types) table above.
3. Follow the configuration dialog to add each tool.
4. Back on **Build a Custom Toolbox**, name the toolbox **`my-toolbox`**, then click **Publish**.
5. Set `TOOLBOX_NAME=my-toolbox` in the sample's `.env` file.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables (including `TOOLBOX_NAME`), and sign in to Azure with the Azure CLI (`az login`).
2. From `src/toolbox-langgraph`, start the agent:
   `uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses`
   (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Troubleshooting

### Agent starts but returns no tools

Check that the toolbox exists in your Foundry project and that `TOOLBOX_NAME`
matches its name. The sample uses `my-toolbox` by default; create it separately
using the `azd` or VS Code steps above.

### OAuth consent required

If a toolbox connection needs additional consent, the gateway returns an MCP error with code `-32006` and a URL on `consent.azure-apim.net`. The agent surfaces this URL through a tool message of the form:

```
OAuth consent required. Open this URL in a browser to authorize the toolbox connection, then retry the request: https://consent.azure-apim.net/...
```

Open the URL, complete the consent flow, then retry the original request.

### Tool call failures don't crash the agent

A `handle_tool_error` callback is installed on every loaded tool, so MCP tool errors are returned as tool messages rather than raising exceptions that would break conversation state.

### Tool schemas rejected by OpenAI

The sample sanitizes malformed schemas from MCP servers (missing `properties` on `object`-type schemas) at load time. If you see `400 Invalid tool schema` errors anyway, inspect the raw tool schema returned by your MCP server — there may be additional shape issues.
