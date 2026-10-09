# What this sample demonstrates

A [LangGraph](https://langchain-ai.github.io/langgraph/) trip-planning agent
hosted on Microsoft Foundry over the **Responses protocol** using
[`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting).
The sample combines Agent Server's resilient background response lifecycle
with durable LangGraph checkpoints so an interrupted turn can continue after
the host restarts.

> **Work in progress / experimental.** The resilience APIs and recovery
> behavior demonstrated by this sample may change.

It demonstrates:

- background Responses with replayable SSE output;
- exact LangGraph checkpoint recovery after a process restart;
- linear multi-turn conversations and optional active-turn steering;
- durable human approval before a sensitive tool executes;
- retrieval and cancellation of stored responses; and
- client recovery from connection failures, interrupted SSE streams, and HTTP
  `5xx` responses.

## How It Works

### Graph shape

The agent is a real-model `StateGraph`. Flight and hotel searches run
automatically, while `book_trip` pauses at a durable LangGraph `interrupt()`
until the client approves or denies the tool call.

```text
START -> agent -> [search tools | approval] -> agent -> END
```

See [main.py](src/langchain-azure-resilient-responses/main.py) for the graph,
tools, and hosting configuration.

### Recovery model

Recovery depends on two persistent layers: Agent Server stores the durable
response and replayable events, while the LangGraph checkpointer stores
workflow state. `FoundryCheckpointSaver` uses Foundry State Store when hosted
and automatically falls back to a file-backed local state store. Both modes
retain graph state across a process restart.

### Agent hosting

`langchain_azure_ai.agents.hosting.run` loads the graph from `langgraph.json`
and exposes the OpenAI-compatible `/responses` endpoint. The configured server
options enable background recovery and active-turn steering. The host maps the
conversation ID to the LangGraph thread and uses `previous_response_id` to
continue the latest completed checkpoint.

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

Create `src/langchain-azure-resilient-responses/.env`:

```dotenv
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
```

### Start the host

From the sample root, start the host:

```bash
azd ai agent run --no-client
```

The Responses endpoint is available at
`http://127.0.0.1:8088/responses` by default.

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

The CUI generates a conversation ID at startup, creates a stable response ID
for every turn, sends `background=true`, `stream=true`, and `store=true`, and
reconnects from the last received SSE sequence number. It also supports
cancellation and enables the composer during active output only when the server
advertises steering support.

See [client/client.py](client/client.py) for the recovery client
implementation.

Useful client options:

| Option                | Purpose                                                               |
| --------------------- | --------------------------------------------------------------------- |
| `--url`               | Host base URL or full Responses endpoint. Defaults to the local host. |
| `--auth`              | Acquire an Azure AI bearer token for a deployed agent.                |
| `--reconnect-timeout` | Seconds to keep recovering an interrupted turn. Defaults to 120.      |

## Option 2: VS Code (Foundry Toolkit)

Install the
[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
and Python extensions. Install the agent dependencies and start the host:

```bash
cd src/langchain-azure-resilient-responses
uv sync --frozen
uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses \
  --option resilient_background=true \
  --option steerable_conversations=true
```

Then open **Agent Inspector** in VS Code
(Command Palette: **Foundry Toolkit: Open Agent Inspector**) and send:

```text
Find flights and a hotel for a two-night trip to Paris.
```

Use the Textual client for the approval, reconnect, steering, and
crash-recovery flows because it preserves the stable response and conversation
IDs required by this sample.

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
same command before the client timeout expires. The CUI retrieves the same
stored response, resumes after its last SSE cursor, and restores the graph from
the local state store; do not submit the original request again. By default,
Agent Server and LangGraph persist local state beneath `~/.agentserver`.

The same flow works against a deployed Foundry agent:

```bash
cd client
uv run --no-sync python client.py --url "<hosted-responses-endpoint>" --auth
```

After the hosted process restarts, the CUI retrieves the same stored response,
resumes after its last SSE cursor, and restores the graph from its Foundry
checkpoint.

## Protocol reference

### Create and retrieve a response

Choose the response ID before create and reuse it for all recovery requests:

```bash
curl -N -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -H "x-agent-response-id: <response-id>" \
  -d '{
    "input": "Book a two-night trip to Paris",
    "conversation": "trip-demo",
    "background": true,
    "stream": true,
    "store": true
  }'
```

Retrieve the stored response by that same ID:

```bash
curl "http://127.0.0.1:8088/responses/<response-id>"
```

### Approve the booking

The first turn completes with an `mcp_approval_request`. Use its `id` in the
next response, keep the same conversation, and link the completed turn with
`previous_response_id`:

```bash
curl -N -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -H "x-agent-response-id: <next-response-id>" \
  -d '{
    "input": [{
      "type": "mcp_approval_response",
      "approval_request_id": "<approval-request-id>",
      "approve": true
    }],
    "conversation": "trip-demo",
    "previous_response_id": "<response-id>",
    "background": true,
    "stream": true,
    "store": true
  }'
```

The sample CUI constructs both approval and denial responses automatically.

### Cancel a response

```bash
curl -X POST "http://127.0.0.1:8088/responses/<response-id>/cancel"
```

Cancellation stops future work but does not roll back completed checkpoints or
external effects.

## Recovery contract

### Client behavior

| Condition                                                                   | Required action                                                                                  |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Connection failure, SSE termination without a terminal event, or HTTP `5xx` | Retrieve the same stable response ID until it becomes terminal or the reconnect timeout expires. |
| Retrieval returns `404` before create was admitted                          | Retry create with the same response ID. Never generate a replacement ID.                         |
| Other HTTP `4xx` or an explicit terminal protocol event                     | Treat the result as final; do not retry it.                                                      |
| Starting the next turn                                                      | Reuse the conversation ID and send the latest response ID as `previous_response_id`.             |

Resilient Responses must use `background=true` and `store=true`. This sample
also uses `stream=true` so the client can replay events after its last received
`sequence_number`. Conversation history is linear; the integration does not
fork an older response into a second branch.

### Graph and handler behavior

- Compile the graph with a durable checkpointer that survives process
  replacement and is accessible to every recovering host instance.
- Keep durable workflow data in LangGraph state. Process memory, local caches,
  active HTTP requests, `ResponseContext`, and cancellation events are
  transient.
- Make nodes replay-safe. A crash between the LangGraph checkpoint and the
  paired Responses checkpoint can execute the last node again.
- Make external side effects idempotent, or deduplicate them with a stable
  operation key. At-least-once execution applies to writes, payments, email,
  queue publication, and other mutating tool calls.
- Keep checkpointed state serializable and compatible across deployments.

Before using this pattern in production, crash-test every node boundary and
both sides of each external side effect. Review the checkpoint retention period
and use durable stores for any additional application state.

## Configuration

| Variable                         | Default          | Purpose                                                                                |
| -------------------------------- | ---------------- | -------------------------------------------------------------------------------------- |
| `PORT`                           | `8088`           | HTTP port for the agent host.                                                          |
| `AGENTSERVER_STATE_ROOT`         | `~/.agentserver` | Local durable task, response, replay-stream, and LangGraph checkpoint state.           |
| `FOUNDRY_PROJECT_ENDPOINT`       | None             | Required Foundry project endpoint.                                                     |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | None             | Required Foundry model deployment name.                                                |

Hosted checkpoint items use Foundry State Store's default 30-day sliding TTL.
Local checkpoints remain beneath `${AGENTSERVER_STATE_ROOT}/state_stores`.

## Deploying the Agent to Foundry

See the [parent deployment guide](../../../README.md#deploying-the-agent-to-foundry)
for the common hosted-agent workflow. This directory is an independent `azd`
project. Its [azure.yaml](azure.yaml) defines both regular and steerable
Responses services.

Install `azd` and authenticate:

```powershell
azd auth login
```

Create a local deployment configuration from the committed template:

```powershell
Copy-Item .\src\langchain-azure-resilient-responses\.env.example .\.env
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
azd env set --file .\src\langchain-azure-resilient-responses\.env
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
uv run --no-sync python client.py --url "https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>/endpoint/protocols/openai/responses?api-version=v1" --auth
```
