# Native A2A hosted-agent samples

Three deterministic Python samples using `azure-ai-agentserver-a2a` and the
official native A2A SDK. No model deployment is required.

| Sample | What you learn |
|---|---|
| [Echo](echo/README.md) | Send a message and receive a completed Task |
| [Long-running Tasks](long-running-tasks/README.md) | Submit, poll and cancel report work |
| [Task persistence](task-persistence/README.md) | Save, retrieve and list complete Task snapshots |

Each README follows the shared hosted-agent template: prerequisites, an azd
run/deploy/invoke path, manual VS Code debugging, and sample-specific examples.
Start with Echo.

## Run locally

Open a sample's runtime directory and run:

```powershell
uv run --frozen --python 3.13 python main.py
```

uv creates the environment and installs the committed lock automatically.
No separate package installation, index flags or feed login is needed.

For azd local startup and hosted invocation, follow the sample README.
Agent extension beta.23 supports hosted A2A 1.0 invocation behind
`AZD_ALPHA_ENABLE_AGENTS_A2A=true`, but does not support A2A `invoke --local`.

## Preview dependencies

All three projects pin A2A `1.0.0a20261029006`, Core `2.3.1a20261029006`, and
native `a2a-sdk==1.2.3`. Only the two AgentServer packages use the public Azure
SDK dev feed; other dependencies use PyPI. These are development builds, not a
PyPI SDK release. Keep `pyproject.toml` and `uv.lock` together.

## Tests

These are optional development checks, not steps needed to invoke an agent.
From the repository root:

```powershell
uv run --frozen --python 3.13 --project samples\python\hosted-agents\bring-your-own\a2a\echo\src\echo-a2a `
  python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

The seven real-HTTP/process tests cover Echo, Unicode, immediate return,
polling, cancellation, full Task retrieval after process restart, local
simulated-caller separation and absent-store reads. Local simulated identities
are not a cloud authentication proof.

## Repository dependency policy

The existing PyPI-only repository check reports `PYREQ009` for the alpha feed
sources. No shared check or unapproved exception should be used to bypass it.
When the SDK packages are published to PyPI, replace the alpha pins, remove
the dev-feed mappings and regenerate all three locks with uv 0.11.7.
