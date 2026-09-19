---
description: Replace all four Foundry hosting storage extension points with custom Redis implementations
ms.date: 2026-09-11
ms.topic: sample
---

# Bring Your Own Store (Responses Protocol)

`ResponsesHostServer` persists agent state through four storage extension
points, each backed by a Foundry native store by default:

| Extension point                   | Purpose                                        |
|-----------------------------------|------------------------------------------------|
| `store`                           | Responses transcript and history               |
| `agent_session_store_provider`    | Agent Framework agent session snapshots        |
| `checkpoint_store_provider`       | Workflow checkpoints, scoped to one context    |
| `function_approval_store_provider`| Human-in-the-loop function approval requests   |

This sample replaces all four defaults with stores that you own and manage. It
uses [Redis](https://redis.io/) as a single, networked backend so the extension
points and their contracts stay in focus while the state survives restarts and
can be shared across multiple agent instances. You can use the same extension
points to integrate another storage backend that meets your data ownership,
retention, compliance, or application integration requirements.

Local development runs against a [Docker](https://www.docker.com/) Redis
container. Deployment provisions [Azure Managed Redis](https://learn.microsoft.com/azure/redis/)
through a layered Bicep stage. An `azd` post-deployment hook adds the deployed
agent identity to the Redis access policy, enabling passwordless authentication.

## What this sample demonstrates

The sample implements each hosting storage contract against Redis:

* `RedisResponseStore` implements `ResponseProviderProtocol` and persists
  response envelopes, transcript items, previous-response history chains, and
  conversation indexes with a configurable retention TTL.
* `RedisAgentSessionStore` implements `SessionStore` for agent session
  snapshots.
* `RedisCheckpointStore` implements `CheckpointStorage` for workflow
  checkpoints, scoped to one workflow context.
* `RedisFunctionApprovalStore` implements `FunctionApprovalStore` for function
  approval requests.

All four stores share one Redis instance, each owns its own key prefix, and
partitions every key by a hash of the Foundry-provided user ID so one caller
cannot read another caller's state.

## How it works

[main.py](src/agent-framework-agent-custom-store-responses/main.py) creates one
shared Redis client and passes the response store plus the three store providers
to `ResponsesHostServer`:

```python
database = create_database()

server = ResponsesHostServer(
    agent,
    store=create_response_store(database),
    agent_session_store_provider=RedisAgentSessionStoreProvider(database),
    checkpoint_store_provider=RedisCheckpointStoreProvider(database),
    function_approval_store_provider=RedisFunctionApprovalStoreProvider(database),
)
```

The `store` argument takes a store instance directly. The three providers return
a per-request store so each request is partitioned by its own user identity. The
checkpoint provider is context-scoped: it also receives the workflow context ID
so checkpoints for one workflow run can be listed and pruned as a collection.

The storage implementation uses
[redis_database.py](src/agent-framework-agent-custom-store-responses/redis_database.py)
to manage one shared asynchronous Redis client, apply a common prefix to every
key, and serialize read-modify-write operations with a write lock. During local
development, the client connects to the Docker Redis instance without
authentication. When deployed, it connects to Azure Managed Redis over TLS and
uses `DefaultAzureCredential` to authenticate with the agent's managed identity.

[redis_response_store.py](src/agent-framework-agent-custom-store-responses/redis_response_store.py)
implements the Responses storage contract, while
[redis_state_stores.py](src/agent-framework-agent-custom-store-responses/redis_state_stores.py)
implements the agent session, workflow checkpoint, and function approval
contracts. Response envelopes and transcript items use native Redis key TTLs,
allowing Redis to remove expired state without a separate cleanup process.

The agent keeps `default_options={"store": False}` because the Responses host
supplies the complete transcript to the model for every turn. This model-client
option is separate from the custom stores configured on the host.

Three local tools provide deterministic validation scenarios:

* `inspect_custom_store` reports per-user key counts for all four stores.
* `validate_checkpoint_store` runs a small Agent Framework workflow, persists
   its checkpoints through `RedisCheckpointStoreProvider`, and loads the last
   checkpoint before returning success.
* `approve_incident_change` requires human approval. The host persists the
   approval request before resuming the tool call from the approval response.

> [!NOTE]
> Redis stores state on a networked service that is shared across every agent
> instance, so conversation continuity and approvals survive restarts and scale
> horizontally. The local Docker Redis is ephemeral by design; the deployed
> Azure Managed Redis is durable.

## Prerequisites

1. Python 3.10 or later. The `azd ai agent run` path uses Python 3.13.
2. A Foundry project with a deployed chat model, or permission to create both
   through `azd provision`.
3. The Foundry User role on the Foundry project for the local or hosted identity.
4. Permission to assign an Azure Managed Redis data access policy during the
   `azd deploy` post-deployment hook, so the deployed agent identity can reach
   Redis without a password or access key.
5. [Docker](https://www.docker.com/) for the local Redis container. Deployment
   provisions Azure Managed Redis instead and requires no local Redis.

The `redis` and `redis-entraid` clients are installed from `requirements.txt`.

## Option 1: Azure Developer CLI

### Install prerequisites

1. Install the [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd).
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
mkdir my-custom-store-agent && cd my-custom-store-agent
azd ai agent init . -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/23-custom-store/azure.yaml
```

Follow the prompts to select or create a Foundry project and model deployment.

### Provision Foundry resources

Provision the resources declared in [azure.yaml](azure.yaml) before the first
deployment, even if the selected project and model deployment already exist.
This runs the `redis` Bicep layer, which provisions Azure Managed Redis:

```bash
azd provision
```

### Run locally

Start a local Redis with Docker from the sample root:

```bash
docker compose up -d
```

Change to the generated service directory, which contains `main.py`. Copy
`.env.example` to `.env`, set the Foundry endpoint and model deployment, and
point `REDIS_URL` at the local Redis for direct `python main.py` runs:

```dotenv
FOUNDRY_PROJECT_ENDPOINT="https://<your-foundry-resource>.services.ai.azure.com/api/projects/<your-project-name>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"

REDIS_URL=redis://localhost:6379/0
LOCAL_STORE_USER_ID=local-developer
REDIS_RESPONSE_TTL_SECONDS=86400
```

To run through `azd`, run the agent from the initialized project root:

```bash
azd ai agent run
```

The Responses endpoint listens on `http://localhost:8088/responses`. Keys are
written to Redis under the `custom-store:` prefix on the first request.

### Verify conversation continuity

Send an initial request, then continue from its response ID:

```powershell
$first = Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -ContentType "application/json" -Body '{"input":"Remember that incident INC-2048 affects the dispatch API."}'
$body = @{ input = "Which API is affected?"; previous_response_id = $first.id } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -ContentType "application/json" -Body $body
```

The second response identifies the dispatch API. Stop and restart the agent host,
then send the follow-up with the same response ID. The context remains available
in Redis until its TTL expires.

### Validate all four custom stores

Use these prompts in Agent Inspector or with `azd ai agent invoke`. Run them in
order so the final prompt can confirm that every store contains data:

1. `Remember marker INC-2301 for my next message.`
2. `Recall my marker, then call inspect_custom_store and include its result verbatim.`
3. `Call validate_checkpoint_store with marker CHK-2301 and include its result verbatim.`
4. `Call approve_incident_change with change_id CHG-2301 and include its result verbatim after approval.`
5. `Call inspect_custom_store and include its result verbatim.`

The first two prompts exercise agent-session persistence and confirm that the
Responses store contains response records. The third runs a real checkpointed
workflow against the checkpoint provider. The fourth creates and reloads an
approval request through the Responses continuation flow. Approve that request
when Agent Inspector asks. The final result has this shape, with positive counts
for every provider:

```text
STORE_COUNTS response_store=4 agent_session_store=4 checkpoint_store=2 function_approval_store=1
```

Counts can differ because a workflow may create more than one checkpoint and
the host writes response and session records for each turn.

### Inspect the Redis data

Connect to the local Redis with `redis-cli` to list the stored keys and read a
value:

```bash
docker exec -it <container-id> sh    #or /bin/bash
redis-cli --scan --pattern "custom-store:*"  # Run this command from inside the container
```

Each store owns a distinct key prefix: `custom-store:resp:` for responses,
`custom-store:session:` for agent sessions, `custom-store:ckpt:` for workflow
checkpoints, and `custom-store:approval:` for function approvals.

### Deploy

Provision Azure Managed Redis, then deploy the agent with its store
configuration:

```bash
azd provision
azd deploy
```

`azd deploy` deploys the agent but does not run the infrastructure layers. After
the initial provisioning, use `azd deploy` by itself for code-only updates. The
`redis` Bicep layer enables public network access, disables access-key
authentication, and exports the Azure Managed Redis host and port as the
`REDIS_HOST` and `REDIS_PORT` outputs, which `azure.yaml` injects into the
deployed agent. Direct local runs continue to use the Docker Redis from `.env`.
After deployment, the `postdeploy` hook assigns the built-in Redis `default`
access policy to the deployed agent identity.
Invoke the deployed agent twice to verify continuation:

```bash
azd ai agent invoke "Remember that incident INC-2048 affects the dispatch API."
azd ai agent invoke "Which API is affected?"
```

> [!NOTE]
> The deployed agent authenticates to Azure Managed Redis without a password or
> access key. After deployment, the `postdeploy` hook assigns the built-in
> `default` Redis access policy to the deployed agent identity. At runtime,
> `DefaultAzureCredential` and `redis-entraid` use that identity to obtain a
> Redis data-plane token. The agent configuration contains only the Redis host
> and port, not a connection secret. This sample deploys Azure Managed Redis
> with public network access enabled for demonstration purposes only. For
> production workloads, configure virtual network integration and private
> endpoints to restrict network access.

## Option 2: VS Code

### Install VS Code prerequisites

1. Install VS Code and the
   [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
   extension.
2. Install the
   [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python).

### Set up the Python environment

Open the service directory in VS Code. Create a `.venv`, then install the
dependencies:

```bash
pip install uv
uv pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure the Foundry endpoint, model
deployment, and store settings. Start a local Redis before running the agent:

```bash
docker compose up -d
```

### Run and debug the agent

Press **F5** to start the agent and open Agent Inspector. You can also run
`python main.py`, open **Foundry Toolkit: Open Agent Inspector** from the Command
Palette, and connect to port `8088`.

To deploy, run **Foundry Toolkit: Deploy Hosted Agent** from the Command Palette
and select the project described by [azure.yaml](azure.yaml).

## Troubleshooting

### A previous response is not found

Confirm that the follow-up uses the exact `id` returned by the first response,
that both requests use the same hosted user identity, and that the TTL has not
expired. Read operations do not extend retention.

### The agent cannot connect to Redis

For local runs, confirm `REDIS_URL` is set, start the Docker Redis with
`docker compose up -d`, and verify it is reachable with
`docker compose exec redis redis-cli ping`. For deployed runs, confirm
`azd provision` completed the `redis` layer and that `REDIS_HOST` is present in
the azd environment. Authentication failures usually mean the deployed agent
identity is missing its Redis access policy assignment; re-run `azd deploy` to
rerun the `postdeploy` hook.

### State is missing after the local container restarts

The local Docker Redis in `docker-compose.yml` keeps data in memory only, so
stopping the container clears all state. The deployed Azure Managed Redis is
durable and shared across agent instances.

## Next steps

* [Quickstart: Create a hosted agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
* [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
