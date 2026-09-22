# What this sample demonstrates

A minimal **echo** hosted agent built with the **Bring Your Own** approach on the **Activity protocol** in Python. The agent simply repeats whatever the user sends, making it the cleanest possible starting point for Activity protocol agents. It demonstrates how [`azure-ai-agentserver-activity`](https://pypi.org/project/azure-ai-agentserver-activity/) acts as the Foundry host while bridging to the [M365 Agents SDK](https://github.com/microsoft/Agents-for-python) for activity processing and outbound channel delivery (for example, Teams).

The protocol SDK takes care of the Foundry platform contract for you — the `POST /activity/messages` endpoint, platform headers, session resolution, OpenTelemetry tracing, error classification, and health probes — leaving you to write only the per-activity handler logic.

## How It Works

Handlers are wired up with the decorator API. When a `message` activity comes in, the host forwards it to the M365 SDK and calls your handler:

```python
from azure.ai.agentserver.activity import ActivityAgentServerHost

host = ActivityAgentServerHost()  # simple Teams agent model (default)
app = host.agent_app

@app.activity("message")
async def on_message(context, state):
    user_text = (context.activity.text or "").strip()
    if user_text:
        await context.send_activity(f"Echo: {user_text}")

host.run()
```

See [main.py](src/echo-activity/main.py) for the complete implementation, including the `conversationUpdate` welcome handler and the error handler.

### Agent Hosting

The agent runs on the [Azure AI AgentServer Activity SDK](https://pypi.org/project/azure-ai-agentserver-activity/), which exposes a REST API endpoint that speaks the Azure AI Activity protocol.

### Agent Deployment

You build and ship the agent to Microsoft Foundry with the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd) using the **native** `azure.ai.agent` flow. The [azure.yaml](azure.yaml) is checked in (Foundry provider), so `azd provision` stands up the platform (Foundry project + Container Registry) and `azd deploy` builds the image, creates the agent version (the Foundry service auto-creates the agent identity blueprint and instance identity), and the azd foundry extension registers the Azure Bot + Microsoft Teams channel for you.

## Prerequisites

Make sure the following are installed and available:

| Requirement | Why you need it |
|-------------|-----------------|
| [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Provisions infrastructure and deploys the agent. Use **1.25 or later** (earlier versions have a container-registry resolution bug during remote build). Install the agent service target with `azd extension install azure.ai.agents`. |
| [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli) | Authentication (`az login`). |
| [Python 3.10+](https://www.python.org/downloads/) | The agent runtime (built inside the Docker image; also handy for local edits). |
| [Docker](https://www.docker.com/products/docker-desktop/) | **Optional.** `azd deploy` uses a remote ACR build, so you don't need Docker unless you want to build the image locally. |

### Required permissions

For the default flow (provision + deploy + sideload into your own Teams):

- **Owner** (or **Contributor + User Access Administrator**) on the target subscription — the deploy creates role assignments.
- **Azure AI User** or **Cognitive Services User** at the subscription or resource-group scope.

Only needed for the **org-wide** path (publishing to your tenant app catalog), not the default sideload:

- **Teams admin** (`AppCatalog.ReadWrite.All`) to publish to the org app catalog.
- **Tenant admin** to approve a tenant-wide configuration.

> [!IMPORTANT]
> **Pick a unique agent name before your first deploy.** The agent name becomes the GLOBAL
> Azure Bot name (`<agent-name>-bot-uai`), which must be unique. If you keep the default
> `echo-activity`, the bot-creation step can fail with `"The requested bot name is not available"`
> because someone (or a previous deploy) already claimed it. Pick a short, lowercase name and
> set it as the service key and `name:` in [azure.yaml](azure.yaml) (keep the two in sync).

> [!NOTE]
> **Region availability:** This sample relies on [Foundry hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd), so your Foundry account and related resources must live in a region that supports them. See the [hosted-agent region list](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd) for the current set (it changes over time).


## Local Debug in VS Code

### Step 1: Open the correct workspace folder

The launch configuration and tasks are defined inside `src/echo-activity/`, not the repo root. VS Code must have that folder loaded as a workspace root before F5 works.

If you opened the repo root folder, add the inner folder first:

1. **File → Add Folder to Workspace…**
2. Select `src/echo-activity/` and click **Add**.

The Explorer panel should now show `echo-activity` as a workspace root (with its own `.vscode/` visible). You can then save this as a multi-root workspace file if you like.

### Step 2: Press F5

Press **F5** (or **Run → Start Debugging**). The launch configuration will:

1. Install `agentsplayground` if not already installed (one-time, via winget).
2. Create a `.venv` (Python 3.13) and install `requirements.txt` if not already done.
3. Start the agent (`main.py`) under the VS Code debugger.
4. Launch **M365 Agents Playground** automatically once port 8088 is ready.

When the debug session ends, the `postDebugTask` kills `agentsplayground` and any process still bound to port 8088.

Once the Playground window opens, type a message — the agent echoes it back. You can set breakpoints in `main.py` as with any Python project.

## Deploying the Agent to Microsoft Foundry

### Step 1: Sign in

```powershell
# Install the azd extension that provides `host: azure.ai.agent` (one-time)
azd extension install azure.ai.agents

# Sign in to both CLIs
az login
azd auth login

# Create an azd environment (its name prefixes the Azure resources)
azd env new myecho
```

### Step 2: Provision and deploy

```bash
azd provision   # Foundry project + Container Registry
azd deploy      # remote ACR build → agent version → Bot + Teams channel (postdeploy)
```

`azd deploy` runs a remote ACR build, pushes the image, creates the **agent version** from
the checked-in [azure.yaml](azure.yaml) (the Foundry service auto-creates the blueprint + the
agent **instance** identity), and patches the `activity` protocol onto the agent endpoint. The
azd foundry extension's postdeploy then registers the **Azure Bot** (instance identity) and
the **Microsoft Teams** channel.

### Step 3: Chat with it in Teams

Package and install the Teams app using the generated `TEAMS_APP_SETUP.md`
guide, then open **Microsoft Teams**, find your agent in the chat list (or under
**Apps → Manage your apps**), send it a message, and it echoes back.

> [!NOTE]
> If **Upload a custom app** is greyed out, custom-app upload is disabled for your account —
> ask an admin to enable it (Teams Admin Center → **Teams apps** → **Setup policies**), or
> publish the package to your organization's app catalog for tenant-wide availability.

## What the deployment sets up

A single deploy wires together several pieces to produce a working Teams agent:

1. **Foundry project + ACR** *(`azd provision`).* A project enabled for hosted agents and a Container Registry to build and store images.

2. **Container image** *(`azd deploy`).* The `azure.ai.agent` service target builds this Python sample into a Docker image with a remote ACR build and pushes it.

3. **Agent version + blueprint + instance identity** *(`azd deploy`).* Creating the agent version makes the Foundry service auto-create the Managed Agent Identity Blueprint (MAIB) and provision the agent **instance** identity used for outbound auth — then `azd` patches the `activity` protocol onto the agent endpoint.

4. **Azure Bot + Teams channel** *(foundry extension postdeploy).* An instance-identity bot (`<agent-name>-bot-uai`) whose `msaAppId` is the agent **instance** identity, configured with the agent endpoint and the Microsoft Teams channel.


<!-- Temporary PR used to verify public Azure Pipelines PR event delivery. -->
