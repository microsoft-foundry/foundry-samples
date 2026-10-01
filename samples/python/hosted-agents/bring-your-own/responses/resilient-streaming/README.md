**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Resilient Streaming Agent — Responses Protocol

This sample demonstrates a **crash-resilient, resumable-streaming** agent built with [azure-ai-agentserver-responses](https://pypi.org/project/azure-ai-agentserver-responses/). It streams a multi-stage response and **checkpoints after each stage**, so a client that disconnects — or a container that crashes — can reconnect and continue from the last completed stage **with no gap, no duplicated content, and no regeneration** of finished stages.

This is the canonical **framework-checkpoint** recovery pattern (`stream.checkpoint()` + `context.persisted_response`).

## What it's good for

Any long, multi-stage generation where a client disconnect or container crash must not lose — or re-bill for — completed work:

- **Long-form document / report generation** (outline → draft → refine → cite). A dropped connection resumes with completed sections intact.
- **Deep-research / multi-step agents** — long reasoning + tool-call chains streamed live.
- **Code / large-refactor generation** — generate a big change stage by stage; reconnect resumes.
- **Flaky-network (mobile) clients** — reconnect without losing or re-paying for tokens.
- **Expensive per-step agentic workflows** — checkpoint boundaries avoid re-running costly completed steps.

## How It Works

```
POST /responses {input, stream:true, store:true, background:true}
      │
      ▼
   stage: analyze ──► [checkpoint]
   stage: generate ─► [checkpoint]
   stage: refine ───► [checkpoint] ──► completed
      │
      ├─ (client disconnects)  ─► reconnect to same response_id ─► replay + continue
      └─ (container crashes)   ─► restart ─► is_recovery ─► seed from persisted_response ─► resume next stage
```

- Each stage emits **one output item** and calls `yield stream.checkpoint()`, which durably persists the response snapshot (every finished item, with its **original id**).
- On recovery, the handler seeds the stream from `context.persisted_response` and resumes at the first un-checkpointed stage — re-emitting the completed items with their original ids (the client-visible reset point).
- A stage interrupted **before** its checkpoint is simply re-run — no watermark bookkeeping, no LLM output stored in metadata.

Enabled by `ResponsesServerOptions(resilient_background=True)` and `store=true, background=true` on the request.

The stages stream **simulated** tokens so the sample runs offline with no credentials — replace `_stage_tokens` with a real model call (e.g. Azure OpenAI via `AIProjectClient(...).get_openai_client()`) to make it live.

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
# Stream a resilient, resumable response (background + stored).
curl -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"model": "streamer", "input": "Tell me about resilience", "stream": true, "store": true, "background": true}'
# -> streams: response.created -> in_progress -> (3 stages of output_text deltas) -> completed

# Reconnect after a drop: re-open the stream for the same response id.
curl -N "http://localhost:8088/responses/<response_id>?stream=true"

# Fetch the final result at any time.
curl "http://localhost:8088/responses/<response_id>"
```

### Try crash recovery locally

Hard-crash the process right after a stage checkpoints, then restart — the handler is re-invoked, seeds from `context.persisted_response`, and resumes from the next stage:

```bash
# Crash after stage 0 (analyze) is checkpointed.
SIMULATE_CRASH_AFTER_STAGE=0 azd ai agent run
# ... POST a background+store request; the process exits after stage 0.
# Restart the agent (same AGENTSERVER_STATE_ROOT); GET the response id:
#   -> status "completed" with all 3 stages (analyze reused from checkpoint; generate + refine resumed).
```

> **Note on local crash testing.** `SIMULATE_CRASH_AFTER_STAGE` uses a hard `os._exit(1)` — a real crash that exercises the framework's lease-based recovery (the correct mechanism; a *simulated graceful shutdown* via `context.shutdown` does not set the underlying task shutdown, so `exit_for_recovery` would reject it). Crash recovery is fully exercised on **Linux / WSL2 / a container** (which is also the hosted runtime). On native Windows, the file-backed stream lock is a best-effort lock-file that a hard crash leaves stale, so you must delete the `*.jsonl.lock` under `${AGENTSERVER_STATE_ROOT}/streams/` between the crash and the restart (Linux's `fcntl` lock is released automatically by the kernel).

### Deploy to Foundry

```bash
azd provision
azd deploy
azd ai agent invoke '{"input": "Tell me about resilience", "store": true, "background": true}'
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

- This sample ports the framework-checkpoint streaming pattern from the [azure-sdk-for-python resilient Responses samples](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/agentserver/azure-ai-agentserver-responses/samples) (`sample_19`).
- Recovery requires `store=true` **and** `background=true` on the request (plus `resilient_background=True` on the server). A foreground response gets a "failed" marker on crash rather than re-invocation.
