# What this sample demonstrates

An **instrumented** [LangGraph](https://langchain-ai.github.io/langgraph/) agent hosted on Foundry over the **Responses protocol** using [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting). A single call to [`enable_auto_tracing()`](https://github.com/langchain-ai/langchain-azure/blob/main/libs/azure-ai/langchain_azure_ai/callbacks/tracers/auto_instrument.py) wires GenAI OpenTelemetry spans into every LangGraph node, LLM call, and tool invocation, with no per-call instrumentation code.

## How It Works

### Tools

| Tool | Purpose |
|---|---|
| `get_current_time` | Local `@tool` — returns the current UTC time. |
| `calculator` | Local `@tool` — evaluates a math expression. |

System prompt: *"You are a friendly assistant. Keep your answers brief."*

### LangGraph Agent

The compiled graph is built with `langchain.agents.create_agent(model, tools=[...], system_prompt=...)`, which returns a compiled LangGraph runnable implementing the standard ReAct loop.

See [main.py](src/langgraph-observability-responses/main.py) for the full implementation.

### Agent Hosting

The graph factory is registered in `langgraph.json` and loaded by `langchain_azure_ai.agents.hosting.run`, which exposes the OpenAI-compatible Responses endpoint at `/responses` and handles conversation history, streaming lifecycle events, and tool-call surfacing automatically.

### Instrumentation

LangGraph does not auto-enable tracing from environment variables alone — a code call is required. The sample makes this one call at startup:

```python
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing
enable_auto_tracing()
```

This injects an `AzureAIOpenTelemetryTracer` into every LangChain `BaseCallbackManager` and into the LangGraph helper factories, so every node, LLM call, and tool invocation produces [GenAI semantic-convention](https://opentelemetry.io/docs/specs/semconv/gen-ai/) spans.

The sample sets two tracing toggles in [azure.yaml](azure.yaml):

| Variable | Purpose |
|---|---|
| `OTEL_AUTO_CONFIGURE_AZURE_MONITOR` | Let `enable_auto_tracing()` configure the OpenTelemetry `TracerProvider` and Azure Monitor exporter itself, using `APPLICATIONINSIGHTS_CONNECTION_STRING`. |
| `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED` | Capture prompts, completions, and tool I/O on spans. |

The `APPLICATIONINSIGHTS_CONNECTION_STRING` environment variable is injected when the agent is deployed to Foundry, so no extra setup is needed in hosted mode. To ship telemetry from a **local** run, you must set it yourself — either in `.env` (for `uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses`) or via `azd env set` (for `azd ai agent run`).

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
mkdir hosted-langgraph-agent && cd hosted-langgraph-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/08-observability/azure.yaml
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

The agent host will start on `http://localhost:8088`. To ship telemetry from a local run, also set `APPLICATIONINSIGHTS_CONNECTION_STRING` via `azd env set` — see [.env.example](src/langgraph-observability-responses/.env.example).

### Invoke the local agent

In a separate terminal, invoke the running agent. This single-turn request exercises both tools and produces a rich span tree:

```bash
azd ai agent invoke --local "What time is it right now, and what is 42 multiplied by 17?"
```

Or invoke directly with curl:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "What time is it right now, and what is 42 multiplied by 17?"}'
```

A typical span hierarchy for this request:

- `invoke_agent` — the overall agent turn.
- `chat` — each call to the underlying model.
- `execute_tool` — each tool invocation (`get_current_time`, `calculator`).

See the [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for the span and attribute reference.

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke "What time is it right now, and what is 42 multiplied by 17?"
```

Once deployed, the agent's traces, metrics, and logs flow into the Application Insights workspace associated with your Foundry project. In the Foundry portal, open the agent and switch to the **Traces** tab to see each conversation and drill into its span tree.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Install uv if it is not already available:

  ```bash
  python -m pip install uv
  ```

- From the sample root, sync the committed environment:

  ```bash
  cd src/langgraph-observability-responses
  uv sync --frozen
  ```

- In VS Code, select `src/langgraph-observability-responses/.venv` as the Python interpreter.
### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.
