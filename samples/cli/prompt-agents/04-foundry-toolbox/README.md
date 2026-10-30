# Prompt Agent with the Microsoft Copilot harness and a Foundry Toolbox

A Microsoft Copilot harness agent backed by a **Foundry Toolbox**, configured in [`azure.yaml`](./azure.yaml).

The sample creates a toolbox containing built-in web search as part of
`azd deploy`.

Requires azd 1.36.0 or later with the Agents beta.21, Projects beta.14, and Toolboxes beta.11
extensions pinned by the manifest.

## Deploy

```bash
azd up
azd ai agent invoke "Search the web for the latest stable Python release and cite the official Python release page."
```
