# Prompt Agent with Skills

A Microsoft Copilot harness prompt agent backed by a reusable, file-based **skill**. [`azure.yaml`](./azure.yaml) declares the `azure.ai.skill` sibling and the agent dependency; the bundle lives under [`skills/`](./skills/).

Requires azd 1.36.0 or later. The manifest pins Agents beta.21, Projects beta.14, and Skills beta.8.

## Deploy

```bash
azd up
azd ai agent invoke "Make me a 3-day travel guide for Lisbon focused on food and viewpoints."
```
