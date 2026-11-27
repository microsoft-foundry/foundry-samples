# Coding Agent Instructions - OpenClaw incident brief

This sample connects OpenClaw tools to a Microsoft Foundry Hosted Agent using
the Invocations protocol and resilient tasks. Read the microsoft-foundry skill
before changing or answering questions about Foundry agents.

## Deployment mode

`azure.yaml` uses direct code deployment with `codeConfiguration`. Keep the
service key and hosted-agent name aligned. Do not commit generated `.vscode`
files.

## Key files

- `src/incident-brief/main.py` - Invocations handlers, durable reservations,
  resilient task, and model calls.
- `src/incident-brief/pyproject.toml` and `uv.lock` - locked Python dependencies.
- `src/incident-brief/tests/` - local HTTP and task integration tests.
- `plugin/` - OpenClaw plugin, locked Node dependencies, and client tests.
- `README.md` - setup, example incident, and operational limits.

Preserve the actual platform invocation ID, the stable caller request ID, and
the session-scoped mapping between them. Never claim exactly-once model
execution: recovery can repeat interrupted calls. Keep user isolation enabled
and preserve the platform call ID in resilient task input.

## Dependency and test workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`; update the lock
when dependency inputs change and run its checker with `--resolve`. Run
`uv run --no-sync python -m pytest -q` from `src/incident-brief` and `npm test`
from `plugin`. Validate and plan the sample's cloud test spec; its assertions
require a completed asynchronous brief.

Use the standard `logging` module for runtime diagnostics. Do not log incident
updates, model output, or access tokens.

## Microsoft Foundry Skill

Install the skill for deployment and troubleshooting:

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

See the [hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents).
