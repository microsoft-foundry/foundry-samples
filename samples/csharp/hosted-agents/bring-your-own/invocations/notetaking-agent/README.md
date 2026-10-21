**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Note-Taking Agent — Invocations Protocol

This sample demonstrates a note-taking agent built with [Azure.AI.AgentServer.Invocations](https://www.nuget.org/packages/Azure.AI.AgentServer.Invocations) that uses **Azure OpenAI function calling** for intent understanding, **SSE streaming** for real-time token delivery, and **local JSONL file storage** for session-persistent notes.

## How It Works

The agent receives natural language messages via `POST /invocations` and uses Azure OpenAI with two tool definitions — `save_note` and `get_notes` — to understand user intent. When the LLM returns a tool call, the agent executes it locally (reads/writes a JSONL file) and streams the LLM's natural language response back as Server-Sent Events.

Notes are stored per session in `notes_{session_id}.jsonl` files, demonstrating **session persistence** — notes survive across multiple invocations within the same session. The session ID is resolved automatically from the `agent_session_id` query parameter.

## Prerequisites

1. An existing Foundry project with a deployed model (e.g., `gpt-5.4-mini`), or create them during setup in Option 1.
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.

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
mkdir notetaking-agent && cd notetaking-agent
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/bring-your-own/invocations/notetaking-agent/azure.yaml
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

```bash
azd ai agent invoke --local '{"message": "save a note - book reservation for dinner"}'
```

In PowerShell:

```powershell
azd ai agent invoke --local '{\"message\": \"save a note - book reservation for dinner\"}'
```

Or use curl directly. Pass a stable `agent_session_id` to persist notes across calls; the `-N` flag streams SSE tokens as they arrive:

```bash
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=my-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "save a note - book reservation for dinner"}'

curl -N -X POST "http://localhost:8088/invocations?agent_session_id=my-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "save a note - buy groceries"}'

curl -N -X POST "http://localhost:8088/invocations?agent_session_id=my-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "get all my notes"}'

# Start a new session
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=new-session" \
  -H "Content-Type: application/json" \
  -d '{"message": "get all my notes"}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke '{"message": "save a note - book reservation for dinner"}'
```

Stream logs from the running agent with `azd ai agent monitor`.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector:

![Agent Inspector](../../../../assets/agent-inspector-invocations.png)

Try sending `{"message": "save a note - book reservation for dinner"}`, then `{"message": "get all my notes"}`. Click **Clear Conversation** (top-right) to start a new session.

### Or run manually, then open the Inspector

1. Sign in to Azure with the Azure CLI (`az login`) and build:

   ```bash
   dotnet build
   ```

   Copy `.env.example` to `.env` and fill in the values (the agent loads `.env` automatically on startup).

2. Start the agent: `dotnet run` (listens on `http://localhost:8088`).
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
