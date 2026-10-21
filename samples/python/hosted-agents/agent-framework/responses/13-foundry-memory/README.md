# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with persistent semantic memory backed by an **Azure AI Foundry Memory Store**, hosted using the **Responses protocol**. The agent remembers facts the user has shared (e.g., dietary preferences, name) across sessions by retrieving and updating memories around every model invocation via `FoundryMemoryProvider`.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. `allow_preview=True` is passed so the same `AIProjectClient` can also call the preview `beta.memory_stores` API.

### Memory via Foundry Memory Store

`FoundryMemoryProvider` is wired into the agent as a context provider. Around each model invocation it:

1. **Retrieves user-profile memories** for the configured `scope` (e.g., user id) on the first turn of a session.
2. **Searches for contextual memories** matching the current user message and injects them into the model context.
3. **Updates the store** with new facts inferred from the conversation.

Crucially, the provider is constructed with `project_client=client.project_client` — i.e. it reuses the `AIProjectClient` that `FoundryChatClient` already created, instead of allocating a second one. This keeps a single authentication context and connection pool for both chat and memory operations.

See [main.py](src/agent-framework-agent-foundry-memory-responses/main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- An Azure AI Foundry project with:
  - A deployed chat model (e.g., `gpt-5.4-mini`)
  - A deployed embedding model (e.g., `text-embedding-3-small`) — used by the memory store itself, not by the agent at runtime
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs **Azure AI User** on the Foundry project scope. This role covers provisioning the memory store with `provision_memory_store.py` and reading/writing memories from `main.py`.

The memory store embeds and retrieves memories through the project's inference endpoint, so the same identity also needs **Cognitive Services OpenAI User** on the Foundry project scope to call the embedding deployment. Without it, memory writes fail with a `401` (`Authentication to the Azure OpenAI resource failed`) and the store stays empty. When deploying, grant both roles to the hosted agent's runtime identity (the `…-AgentIdentity` service principal) at the project scope.


## Option 1: Azure Developer CLI (`azd`)

The manifest declares the chat and embedding deployments, and the bundled
`postprovision` hook creates the Foundry Memory Store after `azd provision`.
It also sets `MEMORY_STORE_NAME` for you.

### 1. Install prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.34.2 or later)
2. Install the unified Foundry CLI extension bundle:
   ```bash
   azd ext install microsoft.foundry
   ```
3. Authenticate:
   ```bash
   azd auth login
   ```

### 2. Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-memory-agent && cd my-memory-agent

azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/13-foundry-memory/azure.yaml
```

Follow the prompts to configure your Foundry project. If you don't have an
existing Foundry project, `azd ai agent init` will guide you through creating
one. Initializing also sets the selected project as the active project and
copies this sample's files into a new service directory `src/<agent-name>/`,
including [`provision_memory_store.py`](src/agent-framework-agent-foundry-memory-responses/provision_memory_store.py)
and the [`hooks/`](hooks/) scripts.

### 3. Provision

The manifest includes the `gpt-5.4-mini` chat deployment and the
`text-embedding-3-small` embedding deployment. The embedding deployment powers
the store's semantic memory, not the agent at runtime:

```bash
azd provision
```

`azd provision` creates (or reuses) your Foundry project and both model
deployments, then the registered `postprovision` hook:

1. Runs [`provision_memory_store.py`](src/agent-framework-agent-foundry-memory-responses/provision_memory_store.py) to create the Foundry Memory Store (user-profile capability enabled, chat-summary disabled) and verifies it on the service.
2. Sets `MEMORY_STORE_NAME` in the `azd` environment so the agent reads and writes that store.

> The hook defaults `MEMORY_STORE_NAME` to `agent_framework_memory`. To use a different name, set it first: `azd env set MEMORY_STORE_NAME "<your-store-name>"`.

### 4. Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "Hi, my name is Alex and I'm vegetarian."
```

### 5. Deploy to Foundry

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

The deployed agent's Managed Identity needs **Azure AI User** on the Foundry project to read and write memories at runtime. The `postprovision` hook already created the memory store against that same project.

### 6. Invoke the deployed agent

```bash
azd ai agent invoke "Do you remember my name and what I like to eat?"
```

### Provision manually (without the hook)

Prefer to run the step yourself (or skip the hook)? [`provision_memory_store.py`](src/agent-framework-agent-foundry-memory-responses/provision_memory_store.py) creates a Foundry Memory Store with the user-profile capability enabled (and chat-summary disabled) using `AIProjectClient.beta.memory_stores.create`. It is safe to re-run: if a store with the same name already exists, the script leaves it alone.

From the project directory, with the venv activated and `az login` done:

```bash
pip install azure-ai-projects azure-identity aiohttp python-dotenv

export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
export AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME="text-embedding-3-small"
export MEMORY_STORE_NAME="agent_framework_memory"
python provision_memory_store.py
```

In PowerShell, use `$env:NAME="value"` instead of `export`. Then point the agent at the same store name:

```bash
azd env set MEMORY_STORE_NAME "agent_framework_memory"
```

Expected output (first run):

```text
Creating memory store 'agent_framework_memory'...
Created memory store 'agent_framework_memory' (id=memstore_...).
```

> To delete the store manually, call `project.beta.memory_stores.delete("<name>")` on an `AIProjectClient` constructed with `allow_preview=True`.

## Option 2: VS Code (Foundry Toolkit)

> The VS Code flow doesn't run the `azd` hook — provision the memory store first with [Provision manually](#provision-manually-without-the-hook).

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install dependencies in the virtual environment:

  ```bash
  # use uv to accelerate
  pip install uv
  uv pip install -r requirements.txt

  # or pure pip
  pip install -r requirements.txt
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

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
