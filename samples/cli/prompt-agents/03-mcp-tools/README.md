# Prompt Agent with MCP Tools

A prompt agent that calls the public **Microsoft Learn** [MCP](https://modelcontextprotocol.io/) server without authentication. The tool is configured for unattended use in [`azure.yaml`](./azure.yaml).

Requires azd 1.36.0 or later. The manifest pins Agents beta.21 and Projects beta.14.

## Deploy

```bash
azd up
azd ai agent invoke "How do I create a hosted agent with azd? Cite the Microsoft Learn docs."
```

## GitHub Copilot harness

To use the GitHub Copilot harness, add this block to a separately named agent service in [`azure.yaml`](./azure.yaml):

```yaml
harness:
  type: github_copilot_preview
```
