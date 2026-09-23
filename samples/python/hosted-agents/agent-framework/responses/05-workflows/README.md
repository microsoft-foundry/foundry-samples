# Multi-Agent Workflow (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) workflow demonstrating **multi-agent chaining**, hosted on Microsoft Foundry using the **Responses protocol**. It shows how to use the Agent Framework's `WorkflowBuilder` to compose a pipeline of specialized agents — a slogan writer, a legal reviewer, and a formatter — that process a request sequentially. Each agent receives only the output of the previous agent, and only the final formatted result is returned to the caller.

> This sample requires a more advanced model because the model needs to continue the conversation from an assistant message. Not all models perform well in this scenario. Tested with OpenAI's model `gpt-5.4`.

> This sample requires a more advanced model because the model needs to continue the conversation from an assistant message. Not all models perform well in this scenario. Tested with OpenAI's model `gpt-5.4`.

## How it works

The agent creates three specialized `Agent` instances sharing the same `FoundryChatClient`: a **writer** that generates slogans, a **legal reviewer** that ensures compliance, and a **formatter** that styles the output. Each agent is wrapped in an `AgentExecutor` with `context_mode="last_agent"` so it only sees the previous agent's output. The `WorkflowBuilder` wires them into a linear pipeline and limits the output to the formatter's result. The workflow is converted to a standard agent via `.as_agent()` and served via `ResponsesHostServer`. See [main.py](src/agent-framework-workflows-responses/main.py) for the implementation.

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
mkdir my-workflow-agent && cd my-workflow-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/05-workflows/azure.yaml
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
azd ai agent invoke --local "Create a slogan for a new electric SUV that is affordable and fun to drive."
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "Create a slogan for a new electric SUV that is affordable and fun to drive."
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
- [Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/) — learn more about building workflows
- [Workflow as an agent](https://learn.microsoft.com/en-us/agent-framework/workflows/as-agents?pivots=programming-language-python) — serving workflows via the Responses protocol
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
- [Basic agent](../01-basic/) — minimal agent with no tools
- [Declarative workflows](../06-declarative-customer-support/) — YAML-defined workflow with multi-turn routing
