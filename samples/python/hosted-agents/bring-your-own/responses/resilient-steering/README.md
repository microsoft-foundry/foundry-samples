**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Resilient Steering Agent — Responses Protocol

This sample demonstrates a **crash-resilient, steerable** long-running agent built with [azure-ai-agentserver-responses](https://pypi.org/project/azure-ai-agentserver-responses/). It shows how the cancellation policy and the crash-recovery contract **compose** when steering, client cancel, and shutdown interleave with crash recovery.

Two opt-in options drive the behavior (both default to `False`):

- **`resilient_background=True`** — a `store=true, background=true` response survives process crashes. The framework persists handler progress and re-invokes the handler on the next process start if a prior attempt did not reach a terminal event.
- **`steerable_conversations=True`** — a client can POST a new turn on an in-flight conversation. The running handler is woken via the cancellation signal (distinguished by `context.pending_input_count > 0`), winds the current turn down cleanly, and the framework re-invokes with the new input.

Recovery here is deliberately **naive**: the handler wraps a non-deterministic upstream (an LLM) and does **not** checkpoint partial output, so recovery needs no special code — every entry builds a fresh stream and re-runs the turn from scratch. The fresh `response.in_progress` (empty output) is the client-visible reset. A `turn_count` watermark in `FoundryStateStore`, keyed by `context.conversation_chain_id`, survives crashes and turn boundaries.

The LLM is **simulated** so the sample runs offline with no credentials — replace `_simulate_llm_stream` with a real model call to make it live.

## How It Works

```
POST /responses {input, store:true, background:true}
      │
      ▼
   turn 1 ──► stream tokens ──► completed
      │
      ├─ (new POST, same conversation)  ─► STEER ─► wind down turn 1 ─► re-invoke with new input ─► turn 2
      ├─ (client cancel)                ─► framework forces "cancelled"
      └─ (process crash / shutdown mid-stream) ─► exit_for_recovery ─► re-run turn from scratch on restart
```

## Cancellation surfaces (mutually exclusive)

| Signal | How the handler sees it | Response |
| --- | --- | --- |
| **Steering** (new turn queued) | `cancellation_signal` set **and** `context.pending_input_count > 0` | Close builders, `emit_completed()` — partial output becomes context for the next turn |
| **Client cancel** | `cancellation_signal` set, `pending_input_count == 0` | Return without a terminal; framework forces `cancelled` |
| **Shutdown** | `context.shutdown.is_set()` (does **not** fire the cancellation signal) | `await context.exit_for_recovery()` — defer to next-lifetime recovery |

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment
- Azure CLI installed and authenticated (`az login`)

### Run the agent locally

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Invoke the local agent

```bash
# Basic turn.
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"model": "agent", "input": "Explain quantum computing"}'

# Resilient + steerable turn (stored background response).
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"model": "agent", "input": "Explain quantum computing", "store": true, "background": true}'
# -> {"id": "<id>", "status": "in_progress", ...}

# Steer — supersede the in-flight turn on the same conversation.
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"model": "agent", "input": "Actually explain relativity", "store": true, "background": true, "previous_response_id": "<id>"}'

# Poll a background response.
curl http://localhost:8088/responses/<id>

# Cancel an in-flight response.
curl -X POST http://localhost:8088/responses/<id>/cancel
```

### Try the recovery path

Fire a simulated mid-stream shutdown; the framework re-invokes the handler on the next lifetime and the turn re-runs from scratch:

```bash
SIMULATE_SHUTDOWN_MS=200 azd ai agent run
```

### Deploy to Foundry

```bash
azd provision
azd deploy
azd ai agent invoke '{"model": "agent", "input": "Explain quantum computing"}'
```

Stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment (or **Python: Select Interpreter** to use an existing one).
- Install dependencies:

  ```bash
  uv sync --frozen
  ```

### Run and debug the agent

Press **F5** to start the agent. The **Agent Inspector** opens automatically — chat with the agent there.

### Or run manually, then open the Inspector

1. Sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message.

### Deploy to Foundry

1. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Deploy Hosted Agent**. The extension reads `azure.yaml` to auto-populate settings.
2. Complete **Foundry Project Setup** if prompted.
3. On **Basics**, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Notes

- This sample ports the resilient-steering pattern from the [azure-sdk-for-python resilient Responses samples](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/agentserver/azure-ai-agentserver-responses/samples).
- To wire a real model, replace `_simulate_llm_stream` with a streaming call to Azure OpenAI via `AIProjectClient(...).get_openai_client()`, and set `AZURE_AI_MODEL_DEPLOYMENT_NAME`.
