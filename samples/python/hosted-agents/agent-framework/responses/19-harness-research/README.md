# What this sample demonstrates

This sample hosts the Microsoft Agent Framework **research harness** on Microsoft Foundry using the **Responses protocol v2**. The agent plans research, tracks todos, searches the web, compacts long context, saves notes in file memory, and loops autonomously while execute-mode todos remain.

## How it works

Give the agent a research goal. It proposes a plan; after you confirm it, the agent searches the web, tracks remaining tasks, saves notes, and returns a sourced summary. Continue the same conversation to refine or extend the research.

### Conversation and session behavior

The Responses protocol owns conversation history, while the hosted session owns filesystem-backed harness memory. The `azd` CLI saves and reuses both automatically. Use `--new-conversation --new-session` to start over.

`create_harness_agent` normally adds an `InMemoryHistoryProvider` that reloads its saved messages. Hosted Responses agents must instead set `load_messages=False` because the host already passes the Responses conversation into each run. The provider remains as a write-only part of the harness's per-service-call persistence pipeline; it is not a second conversation store. Use the Responses conversation ID for cross-turn continuity.

The agent stores file memory under `$HOME/agent-file-memory`. In Foundry, `$HOME` belongs to the hosted session and persists across turns and idle periods; deleting the session removes that filesystem. Local runs fall back to the current working directory when `$HOME` is unavailable.

### Deployment modes

This sample supports both hosted-agent deployment modes:

- **Direct code deployment:** The checked-in `azure.yaml` uses `codeConfiguration` with the Python 3.13 runtime and `main.py` entry point. Docker and Azure Container Registry (ACR) are not required.
- **Container deployment:** Select **Container** during initialization or deployment to build the included Python 3.13 `Dockerfile`. This path requires Docker and an ACR.

For container deployment, the deploying identity needs permission to build or push images to the ACR. The hosted agent identity also needs `AcrPull`; the deploying identity must be allowed to create that role assignment, or an administrator must grant it.

## Prerequisites

1. An existing Foundry project with a deployed `gpt-5.4` model, or permission to create them during Option 1.
2. **Python 3.13 or later.**
3. An identity with the **Foundry User** role on the project. Deploying to an existing project requires **Foundry Project Manager**.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd).
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No clone is required:

```bash
mkdir harness-research-responses
cd harness-research-responses
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/19-harness-research/azure.yaml
```

Choose an existing Foundry project and model deployment, or let the prompts configure a new project. The manifest defaults to direct code deployment. To initialize explicitly for container deployment, append `--deploy-mode container`.

### Provision Azure resources (if needed)

Run this when initialization configured a new Foundry project, model deployment, or container registry:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The host starts on `http://localhost:8088`, and Agent Inspector opens automatically.

### Invoke the local agent

From a second terminal in the initialized project:

```bash
azd ai agent invoke --local "Research the latest advances in small language models."
```

Continue on the saved conversation and session:

```bash
azd ai agent invoke --local "Compare the strongest approaches and cite the sources."
```

### Deploy to Foundry

```bash
azd deploy
```

For deployment details, see [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "Research post-quantum cryptography adoption."
```

Use `--new-conversation --new-session` when you want a clean research task.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then run `az login` in the VS Code integrated terminal.

### Set up the Python virtual environment

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
   pipx install uv==0.11.7
   uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

### Run and debug the agent

Return to the sample root and press **F5**. Select **Debug Hosted Agent in Inspector** if prompted. VS Code starts the host on port `8088`, attaches the debugger on port `5679`, and opens Agent Inspector.

Send this prompt:

```text
Research the latest advances in small language models.
```

Use the same Inspector conversation for follow-up turns so the plan, todos, and file memory remain available.

### Or run manually, then open the Inspector

1. Set the environment variables in `.env` and authenticate with `az login`.
2. From `src/agent-framework-harness-research-responses`, run `uv run --no-sync python main.py`.
3. Open the Command Palette and run **Foundry Toolkit: Open Agent Inspector**.
4. Connect to `http://localhost:8088` and send the prompt above.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to identify the service source folder and auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select the subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, choose CPU and memory, and select **Deploy**.

After deployment, open the **Agent Playground** link from the deployment result and send the prompt above to verify the remote agent. Keep follow-ups in the same Playground conversation, and stream live logs from the **Logs** tab.

## Try the plan-to-execute flow

```bash
azd ai agent invoke --local "Research small language models for consumer phones and laptops in 2026."
azd ai agent invoke --local "The plan looks good. Execute it."
azd ai agent invoke --local "Continue until all todos are complete."
```

The first turn creates a plan. Approval switches the harness to execute mode, where the continuation predicate keeps working through open todos.

## Troubleshooting

- **`FOUNDRY_PROJECT_ENDPOINT` is missing:** use `azd ai agent run`, or populate the service `.env` file for direct Python/F5 runs.
- **Model deployment not found:** make `AZURE_AI_MODEL_DEPLOYMENT_NAME` match a deployment in the selected Foundry project.
- **Container deployment cannot push or pull the image:** verify the deploying identity has the required ACR build/push role and that the hosted agent identity has `AcrPull`.
- **Container provisioning fails on `roleAssignments/write`:** ask an Owner, User Access Administrator, or Role Based Access Control Administrator to grant the required ACR roles.
- **A follow-up lost its plan:** the conversation or session changed. Continue without reset flags, or pass the saved IDs explicitly.
- **Port `8088` or `5679` is occupied:** stop the other local host/debugger before pressing F5.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Microsoft Agent Framework harness source](https://github.com/microsoft/agent-framework/tree/848443ac68b9470de5c43c3a355829625d7f0a3a/python/samples/02-agents/harness)
- [Manage hosted agents](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-agent)
