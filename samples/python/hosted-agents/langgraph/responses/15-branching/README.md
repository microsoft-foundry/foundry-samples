# What this sample demonstrates

A checkpointed `create_agent` graph hosted as the **Responses protocol**
with `enable_response_branching=True`. Clients use `previous_response_id`
to demonstrate branching, rewind, and regeneration with a remembered
number instead of continuing from the latest checkpoint in the thread.

## How It Works

### Model Integration

The agent uses `langchain_openai.ChatOpenAI` with an Azure bearer token
provider from `DefaultAzureCredential` and an OpenAI-compatible endpoint
from `azure.ai.projects.AIProjectClient`.

See [main.py](src/langgraph-branching/main.py) for the full implementation.

### Branching, rewind, and regeneration

The [client](src/langgraph-branching/client.py) asks the agent to remember 10, creates branches B
and C from A, then returns to B after C.

#### Call sequence

Requests are sent in this order: `A -> B -> C -> D -> E -> F`.

#### Branch relationships

Nodes appear from top to bottom in call order. Connecting arrows show
parent-child relationships, not the next call:

```text
A: remember 10 -> 10
|
+----------------------> B: add 1 -> 11
|                        |
+--> C: add 2 -> 12      |
|                        |
|                        `--> D: recall -> 11
|                             |
|                             `--> E: add 1 -> 12
|
`--> F: add 1 -> 11
```

- **Branching:** B and C both select A, so adding 2 produces 12, not 13.
- **Rewind and continuation:** After C is created, D selects B and recalls
  11. E then selects D and adds 1 to get 12, demonstrating that B's branch
  remains usable without incorporating C's update. Existing branches are
  not deleted or modified.
- **Regeneration:** F repeats B's input with the same parent A, not B.
  It returns a new response ID. The answer is intentionally still 11;
  regeneration does not guarantee different output text.

All these operations use `previous_response_id`; there are no separate
rewind or regenerate endpoints. Every request creates a new response.
Keep its ID to select that version later. Reusing A never overwrites A.

### Responses hosting

Pass a history-preserving checkpointer to the graph and enable branching
on the host:

```python
graph = create_agent(model, tools=[], checkpointer=checkpointer)
await ResponsesHostServer(graph, enable_response_branching=True).run_async(
    port=8088
)
```

The host restores the exact graph checkpoint saved for the selected
parent response. The client supplies only the new input and the parent
response ID, not the full conversation history or LangGraph checkpoint IDs.

Local runs use `MemorySaver`; Foundry-hosted runs use
`FoundryCheckpointSaver`. Restarting the local process loses its graph
checkpoints, so start a new root response after a restart. Hosted runs
keep graph checkpoints in Foundry State Store.

### Requirements and limits

- Branching is opt-in and disabled by default.
- The parent response must be completed and have a readable saved
  checkpoint. Its graph must also have finished: branching from a paused
  graph or a pending human approval is not supported.
- A response must be created with `store=true` (the default) to be reused
  through `previous_response_id`. The client sets this explicitly; the curl
  examples rely on the default. A response created with `store=false` cannot
  be used as a later branch point.
- The checkpointer must preserve history and implement asynchronous
  `aget_tuple`, `aput`, and `aput_writes`. Both savers used here support them.
- Leave `steerable_conversations` disabled and let `ResponsesHostServer`
  create its own host; branching does not support an external `app`.
- Use `previous_response_id` alone for linkage in this sample. Do not send
  `conversation` in the same request.
- This sample demonstrates foreground branching. Recovery is also supported
  for forked requests when resilient background execution and persistent
  storage are configured. See the [resilient sample](../09-resilient/README.md)
  for background recovery setup.

## Running the Agent Host

This sample uses `uv` and Python 3.13 for the hosted runtime. From this
sample's directory:

```bash
cd src/langgraph-branching
uv sync --frozen --python 3.13
cp .env.example .env
```

Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`
to your existing Foundry project and model deployment, using
[.env.example](src/langgraph-branching/.env.example) as a reference.
Authenticate with Azure CLI before starting the host:

```bash
az login
uv run --frozen main.py
```

### Run with azd

Use `azd` with the Foundry extension. From this sample's root directory,
create an environment bound to your existing project and model deployment:

```bash
azd env new branching-demo --subscription <subscription-id> --location <project-region>
azd env set AZURE_AI_PROJECT_ID "<project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4.1-mini
uv run --project src/langgraph-branching --frozen azd ai agent run --no-client
```

Use the same project endpoint and model deployment in
`src/langgraph-branching/.env`. `--no-client` starts only the host so the
branching client below can send its six requests. Add `--port 8090` if port
8088 is already in use.

## Interacting with the agent

### Run the number example

In another terminal, from `src/langgraph-branching`, run:

```bash
uv run --frozen client.py
```

The client sends six non-streaming requests and prints assistant reply.
The expected numbers are `10`, `11`, `12`, `11`, `12`, `11`.

For a different host address or port:

```bash
uv run --frozen client.py --base-url http://127.0.0.1:8090
```

### Raw Responses requests

Create the shared parent A:

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Remember the number 10."}'
```

Replace `<A_ID>` below with the returned `id`. Both requests select A,
not each other's response IDs:

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Add 1 to the remembered number.","previous_response_id":"<A_ID>"}'

curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Add 2 to the remembered number.","previous_response_id":"<A_ID>"}'
```

Keep B's returned `id` as `<B_ID>`. After creating C, select B again (D),
then use D's returned `id` as `<D_ID>` to continue it (E):

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"What number do you remember?","previous_response_id":"<B_ID>"}'

curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Add 1 to the remembered number.","previous_response_id":"<D_ID>"}'
```

Regenerate B by resending its original input with the same parent A (F):

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Add 1 to the remembered number.","previous_response_id":"<A_ID>"}'
```

### Streaming

Branch selection works the same way with `"stream": true`. For the raw
requests above, add that field to the body and use `curl -N` to read SSE
events, including `response.output_text.delta` and `response.completed`.

## Deploying the Agent to Foundry

Complete the dependency installation and azd environment setup above,
then deploy from the sample's root directory:

```bash
azd deploy
azd ai agent show
```

The [azure.yaml](azure.yaml) uses direct-code deployment with Python 3.13
and remote dependency resolution; Docker and a container registry are not
required. Runtime dependencies are declared in
[pyproject.toml](src/langgraph-branching/pyproject.toml) and fully pinned in
[uv.lock](src/langgraph-branching/uv.lock) for reproducible installation.
[.agentignore](src/langgraph-branching/.agentignore) excludes local credentials,
virtual environments, and azd state from the runtime package. The agent declares
Responses protocol `2.0.0` for deployment routing and Foundry state-store request
context. No `azd provision` is needed when reusing an existing project and model.

Use the deployed agent's OpenAI protocol base URL, without `/responses`
or the query string. From `src/langgraph-branching`, run:

```bash
uv run --frozen client.py --azure --base-url "https://<resource>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>/endpoint/protocols/openai"
```

`--azure` obtains a token with `DefaultAzureCredential` and adds
`api-version=v1`. The client sends the same A/B/C/D/E/F requests as the local
example, using `FoundryCheckpointSaver` on the hosted agent. See the
[deployment guide](../../README.md#deploying-the-agent-to-foundry) for
Foundry prerequisites.
