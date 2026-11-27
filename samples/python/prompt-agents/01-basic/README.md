# Basic Prompt Agent

The minimal prompt agent: a model plus instructions, defined in [`agent.yaml`](./agent.yaml) and [`instructions.md`](./instructions.md). No tools, files, or skills.

## Deploy

```bash
azd up
azd ai agent invoke "Hi"
```

## Managed Harness Agent

Supported. To run this as a Managed Harness Agent, add one line to [`agent.yaml`](./agent.yaml):

```yaml
harness: github-copilot
```
