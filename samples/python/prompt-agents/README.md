# Prompt Agent Samples

Declarative **prompt agent** samples you deploy with [`azd`](https://aka.ms/azd). Each agent and its inline instructions are defined in `azure.yaml` alongside its Foundry project and dependencies.

## Samples

- [01-basic](./01-basic/) — minimal model + instructions
- [02-tools](./02-tools/) — client-executed function tools
- [03-mcp-tools](./03-mcp-tools/) — remote MCP server tools
- [04-foundry-toolbox](./04-foundry-toolbox/) — curated Foundry Toolbox
- [05-skills](./05-skills/) — reusable file-based skill
- [06-azure-search-rag](./06-azure-search-rag/) — RAG over Azure AI Search

Each sample's README notes whether it supports the GitHub Copilot harness.

See also the standalone SDK samples in this folder: [agent-identity-and-skills](./agent-identity-and-skills/), [code-interpreter-custom](./code-interpreter-custom/).
