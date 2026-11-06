# Coding Agent Instructions - native A2A Echo

This Microsoft Foundry hosted agent implements deterministic Echo using the
native A2A SDK, with no model, Copilot session or Toolbox.

## Deployment mode and key files

- `azure.yaml`: direct code deployment, Python 3.13, A2A interface and Agent Card.
- `src/echo-a2a/main.py`: executor, cancellation handling and server entry point.
- `src/echo-a2a/pyproject.toml` and `uv.lock`: pinned public beta SDK dependencies.
- `echo-request.json` and `get-task.json`: native message and task retrieval examples.
- `README.md`: deployment, local execution and cleanup.

Keep the public PyPI manifests and genuine generated locks consistent. Follow
the shared Python hosted-agent dependency policy and cloud behavior-contract
requirements. Use the shared cloud runner's native A2A 1.0 Task/artifact
validation; never mislabel the protocol or add a skiplist entry to bypass it.

Keep Echo deterministic. Return actual completed A2A Tasks and artifact text.
Use standard logging for runtime diagnostics, not credentials or caller headers.
The hosting adapter owns Task persistence; do not add custom application storage.
Do not commit generated `.azure`, `.vscode`, virtual environments or logs.

Use `azd deploy echo` for direct code deployment. Native A2A requires the
appropriate shell's `AZD_ALPHA_ENABLE_AGENTS_A2A=true` environment setting.
The Microsoft Foundry Skill can guide setup and troubleshooting:

```text
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```
