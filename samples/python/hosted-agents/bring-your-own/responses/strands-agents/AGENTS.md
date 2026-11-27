# Coding Agent Instructions - Strands Agents (Responses)

This sample is a **Microsoft Foundry hosted agent**. It is an AWS-to-Azure migration
assistant built with the Strands Agents SDK that combines agents-as-tools and the
Microsoft Learn MCP server over the Responses protocol. It runs in
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents),
which manages hosting, security, scaling, and observability so contributors can focus on
the agent logic.

## Deployment mode

- **Direct code deployment:** `codeConfiguration` declares the Python runtime and entry
  point. The Dockerfile is kept for local container runs and is not required.

## Key files

- `azure.yaml` - `azd` manifest for the Foundry project, hosted agent, environment
  variables, and deployment mode
- `src/strands-agents/main.py` - Strands orchestrator, specialist agent, MCP client, and
  Responses server entry point
- `src/strands-agents/pyproject.toml` and `uv.lock` - fully resolved Python runtime
  dependencies
- `src/strands-agents/Dockerfile` - optional container definition
- `README.md` - prerequisites and supported local run, test, and deployment paths

Do not commit `.vscode` launch or task files generated when the Foundry Toolkit scaffolds
a local workspace.

## Strands-specific rules

- Build a new `Agent` per request. Strands agents hold conversation state and must not be
  shared across concurrent requests.
- Seed history through `Agent(messages=...)` from `context.get_history()`; do not keep
  server-side conversation state.
- Pass `callback_handler=None` so Strands does not print to stdout.
- Call `agent.cleanup()` when a request finishes so the MCP client session closes.

## Dependency workflow

Follow the shared Python Hosted Agent dependency policy at
`samples/python/hosted-agents/DEPENDENCY_POLICY.md`.

Use `pyproject.toml` and `uv.lock` with uv 0.11.7. The lock must pin the complete direct
and transitive runtime graph. Regenerate it with `uv lock` whenever a dependency input
changes, then run the policy checker, including its `--resolve` closure check when
network access is available.

## Runtime logging

Use the standard `logging` module for diagnostics emitted by the running hosted
agent. Prefer `logger.info()`, `logger.warning()`, and `logger.exception()` over
`print()`; Python stdout may remain buffered in hosted containers. E2E log assertions
must target a deliberate sample-owned log event, not mutable framework wording.

## Development workflow

```bash
azd provision                              # Provision declared Azure resources, if needed
azd ai agent run                           # Run locally on http://localhost:8088
azd ai agent invoke --local "your message" # Test the local agent
azd deploy                                 # Deploy to Foundry
azd ai agent invoke "your message"         # Invoke the deployed agent
azd down                                   # Remove resources created for the project
```

## Microsoft Foundry Skill

Install the **Microsoft Foundry Skill** for guided deployment, evaluation, and
troubleshooting workflows.

Direct install (preferred, works with any coding agent):

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

Or install the Azure Skills Plugin:

- **Copilot CLI**: `/plugin marketplace add microsoft/azure-skills` then
  `/plugin install azure@azure-skills`
- **Claude Code**: `/plugin install azure@claude-plugins-official`

Then ask naturally, for example:
`Use the Microsoft Foundry Skill to deploy this agent.`

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Strands Agents documentation](https://strandsagents.com/latest/documentation/docs/)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
