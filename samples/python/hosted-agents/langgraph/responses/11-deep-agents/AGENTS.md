# Coding Agent Instructions

This project is a **Microsoft Foundry hosted agent** built with LangGraph Deep Agents. It runs in [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) and exposes the Responses protocol.

## Sample scope

Demonstrate the LangChain Azure SDK with LangChain, LangGraph, and Deep Agents,
not only a deployment wrapper. Reuse or adapt the selected SDK research example
while keeping its native graph, state, and tool extension points understandable.
Keep the platform configuration, identity permissions, deployment, and end-to-end
acceptance paths alongside the SDK example. See the collection's
[sample scope](../../README.md#sample-scope) for the two repositories' roles.

## Key files

- `azure.yaml` - Foundry hosted-agent manifest
- `src/langgraph-deep-agents/main.py` - Foundry Responses host entry point
- `src/langgraph-deep-agents/agent.py` - Deep Agents graph assembly
- `src/langgraph-deep-agents/report_export.py` - publish a saved named report to private Blob Storage
- `src/langgraph-deep-agents/client.py` - research, revise, and verify both downloads
- `src/langgraph-deep-agents/research_agent/prompts.py` - research workflow and subagent prompts
- `src/langgraph-deep-agents/research_agent/tools.py` - Foundry Toolbox loading
- `src/langgraph-deep-agents/pyproject.toml` - direct dependencies
- `src/langgraph-deep-agents/uv.lock` - locked dependency graph
- `src/langgraph-deep-agents/tests/` - offline workflow, publication, client, and lifecycle regressions

Document Storage permissions for the local developer and deployed agent separately,
following the manual RBAC pattern in the downstream Azure sample. Keep cloud
assertions within the existing test-spec schema; the demo client checks downloads.

## Development workflow

```bash
azd deploy --all
azd ai agent run --no-client
azd ai agent invoke --local "your message"
azd deploy --all
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
- [Build a deep research agent](https://docs.langchain.com/oss/python/deepagents/deep-research)
- [Foundry Toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
