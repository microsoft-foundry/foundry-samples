# Coding Agent Instructions - LangChain Middleware (Responses)

This sample is a **Microsoft Foundry hosted agent**. It demonstrates native
LangChain middleware and human-reviewed simulated email tool calls over the
Responses protocol. It runs in
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents),
which manages hosting, security, scaling, and observability so contributors can focus on
the agent logic.

## Deployment mode

- **Direct code deployment (default):** `codeConfiguration` declares the Python
  runtime and entry point. `.agentignore` excludes container-only build files.
- **Container deployment:** initializing with `--deploy-mode container` uses the
  included Dockerfile. Repository cloud CI validates both deployment modes.

## Key files

- `azure.yaml` - `azd` manifest for the Foundry project, hosted agent, dependencies,
  environment variables, and deployment mode
- `src/langgraph-middleware/main.py` - agent implementation and server
  entry point
- `src/langgraph-middleware/pyproject.toml` and `uv.lock` - default, fully resolved Python runtime dependencies; use `requirements.txt` only as the backward-compatible fallback
- `src/langgraph-middleware/Dockerfile` and `.dockerignore` - frozen production
  image build and container context exclusions, aligned with neighboring samples
- `README.md` - prerequisites and supported local run, test, and deployment paths

Do not commit `.vscode` launch or
task files generated when the Foundry Toolkit scaffolds a local workspace.

## Dependency workflow

Follow the shared Python Hosted Agent dependency policy at
`samples/python/hosted-agents/DEPENDENCY_POLICY.md`.

Use `pyproject.toml` and `uv.lock` by default. A fully resolved
`requirements.txt` remains accepted as a backward-compatible fallback. The
selected artifact must pin the complete direct and transitive runtime graph; if
both forms exist, the uv pair is authoritative. Update the selected artifact
whenever a dependency input changes. Run the policy checker, including its
`--resolve` closure check when network access is available, before completing
dependency changes.

## Runtime logging

Use the standard `logging` module for diagnostics emitted by the running hosted
agent. Prefer `logger.info()`, `logger.warning()`, and `logger.exception()` over
`print()` when output must be observable while the long-running process remains
alive; Python stdout may remain buffered in hosted containers.

Use `print()` only when stdout is intentionally part of a CLI, provisioning
script, local test utility, or tool-result contract. If stdout is required from a
long-running process, flush it explicitly. E2E log assertions must target a
deliberate sample-owned log event, not mutable framework or dependency wording.

## Development workflow

The **Azure Developer CLI (`azd`)** manages the hosted-agent lifecycle. From an
initialized agent project:

```bash
azd provision                              # Provision declared Azure resources, if needed
azd ai agent run                           # Run locally on http://localhost:8088
azd ai agent invoke --local "your message" # Test the local agent
azd deploy                                 # Deploy to Foundry
azd ai agent invoke "your message"         # Invoke the deployed agent
azd down                                   # Remove resources created for the project
```

Adapt this sequence when the sample is deploy-first or requires another client or
protocol.

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
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
