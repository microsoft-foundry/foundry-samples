# Coding Agent Instructions - LangGraph branching

This sample is a Microsoft Foundry hosted LangGraph agent using the Responses
protocol. It demonstrates branching, rewind, and regeneration with
`previous_response_id` and a checkpointed number-memory graph.

## Deployment mode

The sample uses direct code deployment. `azure.yaml` declares Python 3.13,
`main.py` as the entry point, and `src/langgraph-branching` as the runtime project.
The Dockerfile is an optional container build path.

## Key files

- `azure.yaml` - hosted-agent service, runtime, environment, and resources
- `src/langgraph-branching/main.py` - graph and Responses host
- `src/langgraph-branching/client.py` - branching, rewind, and regeneration demo
- `src/langgraph-branching/pyproject.toml` and `uv.lock` - runtime dependencies
- `src/langgraph-branching/uv.toml` - uv certificate and prerelease settings
- `README.md` - local run, client, and deployment instructions

## Dependency workflow

Follow the shared [Python Hosted Agent dependency policy](../../../DEPENDENCY_POLICY.md).
Use `uv sync --frozen --python 3.13` and `uv run --frozen` from `src/langgraph-branching`.
When dependency inputs change, regenerate `uv.lock` and run the dependency
policy checker with `--resolve`. Preserve existing versions during unrelated work.

## Branching behavior

Keep `enable_response_branching=True` and a history-preserving checkpointer.
Local runs use `MemorySaver`; hosted runs use `FoundryCheckpointSaver`.
The client sends only new input and `previous_response_id`, with `store=True`.
Preserve the documented branch relationships and expected remembered numbers.

## Microsoft Foundry Skill

This project was built with the microsoft-foundry skill. Before working on or
answering questions about foundry agents, read the microsoft-foundry skill first.
If you are in VS Code, read the vscode-microsoft-foundry skill first.
