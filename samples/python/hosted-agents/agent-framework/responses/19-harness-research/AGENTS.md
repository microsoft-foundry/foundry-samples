# Coding Agent Instructions - Research Harness (Responses)

This sample is a **Microsoft Foundry hosted agent**. It hosts the Microsoft Agent
Framework research harness through Responses protocol v2, including planning, todos,
web search, context compaction, and file memory. It runs in
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents),
which manages hosting, security, scaling, and observability so contributors can focus on
the agent logic.

## Deployment mode

- **Direct code deployment:** `codeConfiguration` in `azure.yaml` declares the Python
  3.13 runtime and `main.py` entry point. A Dockerfile is not required for this default
  path.

The source directory also includes a Dockerfile so users can select container deployment
with `azd ai agent init --deploy-mode container`; initialization updates the local
manifest for that deployment mode.

## Key files

- `azure.yaml` - `azd` manifest for the Foundry project, hosted agent, model,
  environment variables, and default deployment mode
- `src/agent-framework-harness-research-responses/main.py` - harness configuration and
  Responses server entry point
- `src/agent-framework-harness-research-responses/pyproject.toml` - Python project
  metadata and dependencies
- `src/agent-framework-harness-research-responses/uv.lock` - reproducible dependency
  lockfile
- `src/agent-framework-harness-research-responses/uv.toml` - uv configuration
- `src/agent-framework-harness-research-responses/Dockerfile` - Python 3.13 container
  definition for optional container deployment
- `src/agent-framework-harness-research-responses/.dockerignore` - files excluded from
  the container build context
- `README.md` - prerequisites and supported local run, test, and deployment paths

Do not commit `.vscode` launch or task files generated when the Foundry Toolkit
scaffolds a local workspace.

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
- [Microsoft Agent Framework harness source](https://github.com/microsoft/agent-framework/tree/848443ac68b9470de5c43c3a355829625d7f0a3a/python/samples/02-agents/harness)
