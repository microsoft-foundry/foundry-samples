# Coding Agent Instructions

This project is a **Microsoft Foundry hosted agent** — a containerized AI agent that runs in [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents). The platform handles containerization, hosting, security, scaling, and observability so you can focus on agent logic.

## Key files

- `src/openai-computer-tool-dotnet-responses/Dockerfile` — container definition
- `src/openai-computer-tool-dotnet-responses/Program.cs` — `Azure.AI.AgentServer.Responses` endpoint (`port 8088`) and `--local` CLI entrypoint
- `src/openai-computer-tool-dotnet-responses/scenarios/PaintSmileyScenario.cs` — Paint Smiley scenario prompt and runner
- `src/openai-computer-tool-dotnet-responses/utils/AgentRunner.cs` — multi-turn GA OpenAI Computer Tool (`{"type": "computer"}`) loop
- `src/openai-computer-tool-dotnet-responses/utils/VirtualPaintDesktop.cs` — `1280x800` in-container Virtual Paint Desktop with pure managed PNG encoding
- `src/openai-computer-tool-dotnet-responses/utils/Settings.cs` — environment and system prompt loader

## Development workflow

The **Azure Developer CLI (`azd`)** manages the full lifecycle:

```bash
azd ai agent run                           # Run locally on http://localhost:8088
azd ai agent invoke --local "paint_smiley" # Test the local agent
azd deploy                                 # Deploy to Foundry
azd ai agent invoke "paint_smiley"         # Invoke the deployed agent
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
