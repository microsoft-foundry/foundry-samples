# Coding Agent Instructions - OpenAI Agents SDK support triage

This sample is a Microsoft Foundry hosted agent using OpenAI Agents SDK handoffs,
a read-only MCP server, and the Responses protocol. This project was built with
the microsoft-foundry skill. Before working on or answering questions about
Foundry agents, read the microsoft-foundry skill first.

## Deployment mode

`azure.yaml` uses direct code deployment with `codeConfiguration`. No Dockerfile
is required. Keep the service key and hosted-agent name aligned.

## Key files

- `azure.yaml` - Foundry project and hosted-agent manifest.
- `src/openai-agents-sdk-triage/main.py` - Responses host, SDK agents, and streaming.
- `src/openai-agents-sdk-triage/case_server.py` - fictional read-only MCP data.
- `src/openai-agents-sdk-triage/pyproject.toml` and `uv.lock` - pinned runtime dependencies.
- `src/openai-agents-sdk-triage/tests/test_triage.py` - local SDK/MCP integration tests.
- `README.md` - setup, examples, and deployment.

Do not commit Foundry Toolkit-generated `.vscode` files. Keep the MCP session,
SDK run, and model client request-scoped and clean them up on cancellation.
Do not replace failures with successful-looking assistant text.

## Dependency and test workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`. Update `uv.lock`
with dependency changes and run the policy checker with `--resolve`. Run
`uv run --no-sync python -m unittest discover -s tests -v` from the runtime
directory, and validate and plan the corresponding cloud test spec.

## Runtime logging

Use the standard `logging` module for runtime diagnostics. Sample-owned log
events record tool names and handoffs without logging case contents or tokens.

## Development workflow

Use `azd ai agent run`, `azd ai agent invoke --local`, and `azd deploy` as
described in the README. Provision only when a new project is needed.

## Microsoft Foundry Skill

Install the skill for deployment and troubleshooting:

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

See the [hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents).
