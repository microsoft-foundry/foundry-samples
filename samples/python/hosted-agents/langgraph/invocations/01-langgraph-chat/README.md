# What this sample demonstrates

A [LangGraph](https://langchain-ai.github.io/langgraph/) multi-turn chat agent with two local tools, hosted on Foundry over the **Invocations protocol** using [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting).

Unlike the Responses protocol, the Invocations protocol does **not** surface intermediate tool calls — clients receive only the final assistant text (or its token deltas when streaming).

## How It Works

### LangGraph Agent

The agent is built with `langchain.agents.create_agent(model, tools=[...], checkpointer=FoundryCheckpointSaver(...))`, which returns a compiled LangGraph runnable implementing the standard ReAct loop. The agent registers two local tools:

- `get_current_time` — returns the current UTC time.
- `calculator` — evaluates a simple math expression.

See [main.py](src/langgraph-chat-invocations/main.py) for the full implementation.

### Agent Hosting

The exported graph is registered in `langgraph.json` and loaded by `langchain_azure_ai.agents.hosting.run`, which exposes the Invocations endpoint at `/invocations` and supports both non-streaming (single JSON response) and streaming (`{"stream": true}` SSE token deltas) modes.

Multi-turn continuity is provided by `FoundryCheckpointSaver`: the host wires the resolved `agent_session_id` into `RunnableConfig.configurable.thread_id`, so each session's history is preserved across turns and process restarts. The saver uses Foundry State Store when hosted and a local file-backed store during local development.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
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
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/invocations/01-langgraph-chat/azure.yaml
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

In a separate terminal, invoke the running agent:

```bash
azd ai agent invoke --local '{"message": "What time is it right now?"}'
```

Or invoke directly with curl. The `-i` flag surfaces the `x-agent-session-id` response header you need for multi-turn conversations:

```bash
# Turn 1 — triggers the get_current_time tool (note the x-agent-session-id response header)
curl -i -X POST http://localhost:8088/invocations \
    -H "Content-Type: application/json" \
    -d '{"message": "What time is it right now?"}'

# Turn 2 — pass the session id from Turn 1; triggers the calculator tool
curl -X POST 'http://localhost:8088/invocations?agent_session_id=REPLACE_WITH_SESSION_ID' \
    -H "Content-Type: application/json" \
    -d '{"message": "What is 42 * 17?"}'

# Turn 3 — context recall (no tool call)
curl -X POST 'http://localhost:8088/invocations?agent_session_id=REPLACE_WITH_SESSION_ID' \
    -H "Content-Type: application/json" \
    -d '{"message": "Add 100 to that result."}'
```

Add `"stream": true` to receive per-token SSE deltas, followed by `event: done`:

```bash
curl -N -X POST http://localhost:8088/invocations \
    -H "Content-Type: application/json" \
    -d '{"message": "Count to 5.", "stream": true}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke '{"message": "What time is it right now?"}'
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
  cd src/langgraph-chat-invocations
  uv sync --frozen
  ```

- In VS Code, select `src/langgraph-chat-invocations/.venv` as the Python interpreter.
### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol invocations` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

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
