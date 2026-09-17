# What this sample demonstrates

A realistic **multi-turn** [Agent Framework](https://github.com/microsoft/agent-framework) **declarative workflow** — defined entirely in YAML — hosted using the **Responses protocol**. It shows how a declarative workflow that invokes multiple Foundry-hosted agents can run end-to-end on every user turn while reading the prior conversation through `Conversation.messages` (populated automatically by `Workflow.as_agent()`).

> Read more about declarative workflows in the [Agent Framework documentation](https://learn.microsoft.com/en-us/agent-framework/workflows/declarative/?pivots=programming-language-python) and about workflow-as-an-agent in the [Workflow as an Agent documentation](https://learn.microsoft.com/en-us/agent-framework/workflows/as-agents?pivots=programming-language-python).

> [!IMPORTANT]
> Deploy this sample as a **container** (not Code/ZIP). Its declarative workflow uses Power Fx, which needs the .NET runtime included in the `Dockerfile`. Choose **Container** in every deploy flow.

## How It Works

### The Workflow

[`workflow.yaml`](src/agent-framework-declarative-customer-support-responses/workflow.yaml) describes a customer-support triage flow:

1. `InvokeAzureAgent: TriageAgent` — looks at the full conversation so far and emits a structured `TriageResponse` (`Category`, `NeedsClarification`, `ClarificationQuestion`, `Reply`).
2. `ConditionGroup` routes on the triage decision:
   - **NeedsClarification** → `SendActivity` asks one focused follow-up question and ends the turn.
   - **Category = "Technical"** → `SendActivity` confirms the handoff, then `InvokeAzureAgent: TechSupportAgent` answers with `autoSend: true` so its reply streams directly to the caller.
   - **Category = "Billing"** → same pattern, routed to `BillingAgent`.
   - **else** → `SendActivity` returns the triage agent's `Reply` directly (good for greetings or general questions).

Each user message re-runs the workflow from the trigger. Because `Workflow.as_agent()` populates `Conversation.messages` with the prior turns of the conversation, every `InvokeAzureAgent` call sees the full history — which is what makes the triage decision and the specialist follow-ups coherent across turns.

### Agent Hosting

[`main.py`](src/agent-framework-declarative-customer-support-responses/main.py) builds three `Agent` instances on top of a shared `FoundryChatClient` (one per workflow role), registers them with the `WorkflowFactory` so the YAML's `InvokeAzureAgent` actions can resolve them by name, loads the workflow, wraps it with `.as_agent(...)`, and hands the agent to `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

The triage agent is configured with `response_format=TriageResponse` (a Pydantic model) so the workflow can read its structured fields via `Local.Triage.*`. The specialist agents are plain text and use `autoSend: true` to deliver their reply straight to the caller.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. **.NET 10 Runtime** for local runs — [Install .NET 10](https://dotnet.microsoft.com/download/dotnet/10.0). The container image installs it automatically.
3. Install the AI agent extension:
   ```bash
   azd ext install microsoft.foundry
   ```
4. Authenticate:
   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-declarative-agent && cd my-declarative-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/09-declarative-customer-support/azure.yaml
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

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "I have a problem"
```

A typical multi-turn session:

```bash
azd ai agent invoke --local "I have a problem"
# → "Could you tell me a bit more about what's going on?"

azd ai agent invoke --local "My laptop won't turn on"
# → "Connecting you with technical support..."
# → TechSupportAgent: "Let's start simple — is the charger LED on when plugged in?"

azd ai agent invoke --local "Yes the LED is on"
# → TechSupportAgent: "Great. Try a hard reset: hold the power button for 30 seconds..."
```

Or for billing:

```bash
azd ai agent invoke --local "I was double-charged this month"
# → "Connecting you with billing support..."
# → BillingAgent: "I'm sorry about that. Can you share the last 4 digits of the card on file?"
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "I have a problem"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **.NET 10 Runtime** for local runs — [Install .NET 10](https://dotnet.microsoft.com/download/dotnet/10.0). The container image installs it automatically.

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
3. On the **Basics** tab, choose **Container** as the deployment method (this sample requires it — see the note above) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
