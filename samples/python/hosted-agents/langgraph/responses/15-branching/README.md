# What this sample demonstrates

A checkpointed `create_agent` graph hosted as the **Responses protocol**
with `enable_response_branching=True`. Clients use `previous_response_id`
to demonstrate branching, rewind, and regeneration with a remembered
number instead of continuing from the latest checkpoint in the thread.

## How it works

### Model Integration

The agent uses `langchain_openai.ChatOpenAI` with an Azure bearer token
provider from `DefaultAzureCredential` and an OpenAI-compatible endpoint
from `azure.ai.projects.AIProjectClient`.

See [main.py](src/langgraph-branching/main.py) for the full implementation.

### Branching, rewind, and regeneration

The [client](src/langgraph-branching/client.py) asks the agent to remember 10,
creates branches B and C from A, then returns to B after C.

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

## Prerequisites

- An existing Microsoft Foundry project with a deployed chat model. This
  sample reuses that project and model; it does not provision them.
- **Python 3.13** and **[uv 0.11.7](https://docs.astral.sh/uv/getting-started/installation/)**,
  matching the hosted runtime and dependency-policy tooling.
- The project's HTTPS endpoint, its full ARM resource ID for deployment, and
  the model's **deployment name**. This sample uses `gpt-5.4-mini` throughout;
  ensure that deployment exists in your project.
- An Azure identity with model-inference access for local runs. Deploying
  additionally requires permission to create hosted agents and versions;
  invoking a deployed agent requires agent-invocation permission. See the
  [hosted-agent permissions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-permissions).

## Option 1: Azure Developer CLI (`azd`)

### Set up the tools

Install [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
and [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then
install the Foundry extension and sign in:

```bash
azd ext install microsoft.foundry
azd auth login
az login
```

`azd auth login` authenticates deployment tooling. The local Python host and
the deployed-agent client use `DefaultAzureCredential`, which can use the
Azure CLI identity from `az login`.

### Configure the existing project

From this sample's root directory, containing `azure.yaml`, install the
locked Python environment and configure an azd environment:

```bash
uv sync --project src/langgraph-branching --frozen --python 3.13
cp src/langgraph-branching/.env.example src/langgraph-branching/.env
azd env new branching-demo --subscription <subscription-id> --location <project-region>
azd env set AZURE_AI_PROJECT_ID "<project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "gpt-5.4-mini"
```

The project resource ID is the full ARM ID, ending in
`/providers/Microsoft.CognitiveServices/accounts/<resource>/projects/<project>`;
it is not the HTTPS endpoint. In `src/langgraph-branching/.env`, replace the
endpoint placeholder and keep `AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4-mini`,
matching the azd environment above.
No `azd provision` is needed when reusing the existing project and model.

### Run the agent locally

From the sample's root directory:

```bash
uv run --project src/langgraph-branching --frozen azd ai agent run --no-client
```

The host listens on `http://localhost:8088`. `--no-client` starts only the
host so the branching client can send its requests. Add `--port 8090` if
port 8088 is already in use.

### Invoke the local agent

In another terminal, from the sample's root directory:

```bash
uv run --directory src/langgraph-branching --frozen client.py
```

See the [number example](#run-the-number-example) for the expected results
and a custom host address.

### Deploy to Foundry

After testing locally, run from the sample's root directory:

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
context.

### Invoke the deployed agent

Use the deployed agent's OpenAI protocol base URL, without `/responses`
or the query string. From the sample's root directory:

```bash
uv run --directory src/langgraph-branching --frozen client.py --azure --base-url "https://<resource>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>/endpoint/protocols/openai"
```

`--azure` obtains a token with `DefaultAzureCredential` and adds
`api-version=v1`. The client sends the same A/B/C/D/E/F requests as the local
example, using `FoundryCheckpointSaver` on the hosted agent. See the
[deployment guide](../../README.md#deploying-the-agent-to-foundry) for
Foundry prerequisites.

## Option 2: VS Code (Foundry Toolkit)

### Set up the environment

Install [VS Code](https://code.visualstudio.com/), the
[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio),
the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python),
and [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
Open this sample's root folder as the VS Code workspace.

From the VS Code terminal:

```bash
cd src/langgraph-branching
uv sync --frozen --python 3.13
cp .env.example .env
az login
```

Set `FOUNDRY_PROJECT_ENDPOINT` in `.env` to your existing project endpoint
and keep `AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4-mini`. Use
[.env.example](src/langgraph-branching/.env.example) as a reference and keep
`.env` local. Select the source directory's `.venv` interpreter in VS Code.

### Run locally and open the Inspector

From `src/langgraph-branching`:

```bash
uv run --frozen main.py
```

The host listens on `http://localhost:8088`. Open the Command Palette and
run **Foundry Toolkit: Open Agent Inspector** to interact with it. Use the
[number example](#run-the-number-example) for the complete branching,
rewind, and regeneration flow.

For **F5** debugging, first generate local launch and task configuration
for this existing project with the
[Toolkit's Copilot configuration tools](https://code.visualstudio.com/docs/intelligentapps/copilot-tools#generate-and-test-agent-code).
That optional generation path requires GitHub Copilot Chat access. Review
the generated entry point (`src/langgraph-branching/main.py`), source working
directory, `.venv` interpreter, and `.env` file before pressing F5. Cloning
the sample does not create these debug files; keep generated `.vscode`
configuration local.

### Deploy with Foundry Toolkit

1. Open the Command Palette and run **Foundry Toolkit: Deploy Hosted Agent**.
2. Select your existing Foundry project and choose **Code** deployment.
3. Confirm the source directory, Python 3.13 runtime, `main.py` entry point,
  and `gpt-5.4-mini` model deployment name before deploying.

Use the [deployed-agent client](#invoke-the-deployed-agent) to run the
branching example against the resulting endpoint.

## Interacting with the agent

### Run the number example

In another terminal, from `src/langgraph-branching`, run:

```bash
uv run --frozen client.py
```

The client sends six non-streaming requests and prints the assistant replies.
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

## Troubleshooting

- **Model deployment not found:** verify that `gpt-5.4-mini` is deployed in
  your Foundry project and matches both the source `.env` and azd environment.
  Existing environment variables take precedence over values loaded from `.env`.
- **Authentication or permission errors:** sign in with `az login` for the
  Python host/client and `azd auth login` for deployment, using identities
  with the permissions required for that operation.
- **A local parent response cannot be reused after a restart:** `MemorySaver`
  loses graph checkpoints when the process exits. Run the number example
  again to create a fresh root response.

## Next steps

- [Resilient execution sample](../09-resilient/README.md)
- [Hosted-agent deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
