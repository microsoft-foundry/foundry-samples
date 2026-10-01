# OpenAI Agents SDK — Responses Protocol (Streaming)

**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

A minimal getting-started agent using the [OpenAI Python SDK](https://pypi.org/project/openai/) (Responses API) backed by **Microsoft Foundry** (no OpenAI API key required), with the [azure-ai-agentserver-responses](https://pypi.org/project/azure-ai-agentserver-responses/) protocol.

Authentication uses `DefaultAzureCredential` via `AIProjectClient` — the same pattern used by other Foundry hosted-agent samples.

## How It Works

1. Receives requests via `POST /responses`
2. Reads input from the responses context (`context.get_input_text()`)
3. Reads platform-managed history (`context.get_history()`)
4. Streams text deltas from OpenAI Agents SDK events
5. Returns `TextResponse(...)` so the responses protocol SDK emits the response lifecycle/events

## Environment Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint (auto-injected in hosted containers; set by `azd ai agent run` locally) |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name in your Foundry project |

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment
- A Microsoft Foundry project with a model deployment (e.g. `gpt-4o-mini`)
- Azure CLI logged in (`az login`) or another credential supported by `DefaultAzureCredential`

### Run the agent locally

`azd ai agent run` automatically injects `FOUNDRY_PROJECT_ENDPOINT` and starts the agent:

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Invoke the local agent

**Bash:**
```bash
azd ai agent invoke --local "What can you help me with?"
```

Or invoke directly with curl:

```bash
# First message
curl -sS -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is Microsoft Foundry?", "stream": true}'

# Follow-up (multi-turn — same session remembers context)
curl -sS -N -X POST "http://localhost:8088/responses" \
  -H "Content-Type: application/json" \
  -d '{"input": "What hosted agent options does it offer?", "agent_session_id": "chat-001", "stream": true}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd provision
azd deploy
```

### Invoke the deployed agent

**Bash:**
```bash
azd ai agent invoke '{"input": "What can you help me with?"}'
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

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install dependencies in the virtual environment:

  ```bash
  uv sync --frozen
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

## Streaming behavior

The responses protocol SDK emits lifecycle and content events automatically when
`TextResponse(...)` is returned.

## Troubleshooting

### `FOUNDRY_PROJECT_ENDPOINT` not set

```text
EnvironmentError: FOUNDRY_PROJECT_ENDPOINT environment variable is not set.
```

Use `azd ai agent run` which sets this automatically, or set it manually:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
```

### `AZURE_AI_MODEL_DEPLOYMENT_NAME` not set

Set it to the name of a model deployment in your Foundry project:

```bash
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

### Authentication failure

Ensure you are logged in with Azure CLI:

```bash
az login
```

`DefaultAzureCredential` tries several credential sources in order. See the [azure-identity docs](https://learn.microsoft.com/python/api/azure-identity/azure.identity.defaultazurecredential) for details.

### No streaming output

Ensure you are using `curl -N` or another streaming-capable HTTP client. The agent uses `text/event-stream` media type.

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
