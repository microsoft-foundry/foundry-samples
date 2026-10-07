# What this sample demonstrates

This sample demonstrates how to implement and wire custom stores for a
LangGraph agent using the **Responses protocol**, so you control its state
persistence independently of Foundry-specific state services.

The same code runs in Foundry Hosted Agents or on-premises. Both targets call a
Foundry model using `AZURE_AI_API_KEY` when provided, or
`DefaultAzureCredential` otherwise.

## How custom stores are connected

- **Conversation-chain store:** Implement `ConversationChainStoreProtocol` and
  pass it to `ResponsesHostServer` as `conversation_chain_store`. See
  [the example implementation](src/custom-store/sqlite_conversation_chain_store.py).
- **Response store:** Implement `ResponseProviderProtocol` and pass it through
  the host's `store` argument to persist response records and items. See
  [the example implementation](src/custom-store/sqlite_response_store.py).
- **Graph checkpoints and long-term memory:** Pass compatible LangGraph
  implementations as `checkpointer` and `store` to `create_agent`. LangMem's
  `manage_memory` and `search_memory` tools use the long-term memory store.

[main.py](src/custom-store/main.py) shows how to connect these components and
manage their async lifetimes.

SQLite serves as a simple example backend for the custom-store pattern. Use any
storage backend that satisfies the contracts for on-prem deployments.

## Prerequisites

- **Python 3.13** for local development to match the hosted runtime declared in
  [azure.yaml](azure.yaml).
- **A Foundry project and model deployment.** Use an existing project, or create
  the resources during the Foundry-hosted setup below. On-premises runs use an
  existing Foundry model deployment.
- **Azure access.** For identity-based model access, use an identity with
  permission to invoke the model in the target project. For the Foundry-hosted
  path, the deploying identity also needs permission to provision the declared
  resources and deploy hosted agents.
- **Model configuration.** For manual local or on-premises runs, create
  `src/custom-store/.env` from [.env.example](src/custom-store/.env.example):

  | Variable | Required | Purpose |
  | --- | --- | --- |
  | `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. `AZURE_AI_PROJECT_ENDPOINT` is also accepted as a fallback. |
  | `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Name of the Foundry model deployment. |
  | `AZURE_AI_API_KEY` | No | API key for model authentication. When empty or absent, the agent uses `DefaultAzureCredential`. |

Install runtime dependencies from
[pyproject.toml](src/custom-store/pyproject.toml) and the committed
[uv.lock](src/custom-store/uv.lock).
Contributors updating dependencies should follow the
[Python Hosted Agent dependency policy](../../../DEPENDENCY_POLICY.md) and
regenerate the pinned artifact in the same change.

## Choose a deployment path

