# Prompt Agent Samples

Declarative **prompt agent** samples you deploy with [`azd`](https://aka.ms/azd). Each is a `kind: prompt` agent defined by `agent.yaml` (the agent), `instructions.md` (its system prompt), and `azure.yaml` (azd wiring).

## Runtime connection

Every sample's `azure.yaml` leaves `promptAgent: {}` empty on purpose. The managed prompt-agent runtime connection — `subscriptionId`, `resourceGroup`, and `workspace` — comes from your Foundry project. `azd ai agent init` fills these in, or set the `AZD_MANAGED_AGENT_*` environment variables.

## Samples

- [01-basic](./01-basic/) — minimal model + instructions
- [02-tools](./02-tools/) — client-executed function tools
- [03-mcp-tools](./03-mcp-tools/) — remote MCP server tools
- [04-foundry-toolbox](./04-foundry-toolbox/) — curated Foundry Toolbox
- [05-files](./05-files/) — document grounding with file search
- [06-skills](./06-skills/) — reusable file-based skill
- [07-azure-search-rag](./07-azure-search-rag/) — RAG over Azure AI Search

Each sample's README notes whether it can also run as a Managed Harness Agent.

See also the standalone SDK samples in this folder: [agent-identity-and-skills](./agent-identity-and-skills/), [code-interpreter-custom](./code-interpreter-custom/).
