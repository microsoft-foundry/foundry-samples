# Note-Taking Agent — Python (Invocations Protocol)

A note-taking agent built with `azure-ai-agentserver-invocations` and Azure OpenAI. Uses function calling to save and retrieve notes, with per-session JSONL persistence accessible via the Session Files API.

## Features

- **Save notes** — natural language commands like "save a note - buy groceries"
- **Retrieve notes** — "show me my notes" returns all saved entries with timestamps
- **Per-session isolation** — each session gets its own note file
- **Streaming responses** — real-time SSE streaming via the Invocations protocol
- **Session Files API** — notes stored at `$HOME` are accessible via the platform file API

## Prerequisites

- Python 3.12+
- Azure OpenAI resource with a deployed model (e.g., `gpt-5.4-mini`)
- Azure credentials configured (e.g., `az login`)

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint (auto-injected when deployed) | `https://account.services.ai.azure.com/api/projects/proj` |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name | `gpt-5.4-mini` |

## Option 1: Azure Developer CLI (`azd`)

### Run the agent locally

```bash
azd ai agent run
```

### Invoke the local agent

```bash
azd ai agent invoke --local '{"message": "save a note - book reservation for dinner"}'
```

Or invoke directly with curl:

```bash
# Save a note
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=my-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "save a note - book reservation for dinner"}'

# Save another note
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=my-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "save a note - buy groceries for the weekend"}'

# Get all notes
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=my-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "show me all my notes"}'

# New session (isolated)
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=another-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "show me my notes"}'
```

### Deploy to Foundry

```bash
azd provision
azd deploy
```

### Invoke the deployed agent

```bash
azd ai agent invoke '{"message": "save a note - book reservation for dinner"}'
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/notetaking-agent-invocations-python

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/notetaking-agent-invocations-python/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/notetaking-agent-invocations-python`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## File Structure

| File | Description |
|---|---|
| `main.py` | Agent entry point with Invocations handler and OpenAI function calling |
| `note_store.py` | Thread-safe per-session JSONL note persistence |
| `pyproject.toml` / `uv.lock` | Python dependencies and reproducible lock |
| `Dockerfile` | Container image definition with SSL cert support |
| `azure.yaml` | Agent hosting configuration |
| `azure.yaml` | Agent metadata and template |
| `.dockerignore` | Docker build exclusions |

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
