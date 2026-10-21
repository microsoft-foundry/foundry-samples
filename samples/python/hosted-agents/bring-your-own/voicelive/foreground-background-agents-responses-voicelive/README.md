<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

## What this sample demonstrates

A hosted agent sample that demonstrates a **foreground/background agent** pattern using the **Bring Your Own** approach with the **Responses protocol**. The foreground router agent stays responsive for voice scenarios by quickly acknowledging the user, deciding whether work should be handled immediately or delegated, and managing task status. The background worker agent performs longer-running tool work asynchronously and stores the result for delivery when ready.

## How It Works
A two-agent architecture where the **Router** handles all user interaction (fast, always responsive) and the **Worker** executes tool-calling loops in the background (async, cancelable).

### Router Agent

- Receives every user message and makes a single LLM call with `tool_choice: required`.
- Must call exactly one of its meta-tools per turn — no free-text output path.
- Meta-tools:
  - `respond_directly` — greetings, chat, clarifications, delivering results
  - `start_task` — delegate actionable field-ops work to the Worker
  - `check_task_status` — report progress of a running task
  - `cancel_task` — cancel a running task
  - `get_task_result` — retrieve a completed task's result
- Guards against duplicate tasks: if a task is already active, `start_task` returns the existing task instead of creating a new one.
- Injected context each turn: running tasks, recently completed results, previously delivered results.

### Worker Agent

- Runs asynchronously via `asyncio.create_task` (fire-and-forget).
- Executes a multi-round tool-calling loop (up to 5 rounds) using domain tools:
  - `search_site_specs` — site specification lookup
  - `search_work_iq` — Teams/Outlook/People search
  - `get_repair_procedure` — step-by-step maintenance procedures
  - `analyze_document` — document understanding and extraction
- Writes results into the shared `Task` object (never talks to the user directly).
- Supports cancellation between rounds via `cancel_event`.
- Resilient to client disconnection — keeps running in background.

### Streaming & Wait Behavior

- Handler streams: acknowledgment → wait for active tasks → deliver results.
- While waiting, periodic LLM-generated status updates are streamed (every ~8s, up to 5 times) in the user's language.
- If cancel signal fires mid-wait, the SSE closes but workers continue — results are delivered next turn.


## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) and the AI agent extension: `azd ext install azure.ai.agents`
   - Authenticated: `azd auth login`

2. **Azure CLI**
   - Installed and authenticated: `az login`

3. **Python 3.12 or later**
   - Verify your version: `python --version`

4. **uv 0.11.7 or later**
   - [Install uv](https://docs.astral.sh/uv/getting-started/installation/) and verify it is available on `PATH`: `uv --version`

> [!NOTE]
> You do **not** need an existing [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-foundry?view=foundry) project or model deployment to get started — `azd provision` creates them for you. If you already have a project, see the [note below](#using-azd) on how to target it.

### Environment Variables

See [`.env.example`](src/foreground-background-agents-voicelive/.env.example) for the full list of environment variables this sample uses.

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name — must match your Foundry project deployment. Declared in `azure.yaml`. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

**Local development (without `azd`):**

```bash
# Copy and fill in values, then source
cp .env.example .env
# Edit .env with your values
source .env
```

> [!NOTE]
> When using `azd ai agent run`, environment variables are handled automatically — no manual setup needed.

### Installing Dependencies

> [!NOTE]
> `azd ai agent run` uses the installed `uv` command to sync dependencies automatically.
> After installing uv, skip to [Running the Sample](#running-the-sample).

```bash
python -m pip install uv
cd src/foreground-background-agents-voicelive
uv sync --frozen
```

### Running the Sample

Run and test hosted agents locally with the Azure Developer CLI (`azd`) or the Foundry VS Code extension.

<details>
<summary><h4>Using the Foundry VS Code Extension</h4></summary>

The [Foundry VS Code extension](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=vscode) has a built-in sample gallery. You can open this sample directly from the extension without cloning the repository — it scaffolds the project into a new workspace, generates `agent.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically, and configures a one-click **F5** debug experience.

Follow the [VS Code quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=vscode) for a full step-by-step walkthrough.

</details>

#### Using [`azd`](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd)

No cloning required. Create a new folder, point `azd` at the manifest on GitHub, and it sets up the sample and adopts its `azure.yaml` as the project manifest and configures your environment automatically:

```bash
# Create a new folder for the agent and navigate into it
mkdir foreground-background-agent && cd foreground-background-agent

# Initialize from the manifest — azd reads it, downloads the sample,
# and adopts its azure.yaml as the project manifest and configures your environment
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voicelive/foreground-background-agents-responses-voicelive/azure.yaml

# Provision Azure resources (Foundry project, model deployment, App Insights)
azd provision

# Run the agent locally (handles env vars, Docker build, and startup)
azd ai agent run
```

> [!NOTE]
> If you've already cloned this repository, pass a local path to the manifest instead:
> `azd ai agent init -t <path-to-repo>/samples/python/hosted-agents/bring-your-own/voicelive/foreground-background-agents-responses-voicelive/azure.yaml`

> [!NOTE]
> If you already have a Foundry project and model deployment, add `-p <project-id> -d <deployment-name>` to `azd ai agent init` to target existing resources. You can also skip provisioning entirely and configure env vars manually — see [Manual setup](#manual-setup).

The agent starts on `http://localhost:8088/`. To invoke it:

```bash
azd ai agent invoke --local "Check the fiber repair procedure"
```

#### Manual setup

If running without `azd`, set environment variables manually (see [Environment Variables](#environment-variables)), then:

```bash
uv run --no-sync python main.py
```

### Deploying the Agent to Microsoft Foundry

Once you've tested locally, deploy to Microsoft Foundry:

```bash
# Provision Azure resources (skip if already done during local setup)
azd provision

# Build, push, and deploy the agent to Foundry
azd deploy
```

After deploying, invoke the agent running in Foundry:

```bash
azd ai agent invoke "Check the fiber repair procedure"
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).
