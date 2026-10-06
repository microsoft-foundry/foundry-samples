**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Resilient Approval-Gate Agent — Invocations Protocol

This sample demonstrates a **long-running, crash-resilient human-in-the-loop** agent built with [azure-ai-agentserver-invocations](https://pypi.org/project/azure-ai-agentserver-invocations/) on top of the resilient `@multi_turn_task` primitive from [azure-ai-agentserver-core](https://pypi.org/project/azure-ai-agentserver-core/). The agent plans a goal with Azure OpenAI, **gates the plan on human approval**, executes it step by step, and **gates every irreversible step on a second human confirmation** — performing each irreversible action *exactly once*, even across container restarts.

Unlike a synchronous "generate a proposal and approve it" flow, the work here is genuinely long-running: the execution phase runs autonomously and can span container evictions, OOM kills, and redeployments. The framework persists task lifecycle state, while application checkpoints are stored explicitly in `FoundryStateStore`, so an interrupted run **resumes from its last checkpoint** — it never restarts from scratch and never repeats a completed irreversible step.

The sample explicitly enables the resilient task subsystem with `set_resilient_tasks_enabled(True)`, as required by AgentServer Core 2.1 and later.

This pattern fits workflows where an agent should **act autonomously but never cross a dangerous line without a human** — provisioning infrastructure, publishing or sending communications, tagging a release, or applying irreversible changes.

## How It Works

```
[plan] ─► AWAITING_PLAN_APPROVAL ─► (approve / edit) ─► EXECUTING ─┐
                │                                                   │
                └─► (reject) ─► RESOLVED (rejected)   ┌────────────┘
                                                      ▼
                            AWAITING_ACTION_APPROVAL ─► (approve_action) ─► EXECUTING
                                                      └─► (reject_action) ─► RESOLVED (stopped)
                                                      ...
                                            (all steps done) ─► RESOLVED (completed)
```

1. **Submit a goal** via `POST /invocations` with `{"action": "plan", "goal": "..."}` — the agent decomposes it into an ordered plan, flags which steps are **irreversible**, and pauses with status `awaiting_plan_approval`.
2. **The agent pauses** — the chain suspends. The human can return minutes, hours, or days later; the plan is persisted in `FoundryStateStore`, not process memory.
3. **Approve the plan** via `{"action": "approve_plan"}` (or `edit_plan` with a revised `plan`, or `reject`). The agent begins executing, **checkpointing after every step**.
4. **Confirm each irreversible step** — before any irreversible action the agent suspends again with status `awaiting_action_approval`. Copy the returned `gate` object into `{"action": "approve_action", "gate": {...}}` to run it exactly once, or use `reject_action` to halt. The gate binds the decision to the invocation and step that requested it.
5. **Poll status** via `GET /invocations/{invocation_id}?agent_session_id=<id>` — every POST returns `202` immediately; poll for the current status and output.

### Why the resilient task primitive

The execution phase is the part most likely to be interrupted. Building on `@multi_turn_task` means:

- **Crash recovery** — after a restart, the framework re-invokes the interrupted turn with the same input (`ctx.entry_mode == "recovered"`), and the handler resumes from the last checkpointed step.
- **At-most-once side effects** — a per-step watermark plus an idempotency token guarantee a completed (or in-flight) irreversible step is never executed twice.
- **Graceful shutdown** — on container shutdown the handler defers the turn (`ctx.exit_for_recovery()`) so the next lifetime picks it up.

See the [Resilient Task Developer Guide](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/agentserver/azure-ai-agentserver-core/docs/tasks-guide.md).

### Offline demo mode

If `FOUNDRY_PROJECT_ENDPOINT` is not set, the agent runs in **offline demo mode** with deterministic stand-ins for the model, so you can exercise the full resilient control flow with no Azure credentials.

## OpenAPI Spec

The agent includes an inline OpenAPI 3.0 specification that documents the request/response contract. It is served at:

```
GET http://localhost:8088/invocations/docs/openapi.json
```

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

Drive the full plan → approve → execute flow with curl (`STEP_DURATION_SEC` controls simulated per-step work):

```bash
# 1. Submit a goal — the agent plans, then suspends for approval.
curl -X POST "http://localhost:8088/invocations?agent_session_id=job-1" \
  -H "Content-Type: application/json" \
  -d '{"action": "plan", "goal": "Prepare the Q3 release"}'
# -> 202 {"invocation_id": "<i1>", "status": "running"}

# 2. Poll until the plan is ready.
curl "http://localhost:8088/invocations/<i1>?agent_session_id=job-1"
# -> {"status": "awaiting_plan_approval", "output": {"plan": [...]}}

# 3. Approve the plan — the agent starts executing (long-running).
curl -X POST "http://localhost:8088/invocations?agent_session_id=job-1" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_plan", "approver": "sam"}'

# 4. Poll — execution pauses at the first irreversible step.
curl "http://localhost:8088/invocations/<i2>?agent_session_id=job-1"
# -> {"status": "awaiting_action_approval", "output": {"next_step": {...}}}

# 5. Confirm the irreversible step — it runs exactly once.
curl -X POST "http://localhost:8088/invocations?agent_session_id=job-1" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_action", "approver": "sam", "gate": {"invocation_id": "<i2>", "step_index": 3, "token": "<token-from-poll>"}}'
# ... repeat steps 4-5 for each irreversible step, until status == "resolved".

# Optional: edit the plan instead of approving as-is.
curl -X POST "http://localhost:8088/invocations?agent_session_id=job-1" \
  -H "Content-Type: application/json" \
  -d '{"action": "edit_plan", "plan": [{"action": "Do X", "irreversible": false}]}'

# Optional: reject the plan, or cancel the whole job.
curl -X POST "http://localhost:8088/invocations?agent_session_id=job-1" \
  -H "Content-Type: application/json" -d '{"action": "reject"}'
curl -X POST "http://localhost:8088/invocations/<invocation_id>/cancel?agent_session_id=job-1"
```

### Try the crash-recovery story

Set a longer per-step duration, start the flow, then kill the process mid-execution and restart it. The recovery scan re-invokes the interrupted turn, resumes from the last completed step (no re-runs), and stops at the next irreversible gate:

```bash
STEP_DURATION_SEC=10 azd ai agent run
# submit + approve_plan, then Ctrl-C mid-execution and re-run `azd ai agent run`.
```

### Deploy to Foundry

```bash
azd provision
azd deploy
```

### Invoke the deployed agent

```bash
azd ai agent invoke '{"action": "plan", "goal": "Prepare the Q3 release"}'
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
  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Troubleshooting

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error calling Azure OpenAI: Error code: 401 - {'error': {'code': 'PermissionDenied', 'message': 'The principal <principal-id> lacks the required data action Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action to perform POST /openai/deployments/{deployment-id}/chat/completions operation.'}}
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

### 409 Conflict on POST

A `409` means the chain is mid-execution (in-flight, non-steerable). Wait for the current gate (`awaiting_plan_approval` / `awaiting_action_approval`) before posting the next decision.
