# What this sample demonstrates

A minimal [LangGraph](https://langchain-ai.github.io/langgraph/) agent
built with `langchain.agents.create_agent` and hosted using the
**Responses protocol**. It uses the configuration-driven
`langchain_azure_ai.agents.hosting.run` entrypoint instead of constructing
a `ResponsesHostServer` in application code.

> **No agent code changes are required to migrate an existing LangChain
> agent to this approach.** Keep the existing graph implementation as-is,
> point `langgraph.json` at its exported graph, and launch the hosting
> entrypoint with the desired protocol.

## How It Works

### Graph and model integration

The agent uses `langchain_openai.ChatOpenAI` with an Azure bearer token
provider from `DefaultAzureCredential` and an OpenAI-compatible endpoint
from `azure.ai.projects.AIProjectClient` (`az login` is enough for local
development). The graph is the same no-tool `create_agent` graph used by
other minimal LangGraph samples in this repo.

See [src/langgraph-run-responses/main.py](src/langgraph-run-responses/main.py)
for the graph and [src/langgraph-run-responses/langgraph.json](src/langgraph-run-responses/langgraph.json)
for its entrypoint configuration.

### Migrating an Existing Agent

An existing LangChain agent that exports a compiled graph does not need a
hosting wrapper, a `ResponsesHostServer` import, or a new `main()` function.
Add a `langgraph.json` file that references the existing graph symbol, then
use the command shown below. The agent's model, tools, prompts, state, and
graph code remain unchanged.

### Agent Hosting

The `langgraph.json` file maps the `agent` name to the compiled graph in
`main.py`. The hosting entrypoint loads that graph and exposes it through
the protocol selected by the required `--protocol` argument. This sample
selects `responses` in both its local command and Docker image.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
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
mkdir hosted-langgraph-agent && cd hosted-langgraph-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/10-run/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run --no-client
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, invoke the running agent:

```bash
azd ai agent invoke --local "Hello!"
```

Or invoke directly with curl:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "Hello!"}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. Install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack if you want to debug the sample locally.

### Set up the Python virtual environment

- Install uv if it is not already available:

  ```bash
  python -m pip install uv
  ```

- From the sample root, sync the committed environment:

  ```bash
  cd src/langgraph-run-responses
  uv sync --frozen
  ```

- In VS Code, select `src/langgraph-run-responses/.venv` as the Python interpreter.
### Run locally

```bash
cd src/langgraph-run-responses
uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses
```

Then invoke it:

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello!"}'
```

## Troubleshooting

### Azure OpenAI Permission Denied (401)

This sample calls the project's model endpoint through LangChain. The hosted agent's managed identity needs the **Foundry User** role on the project. Assign that role at the project scope and retry after role propagation completes.