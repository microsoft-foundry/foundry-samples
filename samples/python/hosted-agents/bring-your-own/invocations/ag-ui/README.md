**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# AG-UI Protocol — Invocations (Pydantic AI)

A minimal getting-started agent implementing the [AG-UI protocol](https://docs.ag-ui.com/introduction) over the Foundry invocations protocol, using [Pydantic AI](https://ai.pydantic.dev/) with Azure OpenAI. **Zero manual event translation** — Pydantic AI's built-in `handle_ag_ui_request` handles the full AG-UI lifecycle automatically.

## How It Works

1. Receives an AG-UI `RunAgentInput` payload via `POST /invocations`
2. Pydantic AI's `handle_ag_ui_request` runs the agent and streams AG-UI events (`RUN_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `RUN_FINISHED`) as SSE — no manual translation needed
3. The agent uses Azure OpenAI (Foundry models) via `AzureProvider`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint (auto-injected in hosted containers) |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name declared in `azure.yaml` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Application Insights connection string (auto-injected in hosted containers) |

> **Note:** Authentication uses `DefaultAzureCredential` (managed identity, Azure CLI, etc.) — no API key needed.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment
- A Foundry project with a deployed model

### Run the agent locally

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Invoke the local agent

In a separate terminal, invoke the running agent:

**Bash:**
```bash
azd ai agent invoke --local '{"threadId": "thread-1", "runId": "run-1", "state": {}, "messages": [{"id": "msg-1", "role": "user", "content": "Hello"}], "tools": [], "context": [], "forwardedProps": {}}'
```

**PowerShell:**
```powershell
azd ai agent invoke --local '{\"threadId\": \"thread-1\", \"runId\": \"run-1\", \"state\": {}, \"messages\": [{\"id\": \"msg-1\", \"role\": \"user\", \"content\": \"Hello\"}], \"tools\": [], \"context\": [], \"forwardedProps\": {}}'
```

Or invoke directly with curl:

```bash
curl -N -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "threadId": "thread-123",
    "runId": "run-456",
    "state": {},
    "messages": [{"id": "msg-1", "role": "user", "content": "Hello!"}],
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
# Provision Azure resources (skip if already done during local setup)
azd provision

# Build, push, and deploy the agent to Foundry
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke '{"threadId": "thread-1", "runId": "run-1", "state": {}, "messages": [{"id": "msg-1", "role": "user", "content": "Hello"}], "tools": [], "context": [], "forwardedProps": {}}'
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install dependencies in the virtual environment:

  ```bash
  uv sync --frozen
  ```

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## SSE Event Format

Standard AG-UI events are streamed automatically:

```
data: {"type":"RUN_STARTED","threadId":"thread-123","runId":"run-456"}
data: {"type":"TEXT_MESSAGE_START","messageId":"...","role":"assistant"}
data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"...","delta":"Hello"}
data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"...","delta":"! How"}
data: {"type":"TEXT_MESSAGE_END","messageId":"..."}
data: {"type":"RUN_FINISHED","threadId":"thread-123","runId":"run-456"}
```

## Learn More

- [AG-UI Protocol](https://docs.ag-ui.com/introduction) — event types, lifecycle, tools
- [Pydantic AI AG-UI docs](https://ai.pydantic.dev/ag-ui/) — `to_ag_ui()`, `handle_ag_ui_request`
- [AG-UI Dojo](https://dojo.ag-ui.com/) — interactive playground for testing AG-UI agents

## Troubleshooting

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error calling Azure OpenAI: Error code: 401 - {'error': {'code': 'PermissionDenied', 'message': 'The principal <principal-id> lacks the required data action Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action to perform POST /openai/deployments/{deployment-id}/chat/completions operation.'}}
```

The identity running the agent does not have the required RBAC roles on the Azure AI Foundry project. Assign the following roles:

- **Cognitive Services OpenAI User**
- **Foundry User**

Use the Azure CLI to assign them:

```bash
# Set your variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="<your-resource-group>"
PROJECT_NAME="<your-ai-foundry-project-name>"
PRINCIPAL_ID="<principal-id-from-error-message>"

# Assign "Cognitive Services OpenAI User" role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/$PROJECT_NAME"

# Assign "Foundry User" role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Foundry User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/$PROJECT_NAME"
```

> **Note:** It may take a few minutes for role assignments to propagate. Retry the request after waiting.
