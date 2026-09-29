# Coding Agent Instructions - Resilient Workflow

This sample is a Microsoft Foundry hosted Agent Framework workflow served through
the Responses protocol. It demonstrates durable checkpoint recovery for a stored
background response after the hosted process is replaced.

## Deployment mode

- **Direct code deployment:** `azure.yaml` declares the Python 3.13 runtime and
  `main.py` entry point. The Dockerfile remains available for equivalent local
  container and live protocol validation.

## Key files

- `azure.yaml` - Foundry project and hosted-agent manifest
- `src/agent-framework-resilient-workflow-responses/main.py` - workflow and host
- `src/agent-framework-resilient-workflow-responses/pyproject.toml` and `uv.lock`
  - fully resolved runtime dependencies
- `src/agent-framework-resilient-workflow-responses/Dockerfile` - Linux container
- `README.md` - local, deployment, and crash-recovery validation

Do not commit Foundry Toolkit generated `.vscode` files.

## Dependency workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`. Use uv 0.11.7, run
`uv lock`, and validate with `uv sync --frozen`.

## Recovery invariants

- Keep workflow and executor identities stable across replacement processes.
- Store durable data only in workflow checkpoint state.
- Use `background=true` together with `store=true`.
- Retrieve the same response ID after a transport failure. Never resubmit under a
  replacement ID.
- Allow the completed superstep to commit before terminating the process.
- Keep replayed work idempotent because recovery can execute the last boundary
  more than once.

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
- [Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/)
