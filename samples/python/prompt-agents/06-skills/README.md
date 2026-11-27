# Prompt Agent with Skills

A prompt agent backed by a reusable, file-based **skill** using the `skills/` folder convention. On deploy, azd registers each `SKILL.md` bundle under [`skills/`](./skills/) and attaches it — no skill is listed in [`agent.yaml`](./agent.yaml).

## Deploy

```bash
azd up
azd ai agent invoke "Make me a 3-day travel guide for Lisbon focused on food and viewpoints."
```

## Managed Harness Agent

Supported (skills are registered as a toolbox/MCP tool). To run this as a Managed Harness Agent, add one line to [`agent.yaml`](./agent.yaml):

```yaml
harness: github-copilot
```
