# Coding Agent Instructions

This project is a **Microsoft Foundry hosted agent** — a containerized AI agent that runs in [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents). The platform handles containerization, hosting, security, scaling, and observability so you can focus on agent logic.

This particular sample combines two layers:

- **GitHub Copilot SDK** (`github-copilot-sdk`) — the agent brain. It spawns the bundled Copilot CLI subprocess and runs its own model + tool-calling loop, and provides native steering (`send(mode="immediate")`), queueing (`send(mode="enqueue")`), durable sessions (`resume_session`), and human-in-the-loop (`on_elicitation_request`).
- **Resilient `@multi_turn_task`** (`azure-ai-agentserver-core`) — the durable host. It keeps the Copilot session alive with no client traffic, re-invokes the task with `entry_mode="recovered"` after a crash, and exposes a file-backed SSE stream that reconnects with no gap.

## Key files

- `src/resilient-copilot/main.py` — HTTP surface (POST / GET-SSE / `/elicit` / cancel)
- `src/resilient-copilot/agent.py` — the resilient `@multi_turn_task` supervising the Copilot session
- `src/resilient-copilot/copilot_session.py` — thin Copilot SDK harness (create/resume, event pump, elicitation bridge)
- `Dockerfile` — container definition

## Development workflow

The **Azure Developer CLI (`azd`)** manages the full lifecycle:

```bash
azd ai agent run                                    # Run locally on http://localhost:8088
azd ai agent invoke --local '{"input": "hi"}'       # Test the local agent
azd deploy                                           # Deploy to Foundry
azd ai agent invoke '{"input": "hi"}'                # Invoke the deployed agent
```

## Microsoft Foundry Skill

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
