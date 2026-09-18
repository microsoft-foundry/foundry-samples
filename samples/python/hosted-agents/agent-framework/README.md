# Agent Framework Samples

This directory contains samples that demonstrate how to use the [Agent Framework](https://github.com/microsoft/agent-framework) to host agents with different capabilities and configurations. Each sample includes a README with instructions on how to set up, run, and interact with the agent.

> [!IMPORTANT]
> **Migrating from Protocol version 1.0.0 to 2.0.0:** The Foundry Hosted Agents service has been updated to use Protocol version 2.0.0. If your application is using Protocol version 1.0.0, upgrade to Protocol version 2.0.0 in your `azure.yaml` or `azure.yaml` and upgrade to the latest `agent-framework-foundry-hosting` package. `agent-framework-foundry-hosting==1.0.0a260625` is the last version that supports Protocol version 1.0.0.
>
> The `agent-framework-foundry-hosting` Python API surface is intended to remain stable, but protocol 1.0.0 and 2.0.0 are incompatible.

## Samples

### Responses API

| #   | Sample                                                                     | Description                                                                                                                                                                                                                                   |
| --- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | [Basic](responses/01-basic/)                                               | A minimal agent demonstrating basic request/response interaction and multi-turn conversations using `previous_response_id`.                                                                                                                   |
| 2   | [Tools](responses/02-tools/)                                               | An agent with local tools (e.g., weather lookup), demonstrating how to register and invoke custom tool functions alongside the LLM.                                                                                                           |
| 4   | [Foundry Toolbox](responses/04-foundry-toolbox/)                           | An agent using Azure Foundry Toolbox, demonstrating toolbox provisioning and querying available tools at runtime.                                                                                                                             |
| 5   | [Workflows](responses/05-workflows/)                                       | An agent with a multi-step orchestrated workflow, demonstrating chaining prompts through an orchestrated flow.                                                                                                                                |
| 6   | [Files](responses/06-files/)                                               | An agent capable of handling files uploaded by users.                                                                                                                                                                                         |
| 7   | [Skills](responses/07-skills/)                                             | An agent using native Agent Framework file-based skills, demonstrating skill discovery and a script-backed PDF travel guide skill.                                                                                                            |
| 7   | [Teams Activity](responses/07-teams-activity/)                              | An agent that can be published to Teams and Microsoft 365, with optional Work IQ tools for answering questions about Teams and calendar data and support for file attachments.                                                                |
| 8   | [Observability](responses/08-observability/)                               | An agent demonstrating observability features, including logging, metrics, and tracing.                                                                                                                                                       |
| 9   | [Declarative Customer Support](responses/09-declarative-customer-support/) | A multi-turn customer-support triage workflow defined entirely in YAML and hosted as an agent, demonstrating declarative workflow authoring with `InvokeAzureAgent` calls to specialist Foundry-hosted agents and conversation-aware routing. |
| 10  | [Downstream Azure services](responses/10-downstream-azure/)                | An agent that performs data-plane operations on Azure Blob Storage and Service Bus using its per-agent Microsoft Entra identity, demonstrating the per-agent identity + Azure RBAC pattern with no connection strings or shared keys.         |
| 11  | [Azure AI Search RAG](responses/11-azure-search-rag/)                      | An agent with Retrieval Augmented Generation (RAG) capabilities backed by Azure AI Search, grounding answers in documents indexed in a pre-provisioned search index.                                                                          |
| 12  | [Foundry Skills](responses/12-foundry-skills/)                             | An agent that uploads `SKILL.md` files to the Foundry Skills REST API and downloads them at startup, decoupling tone/policy guidelines from agent code.                                                                                       |
| 13  | [Foundry Memory](responses/13-foundry-memory/)                             | An agent with persistent semantic memory backed by an Azure AI Foundry Memory Store, using `FoundryMemoryProvider` to remember user facts across sessions.                                                                                    |
| 14  | [Browser Automation Agent](responses/14-browser-automation-agent/)         | A Foundry-hosted browser automation agent using Foundry Toolbox and the Browser Automation tool (Azure Playwright Service) for general browsing, web scraping, and form filling.                                                                |
| 15  | [Optimization Travel Approver](responses/15-optimization-travel-approver/) | A travel request approval agent for Agent Optimizer, demonstrating optimization of agent instructions, skills, and tool descriptions.                                                                                                        |
| 16  | [Content Safety Guardrail](responses/16-content-safety-guardrail/)         | An agent with a definition-level Responsible AI content safety guardrail that screens prompts and responses against a configured RAI policy.                                                                                                  |
| 17  | [Foundry IQ Toolbox](responses/17-foundry-iq-toolbox/)                     | An agent that grounds answers in a Foundry IQ knowledge base through a Foundry Toolbox MCP connection authenticated with the agent's managed identity.                                                                                        |
| 18  | [Egress Control](responses/18-egress-control/)                             | An agent for testing managed egress proxy policies by making outbound HTTP requests that validate Allow, Deny, Transform, and Rewrite rules.                                                                                                  |
| 19  | [Harness Research](responses/19-harness-research/)                         | A research harness with planning, todos, web search, compaction, file memory, and autonomous execute-mode looping over the Responses protocol.                                                                                                |
| 20  | [Harness Data Processing](responses/20-harness-data-processing/)           | A file-backed data-analysis harness that auto-runs read-only tools and exposes resumable approval requests for protected writes over the Responses protocol.                                                                                   |
| 21  | [Harness Scaling Capabilities](responses/21-harness-scaling-capabilities/) | A personal-finance harness that scales with file-based skills, a confined shell, CodeAct, background research agents, and token limits over the Responses protocol.                                                                            |
| 22  | [Foundry Toolbox MCP Skills](responses/22-foundry-toolbox-mcp-skills/)      | A self-contained agent that discovers MCP-based skills from a Foundry Toolbox (bundled `SKILL.md` sources + `toolbox.yaml`) and exposes them via a skills provider with progressive disclosure (advertise, load).                             |

### Invocations API

| #   | Sample                         | Description                                                                                                   |
| --- | ------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| 1   | [Basic](invocations/01-basic/) | A minimal agent demonstrating session state management via `agent_session_id` in URL params/response headers. |

### A2A protocol

| # | Sample | Description |
|---|--------|-------------|
| 1 | [Delegation](a2a/01-delegation/) | A two-agent walkthrough: a Responses-protocol **caller** delegates over A2A to a Responses-protocol **executor** that is exposed as an A2A endpoint via Foundry's [incoming A2A](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint) feature. Includes a Bash/PowerShell script that PATCHes the executor to publish its agent card and enable A2A. |

## Running the Agent Host Locally

The steps below use the [basic Responses sample](responses/01-basic/) as an example and apply to most single-agent Responses samples. Check each sample's README for additional dependencies and configuration.

The other protocols require their own setup and invocation flow:

- For the Invocations protocol, follow the [basic Invocations sample](invocations/01-basic/).
- For A2A, follow the [Delegation walkthrough](a2a/01-delegation/), which deploys and connects two agents.

| Approach | Best for | Setup effort |
| --- | --- | --- |
| **[Azure Developer CLI (`azd`)](#using-azd)** | Command-line workflows, scripting, and CI/CD. Auto-provisions Azure resources from the manifest. | Lowest — no clone required |
| **Foundry Toolkit VS Code Extension** | Integrated editor experience with an **Agent Inspector** for chatting with a running agent and a guided **Deploy Hosted Agent** flow. | Lowest — install the extension |
| **[`python`](#using-python)** | Manual control: clone the repo, manage your own venv, set env vars by hand. | Highest |

### Using `azd`

#### Prerequisites

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.25 or later) and the unified Foundry CLI extension: `azd ext install microsoft.foundry`
   - Authenticated: `azd auth login`

2. **Azure Subscription**

#### Create a new project

**No cloning required**. Create a new folder, point azd at the manifest on GitHub.

```bash
mkdir hosted-agent-framework-agent && cd hosted-agent-framework-agent

# Initialize from the manifest
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/01-basic/azure.yaml
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

> Note: The environment variables set above are only for the current session. You will need to set them again if you open a new terminal session. if you want to set the environment variables permanently in the azd environment, you can use `azd env set <name> <value>`.

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

Or you can in another terminal, without navigating to the project directory, run the following command to invoke the agent:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hello!"}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Hello!"}').Content
```

<details>
<summary><h3>Using the Foundry Toolkit VS Code Extension</h3></summary>

The [Foundry Toolkit VS Code extension](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=vscode) has a built-in sample gallery. You can open this sample directly from the extension without cloning the repository, it scaffolds the project into a new workspace, generates `agent.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically, and configures a one-click **F5** debug experience.

The extension also adds an **Agent Inspector** UI for chatting with a hosted agent that is already running locally, plus a guided **Deploy Hosted Agent** command (see [Deploying the Agent to Foundry](#deploying-the-agent-to-foundry) below).

#### Prerequisites

1. **Foundry Toolkit VS Code Extension** — [install from the VS Code marketplace](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=vscode) and sign in to Azure.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. Python 3.10 or later. The uv setup option requires Python 3.13 or later.
4. [pipx](https://pipx.pypa.io/stable/installation/) if you use the uv setup option.

#### Set up the Python virtual environment

Use the setup option that matches the dependency files included with the sample.

**Using `requirements.txt`**

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** (or **Python: Select Interpreter** to use an existing one).
- Install dependencies: `pip install uv && uv pip install -r requirements.txt`

**Using uv**

Install uv outside the project environment, then let uv create and synchronize the locked environment:

```bash
pipx install uv==0.11.7
uv sync --frozen --python 3.13
```

Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

#### Run and debug with F5 (recommended)

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically.

#### Or run manually, then open the Inspector

Once the agent is running on `http://localhost:8088/` (via [`azd ai agent run`](#using-azd) or one of the run options under [Using `python`](#using-python)):

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector**.
2. The Inspector auto-connects to the running agent.
3. Send messages to chat and watch the streamed responses.

</details>

### Using `python`

#### Prerequisites

1. An existing Foundry project
2. A deployed model in your Foundry project
3. Azure CLI installed and authenticated
4. Python 3.10 or later. The uv setup option requires Python 3.13 or later.
5. [pipx](https://pipx.pypa.io/stable/installation/) if you use the uv setup option

#### Running the Agent Host with Python

Clone the repository containing the sample code:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples/samples/python/hosted-agents/agent-framework/responses/01-basic/src/agent-framework-agent-basic-responses
```

#### Environment setup

Use the setup option that matches the dependency files included with the sample.

**Using `requirements.txt`**

1. Navigate to the sample's service directory (the `project` path in its `azure.yaml`). Create a virtual environment:

   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\Activate

   # macOS/Linux
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

**Using uv**

1. Install uv outside the project environment:

   ```bash
   pipx install uv==0.11.7
   ```

2. Navigate to the sample's service directory (the `project` path in its `azure.yaml`), then create and synchronize the locked environment:

   ```bash
   uv sync --frozen --python 3.13
   ```

After setting up the environment:

1. Create a `.env` file with your Foundry configuration following the `.env.example` file in the sample.

2. Make sure you are logged in with the Azure CLI:

   ```bash
   az login
   ```

#### Running the Agent Host

With the `requirements.txt` environment activated, run:

```bash
python main.py
```

Or with uv, run:

```bash
uv run --no-sync python main.py
```

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

On another terminal, run the following command to invoke the agent:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hello!"}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Hello!"}').Content
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

After running `azd ai agent init -m <azure.yaml>` and following the prompts to configure your agent, you will have a project ready for deployment.

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

For the full deployment guide, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

Once deployed, learn more about how to manage deployed agents in the [official management guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent).

### Deploying with the Foundry Toolkit VS Code Extension

You can also deploy directly from the editor (see [Using the Foundry Toolkit VS Code Extension](#using-the-foundry-toolkit-vscode-extension) above for the local-run setup).

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a tab-based **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate what it can.
2. If prompted, complete **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one) to deploy to.
3. On the **Basics** tab, configure the core deployment settings:
   - **Deployment Method**: **Code** (upload as a ZIP) or **Container** (Docker image via ACR).
   - For **Code**, pick a packaging option: **Remote** or **Local**.
   - For **Container**, pick a registry option: default ACR, your own ACR, or a prebuilt ACR image.
   - **Hosted Agent Name**: confirm the name to register with the hosting service.
4. On the **Review + Deploy** tab, finalize the runtime and resources:
   - Confirm the auto-detected runtime details (language, entry point, or Dockerfile).
   - Pick a **CPU and Memory** size.
   - Click **Deploy**. Fields are validated inline, and the extension handles the build/upload, agent version creation, and RBAC role assignment.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

#### Troubleshooting

**Azure OpenAI permission denied (401):** the identity running the agent does not have the required RBAC roles on the Foundry project. Assign **Cognitive Services OpenAI User** and **Azure AI User** to the agent's identity (it may take a few minutes for role assignments to propagate). See the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent) for details.
