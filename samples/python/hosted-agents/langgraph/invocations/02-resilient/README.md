# What this sample demonstrates

A [LangGraph](https://langchain-ai.github.io/langgraph/) trip-planning agent
hosted on Microsoft Foundry over the **Invocations protocol** using
[`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting).
The sample combines Agent Server's resilient invocation lifecycle with durable
LangGraph checkpoints so an interrupted turn can continue after the host
restarts.

> **Work in progress / experimental.** The resilience APIs and recovery
> behavior demonstrated by this sample may change.

It demonstrates:

- background invocations retrieved by a stable invocation ID;
- exact LangGraph checkpoint recovery after a process restart;
- linear multi-turn sessions linked by `previous_invocation_id`;
- durable human approval before a sensitive tool executes;
- background retrieval and cancellation routes; and
- client recovery from create or polling connection failures and retryable HTTP
  errors.

## How It Works

### Graph shape

The agent is a real-model `StateGraph`. Flight and hotel searches run
automatically, while `book_trip` pauses at a durable LangGraph `interrupt()`
until the client approves or denies the tool call.

```text
START -> agent -> [search tools | approval] -> agent -> END
```

See [main.py](src/langchain-azure-resilient-invocations/main.py) for the graph,
tools, and hosting configuration.

### Recovery model

Recovery depends on two persistent layers: Agent Server stores the durable
invocation and protocol events, while the LangGraph checkpointer stores
workflow state. `FoundryCheckpointSaver` uses Foundry State Store when hosted
and automatically falls back to a file-backed local state store. Both modes
retain graph state across a process restart.

### Agent hosting

`InvocationsHostServer` exposes `/invocations` and supports foreground
streaming, background execution, retrieval, and cancellation. The host maps
`agent_session_id` to the LangGraph thread and uses `previous_invocation_id` to
continue the latest completed checkpoint in that session.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12 or later
- [`uv`](https://docs.astral.sh/uv/)
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
- Azure CLI authenticated with `az login`
- A Microsoft Foundry project and model deployment accessible through
  `DefaultAzureCredential`

Install the Foundry extension and authenticate:

```bash
azd ext install microsoft.foundry
azd auth login
```

See the [parent sample guide](../../../README.md#running-the-agent-host-locally)
for general Foundry setup options.

### Configure the environment

Create `src/langchain-azure-resilient-invocations/.env`:

```dotenv
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
```

### Start the host

From the sample root, start the host:

```bash
azd ai agent run --no-client
```

The Invocations endpoint is available at
`http://127.0.0.1:8088/invocations` by default.

### Use the Textual client

In another terminal, start the Textual CUI:

```bash
cd client
uv sync --frozen
uv run --no-sync python client.py
```

Ask it to book a trip. The CUI displays the proposed `book_trip` arguments
when the graph pauses; choose **Approve** to continue or **Deny** to reject the
tool call.

The CUI generates an `agent_session_id` at startup, reuses it for every turn,
and links turns with `previous_invocation_id`. It creates every turn as a
background invocation with a stable invocation ID, then polls that same ID until
the invocation reaches a terminal status. The composer remains available
immediately after submission. A new turn is queued locally until its active
parent is accepted, then steers it using the canonical invocation ID as
`previous_invocation_id`.

See [client/client.py](client/client.py) for the recovery client
implementation.

Useful client options:

| Option                | Purpose                                                                 |
| --------------------- | ----------------------------------------------------------------------- |
| `--url`               | Host base URL or full Invocations endpoint. Defaults to the local host. |
| `--auth`              | Acquire an Azure AI bearer token for a deployed agent.                  |
| `--reconnect-timeout` | Seconds to keep recovering an interrupted turn. Defaults to 120.        |

## Option 2: VS Code (Foundry Toolkit)

Install the
[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
and Python extensions. Install the agent dependencies and start the host:

```bash
cd src/langchain-azure-resilient-invocations
uv sync --frozen
uv run --no-sync python main.py
```

Then open **Agent Inspector** in VS Code
(Command Palette: **Foundry Toolkit: Open Agent Inspector**) and send:

```text
Find flights and a hotel for a two-night trip to Paris.
```

Use the Textual client for the approval, reconnect, and crash-recovery flows
because it preserves the stable invocation and session IDs required by this
sample.

## Test crash recovery

Start the host normally:

```bash
azd ai agent run --no-client
```

Start the CUI in another terminal:

```bash
cd client
uv run --no-sync python client.py
```

Enter:

```text
Call simulate_crash, recover, and report the result.
```

The tool terminates the host on its first execution. Restart the host with the
same command before the client timeout expires. The CUI polls the same
invocation and the graph resumes from its local checkpoint; do not submit the
original request again. By default, Agent Server and LangGraph persist local
state beneath `~/.agentserver`.

The same flow works against a deployed Foundry agent:

```bash
cd client
uv run --no-sync python client.py --url "<hosted-invocations-endpoint>" --auth
```

After the hosted process restarts, the CUI polls the same invocation and the
graph resumes from its Foundry checkpoint.

## Protocol reference

### Create and retrieve an invocation

Choose the invocation ID before create and reuse it for all recovery requests:

```bash
curl -X POST \
  "http://127.0.0.1:8088/invocations?agent_session_id=trip-demo" \
  -H "Content-Type: application/json" \
  -H "x-agent-invocation-id: <invocation-id>" \
  -d '{
    "message": "Book a two-night trip to Paris",
    "background": true
  }'
```

A background create returns `202`. Poll the invocation by that same ID until
it reaches a terminal status:

```bash
curl "http://127.0.0.1:8088/invocations/<invocation-id>"
```

For foreground SSE output, send `"stream": true` instead of
`"background": true` and consume events through `event: done`. The two modes
cannot be combined. The sample CUI uses background mode and polls the retrieval
endpoint until the invocation reaches a terminal status.

### Approve the booking

The first invocation completes with an `mcp_approval_request` in its `output`
array. Use its `id` in the next invocation, keep the same session, and link the
completed turn with `previous_invocation_id`:

```bash
curl -X POST \
  "http://127.0.0.1:8088/invocations?agent_session_id=trip-demo" \
  -H "Content-Type: application/json" \
  -H "x-agent-invocation-id: <next-invocation-id>" \
  -d '{
    "message": [{
      "type": "mcp_approval_response",
      "approval_request_id": "<approval-request-id>",
      "approve": true
    }],
    "previous_invocation_id": "<invocation-id>",
    "background": true
  }'
```

The sample CUI constructs both approval and denial responses automatically.

### Cancel an invocation

```bash
curl -X POST \
  "http://127.0.0.1:8088/invocations/<invocation-id>/cancel"
```

Cancellation stops future work but does not roll back completed checkpoints or
external effects.

## Recovery contract

### Client behavior

| Condition                                                                                       | Required action                                                                                    |
| ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Create or retrieval connection failure, retryable HTTP error, or post-admission retrieval `404` | Retrieve the same stable invocation ID until it becomes terminal or the reconnect timeout expires. |
| Retrieval returns `404` before create was admitted                                              | Retry create with the same invocation ID. Never generate a replacement ID.                         |
| Other HTTP `4xx` or an explicit terminal protocol event                                         | Treat the result as final; do not retry it.                                                        |
| Starting the next turn                                                                          | Reuse the `agent_session_id` and send the latest invocation ID as `previous_invocation_id`.        |

Each turn needs a stable `x-agent-invocation-id` chosen before create. Sessions
are linear: a new turn continues from the latest completed invocation rather
than forking an older checkpoint.

### Graph and handler behavior

- Compile the graph with a durable checkpointer that survives process
  replacement and is accessible to every recovering host instance.
- Keep durable workflow data in LangGraph state. Process memory, local caches,
  active HTTP requests, `InvocationContext`, and cancellation events are
  transient.
- Make nodes replay-safe. A crash after an external action but before the next
  paired checkpoint can execute that action again.
- Make external side effects idempotent, or deduplicate them with a stable
  operation key. At-least-once execution applies to writes, payments, email,
  queue publication, and other mutating tool calls.
- Keep checkpointed state serializable and compatible across deployments.

Before using this pattern in production, crash-test every node boundary and
both sides of each external side effect. Review the checkpoint retention period
and use durable stores for any additional application state.

## Configuration

| Variable                         | Default              | Purpose                                                                                   |
| -------------------------------- | -------------------- | ----------------------------------------------------------------------------------------- |
| `PORT`                           | `8088`           | HTTP port for the agent host.                                                     |
| `AGENTSERVER_STATE_ROOT`         | `~/.agentserver` | Local durable task, invocation, protocol-event, and LangGraph checkpoint state.   |
| `STEERABLE_CONVERSATIONS`        | `false`          | Enable server-side active-turn steering support.                                  |
| `FOUNDRY_PROJECT_ENDPOINT`       | None             | Required Foundry project endpoint.                                                |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | None             | Required Foundry model deployment name.                                           |

Hosted checkpoint items use Foundry State Store's default 30-day sliding TTL.
Local checkpoints remain beneath `${AGENTSERVER_STATE_ROOT}/state_stores`.

## Deploying the Agent to Foundry

See the [parent deployment guide](../../../README.md#deploying-the-agent-to-foundry)
for the common hosted-agent workflow. This directory is an independent `azd`
project. Its [azure.yaml](azure.yaml) defines both regular and steerable
Invocations services.

Install `azd` and authenticate:

```powershell
azd auth login
```

Create a local deployment configuration from the committed template:

```powershell
Copy-Item .\src\langchain-azure-resilient-invocations\.env.example .\.env
```

Replace the placeholders in `.env`. To use an existing Foundry project,
uncomment and set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_PROJECT_ID`; its
configured model deployment must already exist.

Create and select a new `azd` environment:

```powershell
azd env new resilient
```

If the target `azd` environment already exists, select it instead. This is also
how you switch away from another currently selected environment:

```powershell
azd env list
azd env select <environment-name>
```

Import `.env` into the selected `azd` environment:

```powershell
azd env set --file .\src\langchain-azure-resilient-invocations\.env
```

To create a new Foundry project and the model declared in `azure.yaml`, provision
them before deploying:

```powershell
azd provision
azd deploy
```

If `.env` targets an existing Foundry project, do not run `azd provision`.
The project and selected model deployment must already exist; deploy the agents
directly:

```powershell
azd deploy
```

Run CUI against a deployed Microsoft Foundry agent with Azure authentication:

```bash
cd client
uv run --no-sync python client.py --url "https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>/endpoint/protocols/invocations?api-version=v1" --auth
```
