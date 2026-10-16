# Prompt Agent with MCP Tools

A prompt agent that calls tools on a remote [MCP](https://modelcontextprotocol.io/) server. The `type: mcp` tool and its `connections:` entry in [`agent.yaml`](./agent.yaml) point at the public **Microsoft Learn** MCP server (Entra auth, no keys). `require_approval: always` asks for approval before each call; set it to `never` for unattended use.

## Deploy

```bash
azd up
azd ai agent invoke "How do I create a hosted agent with azd? Cite the Microsoft Learn docs."
```

## Managed Harness Agent

Supported. To run this as a Managed Harness Agent, add one line to [`agent.yaml`](./agent.yaml):

```yaml
harness: github-copilot
```
