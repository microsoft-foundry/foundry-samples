# LangGraph Deep Research Agent

This sample adapts LangChain's official [Build a deep research agent](https://docs.langchain.com/oss/python/deepagents/deep-research) tutorial to Microsoft Foundry hosting. The research workflow follows the tutorial, while the model, web search, durable checkpointing, and Responses protocol server use Microsoft Foundry.

## What the sample demonstrates

- Planning research with `TodoListMiddleware` and state-backed files.
- Delegating focused topics to a single `research-agent` subagent type.
- Discovering current sources with the managed `web_search` tool in a Foundry Toolbox.
- Producing a structured report with consolidated inline citations.
- Hosting the compiled Deep Agents graph through `ResponsesHostServer`.
- Persisting LangGraph checkpoints with `FoundryCheckpointSaver`.

## How it works

The coordinator saves the request to `/research_request.md`, plans the work, and delegates research instead of searching directly. Research subagents use the tutorial's bounded search loop: two or three searches for simple questions and at most five for complex questions. The coordinator consolidates their citations, writes `/final_report.md`, and verifies that the report covers the original request.

The agent uses a model deployed in the Foundry project. Its coordinator and research subagent share all tools loaded from the `deep-agents-tools` Toolbox. The Toolbox is declared as an `azure.ai.toolbox` service in `azure.yaml`, and the hosted agent lists it under `uses`, so `azd` deploys the Toolbox before the agent.

## Project structure

The application follows the official Deep Research example's modular structure:

```text
src/langgraph-deep-agents/
├── main.py
├── agent.py
├── utils.py
└── research_agent/
    ├── __init__.py
    ├── prompts.py
    └── tools.py
```

- `main.py` owns only the Foundry checkpoint and Responses server lifecycle.
- `agent.py` composes the coordinator, research subagent, and planning middleware.
- `utils.py` constructs the Foundry-backed chat model.
- `research_agent/prompts.py` contains the research workflow and delegation instructions.
- `research_agent/tools.py` loads the tools exposed by the Foundry Toolbox.

The extra `main.py` is the hosting adaptation that starts the Foundry Responses server. The remaining layout mirrors the official example directly within the hosted agent's source folder.

## Prerequisites

1. Install the [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd).
2. Install the Foundry agent extension with `azd extension install azure.ai.agents`.
3. Authenticate with `azd auth login`.

## Initialize and provision

```bash
mkdir hosted-langgraph-deep-agent && cd hosted-langgraph-deep-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/11-deep-agents/azure.yaml
azd up
```

`azd up` provisions the Foundry project and model, then deploys the connection-free web-search Toolbox and hosted agent together. No external search API key is required.

## Run locally

```bash
azd ai agent run --no-client
```

In another terminal:

```bash
azd ai agent invoke --local "Compare the latest approaches to small language models on consumer devices."
```

The local server also accepts Responses requests at `http://localhost:8088/responses`.

## Deploy

```bash
azd deploy
azd ai agent invoke "Research recent advances in small language models."
```

See [Microsoft Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent) for the complete deployment workflow.

## Debug in VS Code

Open this sample folder in VS Code, run `uv sync --frozen` from `src/langgraph-deep-agents`, select `src/langgraph-deep-agents/.venv` as the Python interpreter, and create `.env` from `.env.example`. Press **F5** to start the server under `debugpy` and open Foundry Toolkit Agent Inspector.