# Foundry Toolbox - MCP Skills

An agent that uses [**Foundry Toolbox skills**](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?pivots=dotnet) to answer user prompts. Skills are discovered from a Foundry Toolbox MCP endpoint and made available to the agent at runtime.

## How It Works

The agent uses an `AgentSkillsProvider` (built via `AgentSkillsProviderBuilder.UseMcpSkills`) to interact with skills through the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern:

1. **Advertise** - skill names and descriptions are injected into the system prompt so the agent knows what is available.
2. **Load** - when the agent decides a skill is relevant, it retrieves the full skill body via the provider.
3. **Read resources** - if a skill includes supplementary content (reference documents, assets), the agent reads them on demand via the provider.

The full skill body and resources are only fetched from the toolbox when the agent actually needs them, reducing token usage.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the Responses API hosting layer (`AddFoundryResponses` / `MapFoundryResponses`).

See [Program.cs](src/foundry-toolbox-mcp-skills/Program.cs) for the full implementation.

## Prerequisites

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **A Foundry Toolbox with MCP-based skills** — a [Foundry Toolbox](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox) with at least one [skill](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?pivots=dotnet) attached. This sample only consumes skills from an existing toolbox — it does not create or provision them.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name — must match a deployment in your Foundry project. |
| `TOOLBOX_NAME` | Yes | Name of the Foundry Toolbox to connect to. The toolbox must already be provisioned with MCP-based skills. |

Values for these are provided by the `azd ai agent init` command (Option 1) or the Foundry Toolkit scaffold (Option 2).

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
mkdir foundry-toolbox-mcp-skills && cd foundry-toolbox-mcp-skills
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/foundry-toolbox-mcp-skills/azure.yaml
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

In a separate terminal, invoke the running agent:

```bash
azd ai agent invoke --local "What skills do you have available?"
azd ai agent invoke --local "Use the available skill and greet me."
```

Read-only skill discovery and loading are auto-approved. Skill scripts, if a toolbox skill exposes
them, still require explicit approval.

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "What skills do you have available?"
azd ai agent invoke "Use the available skill and greet me."
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

2. Configure the agent: copy `.env.example` to `.env` and fill in the [required variables](#environment-variables) (including `TOOLBOX_NAME`). The sample loads `.env` automatically on startup.

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
