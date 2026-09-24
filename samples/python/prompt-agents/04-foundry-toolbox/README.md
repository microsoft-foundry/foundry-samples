# Managed Agent with a Foundry Toolbox

A GitHub Copilot harness agent backed by a **Foundry Toolbox**, configured in [`azure.yaml`](./azure.yaml).

The sample creates a toolbox containing built-in web search as part of
`azd deploy`.

## Deploy

```bash
azd up
azd ai agent invoke "Use your tools to help me with today's task."
```
