**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Resilient Research Agent — Invocations Protocol

This sample demonstrates a **long-running, crash-resilient, streaming** agent built with [azure-ai-agentserver-invocations](https://pypi.org/project/azure-ai-agentserver-invocations/) on top of the resilient `@multi_turn_task` primitive and the streaming API from [azure-ai-agentserver-core](https://pypi.org/project/azure-ai-agentserver-core/).

The agent runs a multi-phase deep-research plan. Each phase issues several streaming LLM sub-calls (research → critique → refine → synthesize), and progress streams to the client token-by-token over Server-Sent Events. The work is designed to **outlive a single request and even a single container lifetime**: it checkpoints after every sub-call, so a container restart, OOM kill, or redeploy resumes mid-phase — no gap, no repeated work, and reconnecting SSE clients pick up exactly where they left off.

It showcases four capabilities that matter for autonomous hosted agents:

- **Long-running autonomous work** — a plan of many streaming LLM sub-calls that runs on its own.
- **Crash resilience** — per-sub-call watermarks and in-flight text share one application-owned `FoundryStateStore` item with retention matching task recovery; on restart the framework re-invokes the interrupted turn with `ctx.entry_mode == "recovered"` and the handler resumes from the last completed sub-call (worst case: one wasted sub-call, the one actively streaming when the process died).
- **Resumable streaming** — events persist to disk; a client that disconnects can reconnect via `GET` with `?last_event_id=N` and receive the pre-crash events, a `recovered` marker, and the post-crash continuation.
- **Steering** — POST a new topic while a run is in progress and the current turn winds down cleanly at the next checkpoint; the framework re-enters with the new topic.

See the [Resilient Task Developer Guide](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/agentserver/azure-ai-agentserver-core/docs/tasks-guide.md) and the [Streaming Developer Guide](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/agentserver/azure-ai-agentserver-core/docs/streaming-guide.md).

### Offline demo mode

If `FOUNDRY_PROJECT_ENDPOINT` is not set, the agent runs in **offline demo mode** with deterministic synthetic token streams instead of real model calls, so you can exercise the full resilient / streaming / steering control flow with no Azure credentials.

## How It Works

```
POST /invocations {"topic": "..."}
        │
        ▼
   research turn ──► phase 1 ──► sub-call 1..N (stream tokens, checkpoint each)
        │              ├──► phase 2 ──► ...
        │              └──► phase K ──► run_complete
        │
        ├─ (container crash mid-turn) ─► restart ─► entry_mode="recovered" ─► resume from watermark
        └─ (new POST while running)   ─► steer   ─► wind down ─► re-enter with new topic
```

Each turn is one resilient task per session (`task_id = research-<session_id>`); a per-turn `invocation_id` labels the stream.

## Endpoints

| Route | Description |
| --- | --- |
| `POST /invocations` with `Accept: text/event-stream` | Start a run and stream its events live (SSE). |
| `POST /invocations` without the SSE header | Start a run; returns `202` with the `invocation_id`. |
| `GET /invocations/{invocation_id}` with `Accept: text/event-stream` | Stream the turn's events; `?last_event_id=N` resumes after a disconnect. |
| `GET /invocations/{invocation_id}?agent_session_id=<id>` | JSON snapshot of the task's current status/payload. |
| `POST /invocations/{invocation_id}/cancel?agent_session_id=<id>` | Cooperatively cancel the running task. |

Polling reports `running`, `completed`, `failed`, or `cancelled` from the
invocation's durable terminal marker. It does not infer an older invocation's
result from the shared multi-turn task status.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12+
- Azure CLI installed and authenticated (`az login`)
- Azure OpenAI resource with a deployed model

### Run the agent locally

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Invoke the local agent

```bash
# Stream a research run live (SSE).
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=research-1" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"topic": "quantum error correction"}'
# -> id: 1  data: {"type": "run_start", ...}
# -> id: 2  data: {"type": "phase_start", "phase": 1, ...}
# -> id: 3  data: {"type": "token", "content": "..."}
# -> ...    (more tokens, subcall_start/subcall_end, phase_end, cooldown)
# -> event: done

# Or start without streaming and poll the JSON snapshot.
curl -X POST "http://localhost:8088/invocations?agent_session_id=research-1" \
  -H "Content-Type: application/json" \
  -d '{"topic": "quantum error correction"}'
# -> 202 {"status": "started", "invocation_id": "<inv>", ...}
curl "http://localhost:8088/invocations/<inv>?agent_session_id=research-1"
# -> {"status": "running", "state": {...}}

# Reconnect a dropped stream, skipping events already seen.
curl -N "http://localhost:8088/invocations/<inv>?agent_session_id=research-1&last_event_id=42" \
  -H "Accept: text/event-stream"

# Steer: POST a new topic on the same session while a run is in progress.
curl -X POST "http://localhost:8088/invocations?agent_session_id=research-1" \
  -H "Content-Type: application/json" \
  -d '{"topic": "photonic quantum computing"}'

# Cancel the running task.
curl -X POST "http://localhost:8088/invocations/<inv>/cancel?agent_session_id=research-1"
```

### Try the crash-recovery story

Start a run, then kill the process mid-stream and restart it. The recovery scan re-invokes the interrupted turn, resumes from the last checkpointed sub-call, and (for a reconnecting SSE client) replays the pre-crash events plus a `recovered` marker before continuing:

```bash
# Make the run long enough to interrupt.
NUM_PHASES=15 INTER_PHASE_COOLDOWN_SEC=20 azd ai agent run
# start a run, Ctrl-C mid-stream, then re-run `azd ai agent run` and reconnect via GET-SSE.
```

### Deploy to Foundry

```bash
azd provision
azd deploy
```

### Invoke the deployed agent

```bash
azd ai agent invoke '{"topic": "quantum error correction"}'
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
  cd src/resilient-research

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/resilient-research/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/resilient-research`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Files

| File | Purpose |
| --- | --- |
| `src/resilient-research/main.py` | HTTP host — wires the resilient task to the invocations protocol (POST-SSE, GET-SSE/poll, cancel) and bootstraps file-backed streaming. |
| `src/resilient-research/agent.py` | The `@multi_turn_task` research handler — phases, streaming sub-calls, per-sub-call checkpointing, cooperative wind-down. |
| `src/resilient-research/store.py` | Minimal `FoundryStateStore`-backed persistence for invocation checkpoints and terminal markers, with a local-file fallback. |

## Troubleshooting

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error code: 401 - {'error': {'code': 'PermissionDenied', 'message': 'The principal <principal-id> lacks the required data action ...'}}
```

The identity running the agent does not have the required RBAC roles on the Azure AI Foundry project. Assign the following roles:

- **Cognitive Services OpenAI User**
- **Foundry User**

Use the Azure CLI to assign them:

```bash
# Set your variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="<your-resource-group>"
PROJECT_NAME="<your-ai-foundry-project-name>"
PRINCIPAL_ID="<principal-id-from-error-message>"

# Assign "Cognitive Services OpenAI User" role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/$PROJECT_NAME"

# Assign "Foundry User" role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Foundry User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/$PROJECT_NAME"
```

> **Note:** It may take a few minutes for role assignments to propagate. Retry the request after waiting.

### Local IMDS / credential noise

When running locally without `azd ai agent run`, `DefaultAzureCredential` may probe the instance metadata endpoint. Set `AZURE_AI_CREDENTIAL=cli` to force `AzureCliCredential` only, or leave `FOUNDRY_PROJECT_ENDPOINT` unset to run in offline demo mode.
