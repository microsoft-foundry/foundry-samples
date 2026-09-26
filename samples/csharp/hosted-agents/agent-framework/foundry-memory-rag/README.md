# What this sample demonstrates

A personal coach hosted agent with persistent per-user memory, the **Foundry Memory RAG Agent (Responses Protocol)** sample shows how to ground answers in user-private memories that survive across requests and across sessions, using `FoundryMemoryProvider` from [Agent Framework](https://github.com/microsoft/agent-framework) on top of the [Foundry Memory](https://learn.microsoft.com/azure/ai-foundry/) service.

## How It Works

The agent registers a `FoundryMemoryProvider` as an `AIContextProvider`. When the user shares training goals, dietary preferences, injuries, or scheduling constraints, the framework writes those facts to a project-scoped Foundry Memory store. On every subsequent turn (and on requests in brand new sessions) the framework retrieves the most relevant memories and injects them as context for the model, which composes its answer grounded in what it already knows about the user.

The store is created on startup via `EnsureMemoryStoreCreatedAsync` (idempotent), so a fresh `azd provision` produces a fully working agent on first invocation.

> [!NOTE]
> Provisioning of the Foundry project, model deployments, and supporting Azure resources is handled by the [`azd-ai-starter-basic`](https://github.com/Azure-Samples/azd-ai-starter-basic) template, which `azd ai agent init` pulls in automatically. The chat and embedding deployments declared under `resources:` in `azure.yaml` flow into the starter's `AI_PROJECT_DEPLOYMENTS` parameter.

> [!NOTE]
> Memory is partitioned per invoking user through `HostedFoundryMemoryProviderScopes.PerUser()` in
> [Program.cs](src/foundry-memory-rag/Program.cs). Foundry supplies the user identity when hosted;
> for local testing, pass a distinct `--user-identity` for each user as shown below.

See [Program.cs](src/foundry-memory-rag/Program.cs) for the full implementation.

## Prerequisites

1. An existing Foundry project with **chat and embedding model deployments** (or create them during setup in Option 1 — `azd provision` can create them for you).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Chat model deployment name. Declared in `azure.yaml`. |
| `AZURE_AI_EMBEDDING_DEPLOYMENT_NAME` | Yes | Embedding model deployment name (used by Foundry Memory). Declared in `azure.yaml`. |
| `AZURE_AI_MEMORY_STORE_ID` | No | Memory store name. Defaults to `foundry-memory-rag-store`. The store is created on startup if it does not exist. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

When using `azd ai agent run`, these are handled automatically. For manual runs, set them in your shell — .NET does not read `.env` files natively.

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
mkdir foundry-memory-rag-agent && cd foundry-memory-rag-agent
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/foundry-memory-rag/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployments. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

> If you already have a Foundry project and model deployments, add `-p <project-id> -d <chat-deployment-name>` to `azd ai agent init` to target existing resources. You also need an embedding deployment (default `text-embedding-3-small`); set its name via `AZURE_AI_EMBEDDING_DEPLOYMENT_NAME` if it differs from the default.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployments:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

Run a few turns to seed memory, then ask the agent to recall:

```bash
azd ai agent invoke --local --user-identity demo-user "Remember that I want to run my first 5k in October and I prefer morning workouts."
azd ai agent invoke --local --user-identity demo-user "I have a sensitive left knee, please avoid high-impact exercises."
azd ai agent invoke --local --user-identity demo-user "What do you already know about my training goals?"
```

The identity value selects the user's private memory scope. Use a different value to verify isolation.
Memory extraction is asynchronous server-side, so expect a few seconds between the teaching turn and the recall turn.

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry (this also runs provisioning if needed):

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke --user-identity demo-user "What do you already know about my training goals?"
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

2. Configure the agent: copy `.env.example` to `.env` and fill in the [required variables](#environment-variables) (including `AZURE_AI_EMBEDDING_DEPLOYMENT_NAME`). The sample loads `.env` automatically on startup.

3. Sign in to Azure with the Azure CLI so `DefaultAzureCredential` can authenticate the terminal process (the **F5** path reuses the Azure sign-in from the Foundry Toolkit, so it doesn't need a separate `az login`):

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

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
