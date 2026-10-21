**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Human-in-the-Loop Agent (Invocations Protocol) — .NET

This sample demonstrates a human-in-the-loop agent built with [Azure.AI.AgentServer.Invocations](https://pkgs.dev.azure.com/azure-sdk/public/_packaging/azure-sdk-for-net/nuget/v3/index.json) that implements an **approval-gate pattern**. The agent generates a proposal using Azure OpenAI, pauses for human review, and resumes execution after the human approves, requests a revision, or rejects.

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
2. **The agent pauses** — the proposal is saved to disk, and the human can return at any time (minutes, hours, or days later).
3. **Respond with a decision** via another `POST /invocations` using the same `agent_session_id`:
   - `approve` — the agent marks the proposal as final and returns it.
   - `revise` (with feedback) — the agent generates an improved proposal incorporating the feedback.
   - `reject` — the agent marks the session as rejected.
4. **Poll status** via `GET /invocations/{id}` — useful for checking whether a proposal is still pending after reconnecting.
5. **Cancel** via `POST /invocations/{id}/cancel` — cancels a pending session.

## Prerequisites

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.

### Environment variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-resource.openai.azure.com/api/projects/proj"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
```

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
mkdir human-in-the-loop-agent && cd human-in-the-loop-agent
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/bring-your-own/invocations/human-in-the-loop/azure.yaml
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

In a separate terminal, submit a task:

```bash
azd ai agent invoke --local '{"task": "Write a product launch announcement for Azure AI Foundry"}'
```

In PowerShell:

```powershell
azd ai agent invoke --local '{\"task\": \"Write a product launch announcement for Azure AI Foundry\"}'
```

This sample uses an approval-gate flow — submit a task, then approve, revise, or reject via curl using the same `agent_session_id`:

```bash
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
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke '{"task": "Write a product launch announcement for Azure AI Foundry"}'
```

Stream logs from the running agent with `azd ai agent monitor`.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   dotnet restore
   ```

2. Configure the agent: copy `.env.example` to `.env` and fill in the values. The agent loads `.env` automatically on startup.

3. Sign in to Azure with the Azure CLI:

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

## Project Structure

```
human-in-the-loop/
├── README.md                 # This file
├── azure.yaml                # Unified manifest — project, model, and agent (name, protocols, resources, env vars)
└── src/
    └── human-in-the-loop-dotnet-invocations/
        ├── Program.cs                # Entry point, DI setup, and InvocationHandler implementation
        ├── SessionStore.cs           # Session state persistence (JSON files in $HOME)
        ├── human-in-the-loop.csproj  # Project file with NuGet dependencies
        ├── Dockerfile                # Multi-stage Docker build
        ├── .dockerignore             # Docker build exclusions
        └── .env.example              # Example environment variables
```

## Troubleshooting

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error calling Azure OpenAI: Error code: 401 - {'error': {'code': 'PermissionDenied', ...}}
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
