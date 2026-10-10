# Coding Agent Instructions

This project is a **Microsoft Foundry hosted agent** built with LangGraph and the Responses protocol. It runs in [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) and uses the configuration-driven `langchain_azure_ai.agents.hosting.run` entrypoint.

## Key files

- `azure.yaml` - Foundry hosted-agent manifest
- `src/langgraph-run-responses/main.py` - exported LangGraph graph used by the hosting entrypoint
- `src/langgraph-run-responses/langgraph.json` - graph registry for the run command
- `src/langgraph-run-responses/pyproject.toml` - direct dependencies
- `src/langgraph-run-responses/uv.lock` - locked dependency graph

## Development workflow

```bash
azd ai agent run --no-client
azd ai agent invoke --local "your message"
azd deploy
azd ai agent invoke "your message"
```

## Microsoft Foundry Skill

This project was built with the microsoft-foundry skill. Before working on or answering questions about Foundry agents, read that skill first.

Install the skill with:

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
