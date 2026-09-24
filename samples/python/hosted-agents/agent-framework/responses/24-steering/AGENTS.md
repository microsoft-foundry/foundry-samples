# Coding Agent Instructions - Steering

This sample is a Microsoft Foundry hosted Agent Framework agent served through
the Responses protocol. It demonstrates same-conversation steering of a regular
agent while an earlier turn is active.

## Deployment mode

- **Direct code deployment:** `azure.yaml` declares the Python 3.13 runtime and
  `main.py` entry point. The Dockerfile remains available for equivalent local
  container and live protocol validation.

## Key files

- `azure.yaml` - Foundry project and hosted-agent manifest
- `src/agent-framework-steering-responses/main.py` - agent and host
- `src/agent-framework-steering-responses/pyproject.toml` and `uv.lock` - fully
  resolved runtime dependencies
- `src/agent-framework-steering-responses/Dockerfile` - Linux container
- `README.md` - local, deployment, and same-conversation steering validation

Do not commit Foundry Toolkit generated `.vscode` files.

## Dependency workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`. Use uv 0.11.7, run
`uv lock`, and validate with `uv sync --frozen`.

## Steering invariants

- Steering is same-conversation input admitted during active work, not crash
  recovery.
- Send the steering request with the same `conversation` while the first response
  is active.
- Do not combine `conversation` and `previous_response_id` in that request.
- Do not claim the .NET host's `queued` status or serialized ordering. The current
  published Python beta reports the admitted response as `in_progress` and can
  execute it before the earlier turn finishes.

## Runtime logging

Use `logging` for hosted diagnostics. Never log credentials, tokens, or isolation
key values.

## Development workflow

```bash
uv sync --frozen
uv run python main.py
azd ai agent run
azd deploy
```

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Agent Framework agents](https://learn.microsoft.com/en-us/agent-framework/agents/)
