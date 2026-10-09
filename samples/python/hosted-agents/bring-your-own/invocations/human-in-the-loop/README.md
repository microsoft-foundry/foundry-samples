**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Human-in-the-Loop Agent — Invocations Protocol

This sample demonstrates a human-in-the-loop agent built with [azure-ai-agentserver-invocations](https://pypi.org/project/azure-ai-agentserver-invocations/) that implements an **approval-gate pattern**. The agent generates a proposal using Azure OpenAI, pauses for human review, and resumes execution after the human approves, requests a revision, or rejects.

Session state is persisted as JSON files in the `$HOME` directory, so proposals survive agent restarts and are accessible via the **Session Files API** when deployed to Azure.

This pattern is useful for workflows where an AI agent should **not act autonomously** — for example, drafting communications, generating code changes, or proposing decisions that require human sign-off.

## How It Works

```
[new task] ──► AWAITING_APPROVAL ──► (approve) ──► COMPLETED
                    │
                    ├──► (revise + feedback) ──► AWAITING_APPROVAL (loop)
                    │
                    └──► (reject) ──► REJECTED
```

1. **Submit a task** via `POST /invocations` — the agent calls Azure OpenAI to generate a proposal and returns it with status `awaiting_approval`.
2. **The agent pauses** — the proposal is saved in memory, and the human can return at any time (minutes, hours, or days later).
3. **Respond with a decision** via another `POST /invocations` using the same `agent_session_id`:
   - `approve` — the agent marks the proposal as final and returns it.
   - `revise` (with feedback) — the agent generates an improved proposal incorporating the feedback.
   - `reject` — the agent marks the session as rejected.
4. **Poll status** via `GET /invocations/{id}` — useful for checking whether a proposal is still pending after reconnecting.

## OpenAPI Spec

The agent includes an inline OpenAPI 3.0 specification that documents the request/response contract. It is served at:

```
GET http://localhost:8088/invocations/docs/openapi.json
```

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12+
- Azure CLI installed and authenticated (`az login`)
- Azure OpenAI resource with a deployed model

### Run the agent locally

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Invoke the local agent

**Bash:**
```bash
azd ai agent invoke --local '{"task": "Write a product launch announcement for Azure AI Foundry"}'
```

Or drive the full multi-step approval flow with curl:

```bash
# Fetch the OpenAPI spec
curl http://localhost:8088/invocations/docs/openapi.json

# Step 1: Submit a task — agent generates a proposal
curl -X POST "http://localhost:8088/invocations?agent_session_id=session-1" \
  -H "Content-Type: application/json" \
  -d '{"task": "Draft a marketing email for our new AI product launch"}'
# -> {"status": "awaiting_approval", "proposal": "...", "session_id": "session-1", ...}

# Step 2: Check status (e.g., after reconnecting hours later)
curl http://localhost:8088/invocations/<invocation_id>
# -> {"status": "awaiting_approval", "proposal": "...", ...}

# Step 3a: Approve the proposal
curl -X POST "http://localhost:8088/invocations?agent_session_id=session-1" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve"}'
# -> {"status": "completed", "final_output": "...", ...}

# Step 3b: Or request a revision with feedback
curl -X POST "http://localhost:8088/invocations?agent_session_id=session-1" \
  -H "Content-Type: application/json" \
  -d '{"decision": "revise", "feedback": "Make the tone more casual and add a call-to-action"}'
# -> {"status": "awaiting_approval", "proposal": "<revised draft>", ...}

# Step 3c: Or reject
curl -X POST "http://localhost:8088/invocations?agent_session_id=session-1" \
  -H "Content-Type: application/json" \
  -d '{"decision": "reject"}'
# -> {"status": "rejected", ...}

# Cancel a pending session
curl -X POST http://localhost:8088/invocations/<invocation_id>/cancel
# -> {"status": "cancelled", ...}
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd provision
azd deploy
```

### Invoke the deployed agent

```bash
azd ai agent invoke '{"task": "Write a product launch announcement for Azure AI Foundry"}'
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
  cd src/human-in-the-loop-invocations

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/human-in-the-loop-invocations/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/human-in-the-loop-invocations`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
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
