# What this sample demonstrates

A minimal **echo** hosted agent built with the **Bring Your Own** approach on the **Activity protocol** in Python, published as a **Microsoft 365 Autopilot** (digital worker) instead of a single-tenant Teams bot. The agent simply repeats whatever the user sends. It demonstrates how [`azure-ai-agentserver-activity`](https://pypi.org/project/azure-ai-agentserver-activity/) acts as the Foundry host while bridging to the [M365 Agents SDK](https://github.com/microsoft/Agents-for-python) for activity processing and outbound channel delivery (for example, Teams) — using the SDK's **digital-worker auth model** instead of the *simple* Teams-agent model used by the [`echo`](../echo) sample.

The protocol SDK takes care of the Foundry platform contract for you — the `POST /activity/messages` endpoint, platform headers, session resolution, OpenTelemetry tracing, error classification, and health probes — leaving you to write only the per-activity handler logic.

## How It Works

Handlers are wired up with the decorator API, exactly like the [`echo`](../echo) sample. The only difference is `digital_worker=True`, which switches the outbound-auth model from the agent **instance** identity to the agent identity **blueprint** (federated identity) — the model that backs a tenant-scoped Autopilot:

```python
from azure.ai.agentserver.activity import ActivityAgentServerHost

host = ActivityAgentServerHost(digital_worker=True)  # Autopilot / digital-worker model
app = host.agent_app

@app.activity("message")
async def on_message(context, state):
    user_text = (context.activity.text or "").strip()
    if user_text:
        await context.send_activity(f"Echo: {user_text}")

host.run()
```

See [main.py](main.py) for the complete implementation, including the `conversationUpdate` welcome handler and the error handler.

### Agent Hosting

The agent runs on the [Azure AI AgentServer Activity SDK](https://pypi.org/project/azure-ai-agentserver-activity/), which exposes a REST API endpoint that speaks the Azure AI Activity protocol.

### Agent Deployment and Publication

Unlike [`echo`](../echo) (which provisions its own Foundry project + Container Registry via `azd provision`), this sample uses **direct code deployment** into an **existing** Foundry project: `azure.yaml` has no `infra:` block, so `azd deploy` packages and ships the Python code straight to the project identified by the active `azd` environment — no Docker build required.

Publishing the agent as a Microsoft 365 Autopilot is a separate, explicit step (`azd ai agent publish`) driven by the `activity.useCase: digital_worker` and `activity.publish` metadata in [azure.yaml](azure.yaml). After publishing, a tenant administrator approves the resulting agent identity blueprint before it can be instantiated in Teams.

## Prerequisites

Make sure the following are installed and available:

| Requirement | Why you need it |
|-------------|-----------------|
| [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Deploys and publishes the agent. Use **1.31.2 or later**. Install the agent service target with `azd extension install azure.ai.agents`. |
| [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli) | Authentication (`az login`). |
| [Python 3.10+](https://www.python.org/downloads/) | The agent runtime (handy for local edits). |
| An existing Microsoft Foundry project and model deployment | This sample does not provision one — see [Configure an existing Foundry project](#configure-an-existing-foundry-project) below. |
| A Microsoft 365 tenant with Microsoft Agent 365 | Required to publish and approve the Autopilot. |

### Required permissions

- **Foundry Project Manager** at the Foundry project scope — deploys the agent, manages sessions, and publishes the Autopilot.
- **AI Administrator** or **Global Administrator** in the Microsoft 365 admin center — approves the published agent identity blueprint.
- A Microsoft 365 license and tenant app policies that allow creating an instance in Teams.

> [!NOTE]
> **Region availability:** This sample relies on [Foundry hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd), so your Foundry project must live in a region that supports them.

## Local Debug in VS Code

Add this folder (`autopilot/`) as a VS Code workspace root, then run `main.py` under the debugger (`python main.py`) after installing `requirements.txt` into a virtual environment. Use [M365 Agents Playground](https://github.com/microsoft/Agents/blob/main/docs/HowTo/Playground.md) to chat with it locally, the same way as the [`echo`](../echo) sample.

## Deploying and Publishing the Agent

### Step 1: Sign in

```powershell
# Install the azd extension that provides `host: azure.ai.agent` (one-time)
azd extension install azure.ai.agents

# Sign in to both CLIs (use the same tenant for both)
az login --tenant <tenant-id>
azd auth login --tenant-id <tenant-id>

# Create an azd environment
azd env new myechoautopilot
```

### Step 2: Point at an existing Foundry project

```powershell
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION <foundry-project-region>
azd env set AZURE_AI_PROJECT_ID <foundry-project-resource-id>
azd env set FOUNDRY_PROJECT_ENDPOINT <foundry-project-endpoint>
```

Copy the project resource ID, endpoint, and region from **Manage** > **Project details** in the Foundry portal. `AZURE_SUBSCRIPTION_ID` is required separately even though the project resource ID contains it, and `AZURE_LOCATION` must match the existing project's region.

### Step 3: Deploy the code

```bash
azd deploy
```

This packages `main.py` and `requirements.txt` and creates a new hosted-agent version in the existing project. It does not publish or update the Microsoft 365 app.

### Step 4: Publish the Autopilot

```bash
azd ai agent publish
```

This reads the `activity.publish` metadata in [azure.yaml](azure.yaml) and submits the Microsoft 365 publication for the agent identity blueprint.

### Step 5: Approve and create an instance

1. An **AI Administrator** or **Global Administrator** opens [Agents in the Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested), approves the pending blueprint, and verifies it appears in the Agent 365 registry.
2. A licensed user opens **Apps** > **Agents for your team** in Teams, selects the approved blueprint, and creates an instance.

### Step 6: Chat with it in Teams

Send the instance a message — it echoes back.

## What the deployment sets up

1. **Container image** *(`azd deploy`).* The `azure.ai.agent` service target packages this Python sample directly (no Dockerfile) into the existing Foundry project.
2. **Agent version + blueprint** *(`azd deploy`).* Creating the agent version makes the Foundry service auto-create the Managed Agent Identity Blueprint (MAIB) used for outbound auth.
3. **Microsoft 365 Autopilot publication** *(`azd ai agent publish`).* Submits the blueprint for tenant-wide Microsoft 365 publication using the `activity.publish` metadata.
4. **Approval + instance** *(Microsoft 365 admin center + Teams).* A tenant admin approves the blueprint, then a licensed user creates an instance in Teams.

## Key files

| File | Purpose |
| --- | --- |
| `azure.yaml` | Hosted-agent deployment + Autopilot publication metadata |
| `main.py` | Activity handlers and the `ActivityAgentServerHost(digital_worker=True)` setup |
| `requirements.txt` | Python runtime dependencies |
