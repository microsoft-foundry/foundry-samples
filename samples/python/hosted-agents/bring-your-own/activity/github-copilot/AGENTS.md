# Coding Agent Instructions

This project is a **Microsoft Foundry hosted agent** — a containerized AI agent that runs in [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents). The platform handles containerization, hosting, security, scaling, and observability so you can focus on agent logic.

This agent uses the **Activity protocol** (Bot Framework / M365 Agents SDK), so it is reached through a **Bot channel (Microsoft Teams)** rather than the request/response `azd ai agent invoke` path used by the responses protocol.

## Key files

- `main.py` — activity handlers (`message`, `conversationUpdate`) → `client.ask()`
- `client.py` — GitHub Copilot SDK harness (session + `ask()`)
- `tools.py` — the custom tool set (a to-do list); tasks are persisted to a JSON file under `$HOME` so they survive sandbox idle/recycle
- `files.py` — attachment text extraction (PDF / DOCX / PPTX), inlined into the prompt by `main.py`
- `pyproject.toml` — direct runtime dependencies and Python compatibility
- `uv.lock` — reproducible dependency graph used by local and container workflows
- `Dockerfile` — container definition

## Development workflow

The **Azure Developer CLI (`azd`)** manages the full lifecycle:

```bash
cd src/github-copilot-activity
uv sync --frozen
cd ../..
azd ai agent run                 # Run locally on http://localhost:8088
azd deploy                       # Deploy to Foundry (creates the Azure Bot + Teams channel)
```

Activity agents are push-based: the agent replies out-of-band through the Bot
Connector, so `azd ai agent invoke` (which reads a synchronous response body) does
**not** apply here. Test a deployed agent by chatting with it in **Microsoft Teams**
(package/sideload the Teams app produced during deploy). For a local terminal loop,
POST a synthetic activity to `http://localhost:8088/activity/messages` with a
`serviceUrl` pointing at a local catcher.

## Microsoft Foundry Skill

This project was built with the microsoft-foundry skill. Before working on or answering questions about Foundry agents, read the microsoft-foundry skill first.

Install the **Microsoft Foundry Skill** for guided deployment, evaluation, and troubleshooting workflows.

Direct install (preferred, works with any coding agent):

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

Or install the Azure Skills Plugin:

- **Copilot CLI**: `/plugin marketplace add microsoft/azure-skills` then `/plugin install azure@azure-skills`
- **Claude Code**: `/plugin install azure@claude-plugins-official`

Then ask naturally, e.g. `Use the Microsoft Foundry Skill to deploy this agent.`

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
