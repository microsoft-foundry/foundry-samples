# Coding Agent Instructions

This project is a Microsoft Foundry hosted agent: a containerized LangGraph
agent that runs in Foundry Agent Service over the Invocations protocol.

## Key files

- `azure.yaml` - Foundry services and deployment configuration.
- `src/langchain-azure-resilient-invocations/main.py` - Agent graph, tools,
  checkpointing, and host startup.
- `src/langchain-azure-resilient-invocations/pyproject.toml` - Direct agent
  dependencies.
- `src/langchain-azure-resilient-invocations/uv.lock` - Locked dependency graph.
- `src/langchain-azure-resilient-invocations/Dockerfile` - Container definition.
- `client/` - Textual client for background invocation recovery, steering,
  cancellation, and human approval.

## Development workflow

Run `azd` commands from the sample root:

```bash
azd ai agent run --no-client
azd deploy
```

Run the Textual client in a separate terminal:

```bash
cd client
uv sync --frozen
uv run --no-sync python client.py
```

Keep external effects idempotent. A recovered LangGraph node can execute again
if the host stops between an external effect and its paired checkpoint.

## Microsoft Foundry Skill

Install the Microsoft Foundry Skill for guided deployment, evaluation, and
troubleshooting workflows:

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

Then ask your coding agent to use the Microsoft Foundry Skill to deploy or
troubleshoot this sample.

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)