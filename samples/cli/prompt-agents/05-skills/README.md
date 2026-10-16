# Prompt Agent with Skills

A prompt agent backed by a reusable, file-based **skill**. [`azure.yaml`](./azure.yaml) declares the `azure.ai.skill` sibling and the agent dependency; the bundle lives under [`skills/`](./skills/).

## Deploy

```bash
azd up
azd ai agent invoke "Make me a 3-day travel guide for Lisbon focused on food and viewpoints."
```

## GitHub Copilot Harness

Supported. To use the GitHub Copilot harness, add this block to the agent service in [`azure.yaml`](./azure.yaml):

```yaml
harness:
  type: github_copilot_preview
```
