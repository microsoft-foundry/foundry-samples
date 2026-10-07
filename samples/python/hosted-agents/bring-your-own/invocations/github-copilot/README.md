**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# GitHub Copilot SDK — Invocations Protocol (Streaming)

A minimal getting-started agent using the [GitHub Copilot SDK](https://pypi.org/project/github-copilot-sdk/) (`CopilotClient`) with the [azure-ai-agentserver-invocations](https://pypi.org/project/azure-ai-agentserver-invocations/) protocol. Streams raw Copilot SDK session events as SSE with multi-turn support.

## How It Works

1. Receives `{"input": "..."}` via `POST /invocations`
2. On first request, tries to resume a persisted Copilot session (by `FOUNDRY_AGENT_SESSION_ID`); if none exists, creates a new one
3. Each `SessionEvent` from the Copilot SDK is streamed back as an SSE `data:` event using `event.to_dict()`
4. A final `event: done` signal marks the end of the response
5. The session is cached in memory and reused across requests for multi-turn conversation
6. Skills in the `skills/` directory are auto-loaded — e.g. the included `joke` skill makes Copilot respond in pirate tone

## Environment Variables

This agent supports two LLM backends. Configure one of the following:

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | For Copilot model | GitHub fine-grained PAT with **Copilot Requests → Read-only** permission |
| `FOUNDRY_PROJECT_ENDPOINT` | For Foundry model | Azure AI Foundry project endpoint URL. Auto-injected when hosted — only needed locally |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | For Foundry model | Model deployment name (e.g. `gpt-5.4-mini`) |
| `FOUNDRY_AGENT_SESSION_ID` | No | Session ID for persistence/resume. If unset, a UUID is generated |

**How the agent selects its LLM backend:**
- If `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` are set → uses your **Foundry model** via Managed Identity (no `GITHUB_TOKEN` needed)
- If only `GITHUB_TOKEN` is set → uses the **GitHub Copilot model** (quickest way to get started)
- If both are set → the **Foundry model takes precedence**

> When deployed with `azd`, `azure.yaml` declares `AZURE_AI_MODEL_DEPLOYMENT_NAME` by default (the BYOK Foundry model). To use the GitHub Copilot model instead, comment out `AZURE_AI_MODEL_DEPLOYMENT_NAME` and uncomment `GITHUB_TOKEN` in `azure.yaml`.

## Prerequisites

- **Python 3.12+**
- An Azure AI Foundry project with a deployed model — for the default BYOK path (`FOUNDRY_PROJECT_ENDPOINT` is auto-injected when hosted; set it locally)
- *(GitHub Copilot model only)* A GitHub fine-grained PAT (`github_pat_` prefix)

  Create one at [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new) with **Account permissions → Copilot Requests → Read-only**.

  > **Note:** Classic tokens (`ghp_`) are not supported. Use a fine-grained PAT (`github_pat_`), OAuth token (`gho_`), or GitHub App user token (`ghu_`).

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

### Configure the model backend

By default this sample uses a **BYOK Foundry model**. Copy the env template and set your project endpoint:

```bash
cp .env.example .env  # skip if .env already exists
# Edit .env: set FOUNDRY_PROJECT_ENDPOINT to your project
# (AZURE_AI_MODEL_DEPLOYMENT_NAME defaults to gpt-5.4-mini)
```

The sample loads `.env` automatically when running locally. Sign in so it can authenticate to the Foundry model via Managed Identity:

```bash
az login
```

> **Prefer the GitHub Copilot model?** In `.env` comment out the Foundry vars and uncomment `GITHUB_TOKEN` (a fine-grained PAT with "Copilot Requests → Read-only"). To deploy that way, flip the same vars in `azure.yaml`.

### Run the agent locally

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Invoke the local agent

**Bash:**
```bash
azd ai agent invoke --local '{"input": "What can you help me with?"}'
```

**PowerShell:**
```powershell
azd ai agent invoke --local '{\"input\": \"What can you help me with?\"}'
```

Or invoke directly with curl:

```bash
# First message
curl -N -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": "What is Python?"}'

# Follow-up (multi-turn — same session remembers context)
curl -N -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": "Give me a code example"}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
# Provision Azure resources (skip if already done during local setup)
azd provision

# Build, push, and deploy the agent to Foundry
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

**Bash:**
```bash
azd ai agent invoke '{"input": "What can you help me with?"}'
```

**PowerShell:**
```powershell
azd ai agent invoke '{\"input\": \"What can you help me with?\"}'
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/github-copilot-invocations

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/github-copilot-invocations/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/github-copilot-invocations`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

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

## SSE Event Format

Each Copilot SDK event is streamed via `event.to_dict()`:

```
data: {"type": "assistant.message_delta", "data": {"delta_content": "Python is"}}\n\n
data: {"type": "assistant.message_delta", "data": {"delta_content": " a programming"}}\n\n
...
event: done
data: {"invocation_id": "...", "session_id": "..."}
```

## Using Your Own Foundry Model

To use your own Azure AI Foundry model instead of the Copilot model, set the Foundry variables (no `GITHUB_TOKEN` needed):

```bash
cd src/github-copilot-invocations

FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project> \
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4-mini \
uv run --no-sync python main.py
```

Authentication uses Managed Identity via `DefaultAzureCredential`. When deployed as a hosted agent, `FOUNDRY_PROJECT_ENDPOINT` is auto-injected by the platform, so in `azure.yaml` you only need `AZURE_AI_MODEL_DEPLOYMENT_NAME` (declared by default).

## Adding Skills

Any subdirectory under `skills/` containing a `SKILL.md` file is automatically loaded by the Copilot SDK. The included `joke` skill demonstrates this:

```
skills/
└── joke/
    └── SKILL.md    ← tells Copilot to respond like a pirate
```

To add your own skill, create a new folder under `skills/` with a `SKILL.md`:

```bash
mkdir skills/my-skill
cat > skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: What this skill does.
---

# My Skill

Instructions for Copilot when this skill is active.
...
```

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
