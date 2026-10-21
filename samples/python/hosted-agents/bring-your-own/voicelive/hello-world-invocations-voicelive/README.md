<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A minimal "hello world" hosted agent using the **Bring Your Own** approach with the **Invocations protocol** in Python, designed for **real-time voice interactions** with the [Azure VoiceLive SDK](https://pypi.org/project/azure-ai-voicelive/). It shows how to use the [`azure-ai-agentserver-invocations`](https://pypi.org/project/azure-ai-agentserver-invocations/) SDK to host a custom agent that calls a Foundry model via the Responses API and streams `output_audio_transcription` events compatible with VoiceLive.

This is the simplest possible BYO integration — the protocol SDK handles the HTTP endpoints, session resolution, client header forwarding, and OpenTelemetry tracing. You supply the model call using the [Foundry SDK (`azure-ai-projects`)](https://pypi.org/project/azure-ai-projects/). 

Once the agent is deployed, you can interact with the agent using voice through the included [`voicelive_client.py`](voicelive_client.py) client.

## How It Works

### Model Integration

The agent uses the Foundry SDK to create a Responses client from the project endpoint and model deployment name. When a request arrives, the handler looks up the session history by `session_id`, appends the new user message, calls the model via the Responses API with streaming, and returns a `StreamingResponse` of SSE events — `output_audio_transcription.delta` events during generation, an `output_audio_transcription.done` event with the full text, then a final `done` event.

See [main.py](src/hello-world-python-invocations-voicelive/main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer Invocations SDK](https://pypi.org/project/azure-ai-agentserver-invocations/), which provisions a REST API endpoint compatible with the Azure AI Invocations protocol.

### Agent Deployment

The hosted agent can be developed and deployed to Microsoft Foundry using the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd).

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.34.2 or later) and the unified Foundry CLI extension: `azd ext install microsoft.foundry`
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

See [`.env.example`](src/hello-world-python-invocations-voicelive/.env.example) or `.env` for the full list of environment variables this sample uses.

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name — must match your Foundry project deployment. Declared in `azure.yaml`. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

**Local development (without `azd`):**

```bash
cp .env.example .env  # skip if .env already exists
# Edit .env and fill in your values, then:
export $(grep -v '^#' .env | xargs)
```

> [!NOTE]
> When using `azd ai agent run`, environment variables are handled automatically — no manual setup needed.

### Installing Dependencies

> [!NOTE]
> `azd ai agent run` uses the installed `uv` command to sync dependencies automatically.
> After installing uv, skip to [Running the Sample](#running-the-sample).

```bash
python -m pip install uv
cd src/hello-world-python-invocations-voicelive
uv sync --frozen
```

### Running the Sample

Run and test hosted agents locally with the Azure Developer CLI (`azd`) or the Foundry Toolkit VS Code extension.

<details>
<summary><h4>Using the Foundry Toolkit VS Code Extension</h4></summary>

The [Foundry Toolkit VS Code extension](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=vscode) has a built-in sample gallery. You can open this sample directly from the extension without cloning the repository, it scaffolds the project into a new workspace, generates `agent.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically, and configures a one-click **F5** debug experience.

Chat with a running agent using the **Agent Inspector**:

1. Start the agent locally first using **Using `azd`** or **Manual setup** above. The agent listens on `http://localhost:8088/`.
2. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector**.
3. The Inspector auto-connects to the running agent. Send messages to chat with the agent and watch the streamed responses.

</details>

#### Using [`azd`](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd)

No cloning required. Create a new folder, point `azd` at the manifest on GitHub, and it sets up the sample and adopts its `azure.yaml` as the project manifest and configures your environment automatically:

```bash
# Create a new folder for the agent and navigate into it
mkdir hello-world-agent && cd hello-world-agent

# Initialize from the manifest — azd reads it, downloads the sample,
# and adopts its azure.yaml as the project manifest and configures your environment
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voicelive/hello-world-invocations-voicelive/azure.yaml

# Provision Azure resources (Foundry project, model deployment, App Insights)
azd provision

# Run the agent locally (handles env vars, dependency install, and startup)
azd ai agent run
```

> [!NOTE]
> If you've already cloned this repository, pass a local path to the manifest instead:
> `azd ai agent init -t <path-to-repo>/samples/python/hosted-agents/bring-your-own/voicelive/hello-world-invocations-voicelive/azure.yaml`

> [!NOTE]
> If you already have a Foundry project and model deployment, add `-p <project-id> -d <deployment-name>` to `azd ai agent init` to target existing resources. You can also skip provisioning entirely and configure env vars manually — see [Manual setup](#manual-setup).

The agent starts on `http://localhost:8088/`. To invoke it:

```bash
azd ai agent invoke --local "What is Microsoft Foundry?"
```

Or use curl directly. The `-N` flag disables output buffering so you see SSE tokens as they arrive:

> [!NOTE]
> `agent_session_id` is optional. If omitted, the server auto-generates one and returns it in the `done` event (`session_id` field). To continue a conversation across turns, pass the same `agent_session_id` in each request.

```bash
# Turn 1 — start a new conversation
curl -sS -N -X POST "http://localhost:8088/invocations?agent_session_id=chat-001" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is Microsoft Foundry?"}'

# Turn 2 — continue the same conversation
curl -sS -N -X POST "http://localhost:8088/invocations?agent_session_id=chat-001" \
  -H "Content-Type: application/json" \
  -d '{"message": "What hosted agent options does it offer?"}'
```

Each response is a stream of SSE events: `output_audio_transcription.delta` events with incremental text, an `output_audio_transcription.done` event with the complete reply, followed by a `done` event.

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
azd ai agent invoke "What is Microsoft Foundry?"
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

#### Deploying with the Foundry Toolkit VS Code Extension

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

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.


## Using the Agent with Voice Live

Once the agent is deployed to Microsoft Foundry, you can interact with it using **real-time voice** through the [Azure VoiceLive SDK](https://pypi.org/project/azure-ai-voicelive/). The included [`voicelive_client.py`](voicelive_client.py) connects to a VoiceLive endpoint, streams microphone audio to the agent, and plays back the agent's spoken response.

### Prerequisites

- The agent must already be deployed to Microsoft Foundry (see [Deploying the Agent](#deploying-the-agent-to-microsoft-foundry)).
- An **Azure VoiceLive endpoint** — provision one through the Azure portal or your Foundry project.
- A working **microphone and speakers** on your machine.
- **Python 3.12+** with the following packages:

```bash
pip install azure-ai-voicelive[aiohttp]==1.3.0b1 azure-identity pyaudio
```

> [!NOTE]
> On Linux, install PortAudio first: `sudo apt-get install -y portaudio19-dev libasound2-dev`

### Running the Voice Live Client

```bash
python voicelive_client.py \
  --endpoint "https://<your-foundry-resource>.services.ai.azure.com" \
  --agent-name "<your-agent-name>" \
  --project-name "<your-foundry-project-name>"
```

The client authenticates using `DefaultAzureCredential` — make sure you are logged in (`az login`).

Once connected, speak into your microphone. The agent will respond with synthesized speech. Press **Ctrl+C** to end the session.
