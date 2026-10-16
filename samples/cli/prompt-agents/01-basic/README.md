# Basic Prompt Agent

The minimal prompt agent: a model plus inline instructions, defined in [`azure.yaml`](./azure.yaml). No tools or skills.

## Deploy

```bash
azd up
azd ai agent invoke "Hi"
```

## GitHub Copilot Harness

Supported. To use the GitHub Copilot harness, add this block to the agent service in [`azure.yaml`](./azure.yaml):

```yaml
harness:
  type: github_copilot_preview
```
