# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent hosted using the **Invocations protocol** with session management. Unlike the Responses protocol, the Invocations protocol does **not** provide built-in server-side conversation history — this agent maintains an in-memory session store keyed by `agent_session_id`. In production, replace it with durable storage (Redis, Cosmos DB, etc.) so history survives restarts.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. When a request arrives, the handler looks up (or creates) a session by `session_id`, runs the agent with the user message and session context, and returns the reply. The agent supports both streaming (SSE events) and non-streaming (JSON) response modes.

See [main.py](src/agent-framework-agent-basic-invocations/main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer Invocations SDK](https://pypi.org/project/azure-ai-agentserver-invocations/) (`InvocationAgentServerHost`), which provisions a REST API endpoint compatible with the Azure AI Invocations protocol.

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

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-invocations-agent && cd my-invocations-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/invocations/01-basic/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory. The Invocations protocol uses a `{"message": "..."}` payload:

```bash
azd ai agent invoke --local '{"message": "Hi"}'
```

For multi-turn conversations:

```bash
azd ai agent invoke --local '{"message": "How are you?"}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke '{"message": "Hi"}'
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
   pipx install uv==0.11.7
   uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
