# Coding Agent Instructions - Harness scaling capabilities

This sample is a **Microsoft Foundry hosted agent**. It ports the Microsoft Agent Framework
personal-finance harness sample to the Foundry **Responses v2** protocol while preserving its file
skills, background research, confined shell, CodeAct provider, and simulated trade tool. It runs in
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents),
which manages hosting, security, scaling, and observability so contributors can focus on the agent
logic.

## Deployment mode

- **Direct code deployment:** `codeConfiguration` in `azure.yaml` declares the Python runtime and
  `main.py` entry point. A Dockerfile is not required.

## Key files

- `azure.yaml` - `azd` manifest for the Foundry project, model deployment, hosted agent,
  environment variables, and direct code deployment
- `src/harness-scaling-capabilities-responses/main.py` - agent implementation and Responses server
  entry point
- `src/harness-scaling-capabilities-responses/pyproject.toml` - project metadata and dependencies
- `src/harness-scaling-capabilities-responses/uv.lock` - reproducible dependency lock
- `src/harness-scaling-capabilities-responses/skills/` - bundled valuation and risk-scoring skills
- `src/harness-scaling-capabilities-responses/working/` - seed portfolio and trade-confirmation
  files copied into writable session storage
- `README.md` - prerequisites and supported local run, test, and deployment paths

Do not commit `.vscode` launch or task files generated when the Foundry Toolkit scaffolds a local
workspace. Keep the project's `.venv` in `src/harness-scaling-capabilities-responses/`, next to
`pyproject.toml`.

## Development workflow

The **Azure Developer CLI (`azd`)** manages the hosted-agent lifecycle. From an initialized agent
project:

```bash
azd provision                              # Provision declared Azure resources, if needed
azd ai agent run                           # Run locally on http://localhost:8088
azd ai agent invoke --local "your message" # Test the local agent
azd deploy                                 # Deploy to Foundry
azd ai agent invoke "your message"         # Invoke the deployed agent
azd down                                   # Remove resources created for the project
```

Consecutive invokes reuse the Responses conversation, which lets the README's multi-turn capability
trajectory build on earlier turns.

## Microsoft Foundry Skill

This project was built with the microsoft-foundry skill. Before working on or answering questions
about Foundry agents, read the microsoft-foundry skill first.

Install the **Microsoft Foundry Skill** for guided deployment, evaluation, and troubleshooting
workflows.

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

- [Original Agent Framework sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/harness/build_your_own_claw/claw_step03_scaling_capabilities.py)
- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
