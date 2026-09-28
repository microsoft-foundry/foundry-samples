# Agent Framework Samples

This directory contains samples that demonstrate how to use the [Agent Framework](https://github.com/microsoft/agent-framework) to host agents with different capabilities and configurations. Each sample includes a README with instructions on how to interact with the agent.

> [!IMPORTANT]
> **Responses container protocol v2.0.** These samples target the Foundry Responses container
> protocol **v2.0**, declared in each `azure.yaml`. The updated projects use the published
> `Microsoft.Agents.AI.*` **1.22.0** package line, with Foundry hosting pinned to
> `1.22.0-preview.260918.1` and MCP integration pinned to `1.22.0-alpha.260918.1`.
> Use each project file as the authoritative package reference when copying a sample.

## Samples

### Responses API

| # | Sample | Description |
|---|--------|-------------|
| 1 | [hello-world](hello-world/) | A minimal agent demonstrating basic request/response interaction and multi-turn conversations. |
| 2 | [simple-agent](simple-agent/) | A general-purpose AI assistant — the simplest hosted agent using `AsAIAgent(model, instructions)`. |
| 3 | [local-tools](local-tools/) | A hotel search assistant with local C# function tools (`AIFunctionFactory.Create`). |
| 4 | [mcp-tools](mcp-tools/) | An agent demonstrating client-side and server-side MCP tool integration. |
| 5 | [text-search-rag](text-search-rag/) | A support agent with RAG capabilities using `TextSearchProvider`. |
| 6 | [workflows](workflows/) | A multi-agent translation pipeline using `WorkflowBuilder`. |
| 7 | [foundry-toolbox-server-side](foundry-toolbox-server-side/) | An agent that loads a Foundry Toolbox via `AddFoundryToolboxes()` and exposes its tools as server-side tools — Foundry executes them on the agent's behalf. |
| 8 | [toolbox-auth-paths](toolbox-auth-paths/) | A multi-tool Foundry Toolbox demonstrating the authentication paths an MCP tool can use (key-based `CustomKeys`, public no-auth, and optional Entra agent identity) — all resolved server-side. |
| 9 | [azure-search-rag](azure-search-rag/) | A support agent with RAG grounded in an Azure AI Search keyword index via `TextSearchProvider` over `Azure.Search.Documents`. |
| 10 | [foundry-memory-rag](foundry-memory-rag/) | A personal-coach agent with persistent per-user memory that survives across requests and sessions using `FoundryMemoryProvider`. |
| 11 | [file-tools](file-tools/) | An agent that answers questions over both image-baked bundled files and per-session uploaded files through scoped, security-hardened tools. |
| 12 | [agent-skills](agent-skills/) | An agent that loads its behavioral guidelines from Foundry Skills (`SKILL.md`) at startup, so updates ship without code changes. |
| 13 | [observability](observability/) | An instrumented agent demonstrating OpenTelemetry tracing, metrics, and logging for a hosted agent. |
| 14 | [teams-activity](teams-activity/) | A hosted agent that can be deployed to Foundry and published to Teams, handling messages with file attachments and Teams/calendar questions. |
| 15 | [a2a/01-delegation](a2a/01-delegation/) | Two hosted agents — a math-expert executor exposed over A2A and a concierge caller that delegates to it through a Foundry Toolbox A2A connection. |
| 16 | [foundry-toolbox-mcp-skills](foundry-toolbox-mcp-skills/) | An agent that discovers MCP-based skills from a Foundry Toolbox and exposes them to the agent via `AgentSkillsProvider` with progressive disclosure. |
| 17 | [steering](steering/) | A long-running agent that queues a second input on the same active conversation instead of rejecting it as locked. |
| 18 | [resilient-workflow](resilient-workflow/) | A model-backed workflow whose Agent Executor calls an intentional crash tool and resumes the pending tool call in a replacement process. |
| 19 | [steerable-workflow](steerable-workflow/) | A deterministic workflow that queues steering input, cancels an active superstep, and continues from the last committed checkpoint. |
| 20 | [egress-control](egress-control/) | A network-isolated agent that demonstrates allowlisted outbound access through Foundry egress controls. |
| 21 | [browser-automation](browser-automation/) | A container-only browser automation agent that uses the Playwright CLI and a Foundry Toolbox. |
| 22 | [harness-research](harness-research/) | A research harness agent with planning, web search, todo tracking, and session state. |
| 23 | [harness-data-processing](harness-data-processing/) | A data-processing harness agent with scoped file access and approval-gated writes. |
| 24 | [harness-scaling-capabilities](harness-scaling-capabilities/) | A harness agent that combines skills, background agents, confined shell access, and optional Hyperlight CodeAct. |

### Invocations API

| # | Sample | Description |
|---|--------|-------------|
| 1 | [invocations-echo-agent](invocations-echo-agent/) | A minimal echo agent demonstrating session state management via `agent_session_id` (no LLM needed). |

## Running the Agent Host Locally

You can run any sample in this folder using one of three approaches. Pick the one that matches your workflow.

| Approach | Best for | Setup effort |
| --- | --- | --- |
| **[Azure Developer CLI (`azd`)](#using-azd)** | Command-line workflows, scripting, and CI/CD. Auto-provisions Azure resources from the manifest. | Lowest — no clone required |
| **Foundry Toolkit VS Code Extension** | Integrated editor experience with an **Agent Inspector** for chatting with a running agent and a guided **Deploy Hosted Agent** flow. | Lowest — install the extension |
| **[`dotnet run`](#using-dotnet-run)** | Manual control: clone the repo, manage your own env vars, debug with the .NET CLI. | Highest |

### Using `azd`

#### Prerequisites

1. **Azure Developer CLI (`azd`)**

    - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.27.1 or later) and the unified Foundry CLI extension: `azd ext install microsoft.foundry`
    - Authenticated: `azd auth login`

2. **Azure Subscription**

#### Create a new project

**No cloning required**. Create a new folder, point azd at the manifest on GitHub.

```bash
mkdir hosted-agent-framework-agent && cd hosted-agent-framework-agent

# Initialize from the manifest
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/hello-world/azure.yaml
```

Follow the instructions from `azd ai agent init` to complete the agent initialization. If you don't have an existing Foundry project and a model deployment, `azd ai agent init` will guide you through creating them.

#### Provision Azure Resources

> This step is only needed if you don't have an existing Foundry project and model deployment.

Run the following command to provision the necessary Azure resources:

```bash
azd provision
```

This will create the following Azure resources:

- A new resource group named `rg-[project_name]-dev`. In this guide, `[project_name]` will be `hosted-agent-framework-agent`.
- Within the resource group, among other resources, the most important ones are:
  - A new Foundry instance
  - A new Foundry project, within which a new model deployment will be created
  - An Application Insights instance
  - A container registry, which will be used to store the container images for the hosted agent

#### Set Environment Variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
# And any other environment variables required by the sample
```

Or in PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
# And any other environment variables required by the sample
```

> Note: The environment variables set above are only for the current session. You will need to set them again if you open a new terminal session.

#### Running the Agent Host

```bash
azd ai agent run
```

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

Open another terminal, **navigate to the project directory**, and run the following command to invoke the agent:

```bash
azd ai agent invoke --local "Hello!"
```

<details>
<summary><h3>Using the Foundry Toolkit VS Code Extension</h3></summary>

The [Foundry Toolkit VS Code extension](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio) has a built-in sample gallery. You can open a sample directly from the extension without cloning the repository — it scaffolds the project into a new workspace, generates `agent.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically, and configures a one-click **F5** debug experience. It also adds an **Agent Inspector** UI for chatting with a running agent and a guided **Deploy Hosted Agent** command (see [Deploying the Agent to Foundry](#deploying-the-agent-to-foundry) below).

#### Prerequisites

1. **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed and signed in to Azure.
2. **[C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit)** extension. Run Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain.

#### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

#### Or run manually, then open the Inspector

1. Start the agent with [`azd ai agent run`](#using-azd) or [`dotnet run`](#using-dotnet-run) — it listens on `http://localhost:8088/`.
2. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector**.
3. The Inspector auto-connects to the running agent. Send messages to chat and watch the streamed responses.

</details>

### Using `dotnet run`

#### Prerequisites

1. An existing Foundry project
2. A deployed model in your Foundry project
3. [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and authenticated (`az login`)
4. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) or later

#### Running the Agent Host with `dotnet`

Clone the repository containing the sample code:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples/samples/csharp/hosted-agents/agent-framework
```

#### Environment setup

1. Navigate to the sample directory you want to explore:

   ```bash
   cd hello-world
   ```

2. Restore dependencies:

   ```bash
   dotnet restore
   ```

3. Set environment variables:

   ```bash
   export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
   export AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
   ```

   Or in PowerShell:

   ```powershell
   $env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
   $env:AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
   ```

4. Make sure you are logged in with the Azure CLI:

   ```bash
   az login
   ```

#### Running the Agent Host

```bash
dotnet run
```

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

On another terminal, run the following command to invoke the agent:

```bash
azd ai agent invoke --local "Hello!"
```

## Deploying the Agent to Foundry

Once you've tested locally, deploy to Microsoft Foundry. You can use either `azd` or the Foundry Toolkit VS Code extension — both produce the same result.

| Approach | Best for |
| --- | --- |
| **[`azd deploy`](#using-azd-1)** | Command-line workflows, scripting, and CI/CD. |
| **Foundry Toolkit VS Code Extension** | Guided UI in the editor with prompts for agent name, container registry, and resource size. |

### Using `azd`

#### With an Existing Foundry Project

If you already have a Foundry project and the necessary Azure resources provisioned, you can skip the setup steps and proceed directly to deploying the agent.

After running `azd ai agent init --deploy-mode container -m <azure.yaml>` and following the prompts to configure your agent, you will have a project ready for deployment.

#### Setting Up a New Foundry Project

Follow the steps in [Using `azd`](#using-azd) to set up the project and provision the necessary Azure resources for your Foundry deployment.

#### Deploying the Agent

Once the project is setup and resources are provisioned, you can deploy the agent to Foundry by running:

```bash
azd deploy
```

> The Foundry hosting infrastructure will inject the following environment variables into your agent at runtime:
>
> - `FOUNDRY_PROJECT_ENDPOINT`: The endpoint URL for the Foundry project where the agent is deployed.
> - `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of the model deployment in your Foundry project. This is configured during the agent initialization process with `azd ai agent init`.
> - `APPLICATIONINSIGHTS_CONNECTION_STRING`: The connection string for Application Insights to enable telemetry for your agent.

This will package your agent and deploy it to the Foundry environment, making it accessible through the Foundry project endpoint. Once it's deployed, you can also access the agent through the Foundry UI.

#### Invoking the deployed agent

```bash
azd ai agent invoke "Hello!"
```

For Responses work that must continue after the CLI disconnects, start a stored background response and follow it separately:

```bash
azd ai agent invoke --long-running --no-wait "Run the long task"
azd ai agent invocations follow
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Deploying with the Foundry Toolkit VS Code Extension

You can also deploy directly from the editor (see [Using the Foundry Toolkit VS Code Extension](#using-the-foundry-toolkit-vscode-extension) above for the local-run setup).

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a tab-based **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate what it can.
2. If prompted, complete **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one) to deploy to.
3. On the **Basics** tab, configure the core deployment settings:
   - **Deployment Method**: **Code** (upload as a ZIP) or **Container** (Docker image via ACR). The browser automation sample is container-only because its image installs Playwright CLI.
   - For **Code**, pick a packaging option: **Remote** or **Local**.
   - For **Container**, pick a registry option: default ACR, your own ACR, or a prebuilt ACR image.
   - **Hosted Agent Name**: confirm the name to register with the hosting service.
4. On the **Review + Deploy** tab, finalize the runtime and resources:
   - Confirm the auto-detected runtime details (language, entry point, or Dockerfile).
   - Pick a **CPU and Memory** size.
   - Click **Deploy**. Fields are validated inline, and the extension handles the build/upload, agent version creation, and RBAC role assignment.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

#### Troubleshooting

**Azure OpenAI permission denied (401):** the identity running the agent does not have the required RBAC roles on the Foundry project. Assign **Cognitive Services OpenAI User** and **Azure AI User** to the agent's identity (it may take a few minutes for role assignments to propagate). See the [Foundry deployment guide](https://aka.ms/azdaiagent/docs) for details.
