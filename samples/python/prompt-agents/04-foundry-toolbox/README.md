# Prompt Agent with a Foundry Toolbox

A prompt agent backed by a **Foundry Toolbox** — a curated bundle of tools behind one managed endpoint. [`agent.yaml`](./agent.yaml) references the toolbox by name and adds `toolbox_search_preview` so the model can discover its tools.

## Prerequisites

An existing Foundry Toolbox in your project:

```bash
azd env set TOOLBOX_NAME <your-toolbox-name>
```

## Deploy

```bash
azd up
azd ai agent invoke "Use your tools to help me with today's task."
```

## Managed Harness Agent

Supported. To run this as a Managed Harness Agent, add one line to [`agent.yaml`](./agent.yaml):

```yaml
harness: github-copilot
```
