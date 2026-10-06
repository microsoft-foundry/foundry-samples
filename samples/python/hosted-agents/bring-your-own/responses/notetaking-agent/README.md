# Note-Taking Agent — Python (Responses Protocol)

A note-taking agent built with `azure-ai-agentserver-responses` and Azure OpenAI. Uses function calling to save and retrieve notes, with per-session JSONL persistence accessible via the Session Files API.

## Features

- **Save notes** — natural language commands like "save a note - buy groceries"
- **Retrieve notes** — "show me my notes" returns all saved entries with timestamps
- **Per-session isolation** — each session gets its own note file
- **Streaming responses** — real-time SSE streaming via the Responses protocol
- **Session Files API** — notes stored at `$HOME` are accessible via the platform file API

## Prerequisites

- Python 3.12+
- Azure OpenAI resource with a deployed model (e.g., `gpt-5.4-mini`)
- Azure credentials configured (e.g., `az login`)

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint URL | `https://your-project.services.ai.azure.com/api/projects/your-project` |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name declared in `azure.yaml` | `gpt-5.4-mini` |

## Option 1: Azure Developer CLI (`azd`)

### Run the agent locally

```bash
azd ai agent run
```

### Invoke the local agent

```bash
azd ai agent invoke --local "save a note - book reservation for dinner"
```

Or invoke directly with curl:

```bash
# Save a note
curl -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "save a note - book reservation for dinner", "stream": true, "agent_session_id": "my-session"}'

# Save another note
curl -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "save a note - buy groceries for the weekend", "stream": true, "agent_session_id": "my-session"}'

# Get all notes
curl -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "show me all my notes", "stream": true, "agent_session_id": "my-session"}'
```

### Deploy to Foundry

```bash
azd provision
azd deploy
```

### Invoke the deployed agent

```bash
azd ai agent invoke "save a note - book reservation for dinner"
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/notetaking-agent-responses-python

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/notetaking-agent-responses-python/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/notetaking-agent-responses-python`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## File Structure

| File | Description |
|---|---|
| `main.py` | Agent entry point with Responses handler and OpenAI function calling |
| `note_store.py` | Thread-safe per-session JSONL note persistence |
| `pyproject.toml` / `uv.lock` | Python dependencies and reproducible lock |
| `Dockerfile` | Container image definition |
| `azure.yaml` | Agent hosting configuration |
| `azure.yaml` | Agent metadata and template |
| `.dockerignore` | Docker build exclusions |

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