| Path | Agent runtime | Foundry services used |
| --- | --- | --- |
| [Foundry Hosted Agents](#option-1-foundry-hosted-agents) | Agent runs on Foundry with your chosen store implementations. | Foundry agent hosting and Foundry models. |
| [On-premises](#option-2-on-premises-with-foundry-models) | Agent runs on your infrastructure with your chosen store implementations. | Foundry models only. |

### Option 1: Foundry Hosted Agents

The sample uses **direct code deployment**:
[azure.yaml](azure.yaml) declares `codeConfiguration` with the Python 3.13
runtime and `main.py` entry point under `src/custom-store`. Foundry builds the
runtime from that source directory and its committed dependencies; a Dockerfile
is not required.

#### Azure Developer CLI (`azd`)

Install [Azure Developer CLI 1.27.1 or later](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
and the Foundry extension, then authenticate:

```bash
azd ext install microsoft.foundry
azd auth login
```

The manifest requires `azure.ai.agents` extension version `1.0.0-beta.9` or
later. To initialize a new workspace from the sample:

```bash
mkdir custom-store-agent
cd custom-store-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/13-custom-store/azure.yaml
```

Follow the prompts to select or create the Foundry project and model deployment.
When working from a repository checkout, use this sample's root directory
directly instead of initializing another workspace.

Provision the declared resources as needed, then run locally:

```bash
azd provision
azd ai agent run --no-client
```

The local endpoint is `http://localhost:8088`. From a second terminal in the
same project directory:

```bash
azd ai agent invoke --local "Remember that my project is ExampleProject."
```

Use the [store tests](#test-the-stores) for the sample's defining behaviors.
After local testing, deploy and invoke the hosted agent:

```bash
azd deploy
azd ai agent invoke "Remember that my project is ExampleProject."
```

The deployed agent uses managed identity through `DefaultAzureCredential` when
`AZURE_AI_API_KEY` is empty or absent. That identity must have permission to call
the Foundry model. This path supports keyless model access.

For identity-based local authentication, install
[Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and run
`az login`, or configure another identity available to `DefaultAzureCredential`,
before starting the agent. Use `azd auth login` for deployment operations and
configure the local agent's model authentication separately.

#### VS Code (Foundry Toolkit)

1. Install **VS Code**, the
   [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio),
   and the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python).
2. Open the sample root or the initialized workspace. Use **Python: Create
   Environment...** or **Python: Select Interpreter** to select Python 3.13.
   With that environment activated, install the runtime dependencies:

   ```bash
   cd src/custom-store
   uv sync --frozen
   ```

3. Configure the model connection described in [Prerequisites](#prerequisites).
   For identity-based local model access, run `az login` in the integrated
   terminal or configure another supported Azure identity.
4. In a Toolkit-scaffolded workspace, press **F5** to run the agent and open
   **Agent Inspector**. The Toolkit generates the local
   `.vscode/launch.json` and `.vscode/tasks.json` files for this flow; keep those
   generated files out of sample commits.

   Alternatively, run manually from the source directory:

   ```bash
   cd src/custom-store
   uv run --no-sync python main.py
   ```

   Then open the Command Palette and select **Foundry Toolkit: Open Agent
   Inspector** to send test messages to the local agent.
5. To deploy, run **Foundry Toolkit: Deploy Hosted Agent** from the Command
   Palette. Select the Foundry project, choose **Code** deployment, and confirm
   the runtime and entry point from the manifest. Review the settings and
   select **Deploy**.
6. Invoke the deployed agent in the Agent Playground and inspect its **Logs**
   tab.

### Option 2: On-premises with Foundry models

Run the agent on your own infrastructure and call an existing Foundry model
deployment. Model requests go to Foundry over the network, while the agent
runtime and its state stay on your infrastructure. Follow the local setup
below for this path; hosted-agent provisioning and deployment belong to
Option 1.

Create a virtual environment from the sample root:

```bash
cd src/custom-store
python -m pip install uv
uv sync --frozen
```

Configure `.env` in the source directory as described in
[Prerequisites](#prerequisites).

Choose one authentication method:

- **API key:** Set `AZURE_AI_API_KEY` to authenticate the agent's model calls
  directly with the key.
- **Azure identity:** Leave `AZURE_AI_API_KEY` empty or unset and authenticate
  with `az login` for an interactive local run, or configure another identity
  supported by `DefaultAzureCredential` for an unattended on-premises process.
  The identity must have permission to call the Foundry model.

Then start the agent from the source directory with the virtual environment
activated:

```bash
uv run --no-sync python main.py
```

## Test the stores

Run these checks against the local `/responses` endpoint with the server running
throughout.

### Conversation context and response history (`langchain_azure_ai.agents.hosting.ConversationChainStoreProtocol`, `azure.ai.agentserver.responses.ResponseProviderProtocol`)

1. Start a conversation with a fact that appears only in this turn:

   ```bash
   curl -X POST http://127.0.0.1:8088/responses \
     -H "Content-Type: application/json" \
     -d '{"input":"For this conversation only, the parcel code is MAPLE-5831. Keep it in conversation context only and reply OK directly."}'
   ```

   Save the response `id` as `<first-response-id>` for the follow-up request.

2. Continue from the first response using only the follow-up question. Replace
   `<first-response-id>` with the response ID generated in step 1:

   ```bash
   curl -X POST http://127.0.0.1:8088/responses \
     -H "Content-Type: application/json" \
     -d '{"previous_response_id":"<first-response-id>","input":"What is the parcel code from our earlier turn? Answer directly from conversation context only."}'
   ```

   Expect: an answer containing `MAPLE-5831`.

3. As a control, ask in a fresh conversation:

   ```bash
   curl -X POST http://127.0.0.1:8088/responses \
     -H "Content-Type: application/json" \
     -d '{"input":"What is the parcel code? Answer directly from this conversation only. If the code is missing from this conversation, say that it is unknown."}'
   ```

   Expect the agent to say that the code is unknown.

### Long-term memory across conversations (`langgraph.store.base.BaseStore`)

Send two requests in different conversations. This validates long-term memory with `AsyncSqliteStore`.

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Remember that my project is ExampleProject."}'

curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Search your saved memories. What is my project?"}'
```

Expect the first turn to call `manage_memory` and the second to call
`search_memory` and return `ExampleProject`. Unlike the context checks above, this
intentionally retrieves a saved fact in a different conversation.

## Limitations

The SQLite classes keep this sample small and make each store contract easy to
inspect. Consider the following limitations when choosing a production backend:

| Area | Example behavior |
| --- | --- |
| Concurrency | `SqliteResponseStore` serializes its writes with an in-process `asyncio.Lock`. SQLite still permits one writer at a time, and the sample does not add cross-process locking, connection pooling, busy retries, or load-shedding behavior. |
| Multiple replicas | Each process opens local database files. Replicas do not share state or coordinate writes, so requests routed to different replicas can observe different response, conversation, checkpoint, and memory state. |
| User isolation | The sample prioritizes simplicity and does not provide user-level data isolation. Use only non-sensitive demonstration data. |
| Transactions | Each response-store mutation wraps its response record and items in one SQLite transaction. Conversation-chain writes commit independently, and checkpoints, long-term memory, conversation chains, and responses use separate database files. An operation spanning those stores is not atomic and can leave partial state after a failure. |
| Availability and scale | The example has no replication, failover, distributed consistency, or high-throughput write strategy. Local files also tie state availability to the filesystem visible to that process. |
| Data lifecycle and security | The sample defines no retention, archival, backup, migration, or comprehensive cleanup policy. Data is stored without application-level encryption, so filesystem access controls protect the database files. |

For production, you should back the custom store implementation
with a more capable storage solutions, such as Azure Cosmos DB.

## Troubleshooting

- **Model configuration errors:** Check the project endpoint and deployment name
  in the source directory's `.env`. Use the deployment name configured in your
  Foundry project.
- **Azure credential errors:** For identity-based local runs, authenticate with
  `az login` or configure another `DefaultAzureCredential` identity. Confirm that
  the identity has model-invocation access to the selected project.
- **F5 configuration unavailable:** Use the manual run and Agent Inspector steps
  above, or let Foundry Toolkit scaffold the workspace's local debug files.

## Next steps

- Adapt the custom stores to a backend that satisfies the same contracts.
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Explore the other LangGraph samples](../../README.md)
