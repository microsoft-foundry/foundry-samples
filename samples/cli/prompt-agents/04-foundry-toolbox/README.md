# Prompt Agent with the GitHub Copilot harness and a Foundry Toolbox

A GitHub Copilot harness agent backed by a **Foundry Toolbox**, configured in [`azure.yaml`](./azure.yaml).

The sample creates a toolbox containing built-in web search as part of
`azd deploy`.

## Deploy

```bash
azd up
azd ai agent invoke "Search the web for the latest stable Python release and cite the official Python release page."
```
