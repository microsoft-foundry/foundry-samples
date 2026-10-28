# Credential-free Python Hosted Agent runtime checks

The [Hosted-agent policies workflow](../../../.github/workflows/hosted-agent-policies.yml)
has separate dependency-policy, contract-policy, and runtime jobs. A passing
policy test does not mean a sample executed. The runtime job runs the commands
declared by each selected sample using Python 3.13 and uv 0.11.7, without Azure
secrets, OIDC, or persisted checkout credentials.

## Declare checks

For a uv-based Python `azure.ai.agent` service, add a locked `dev` dependency
group and this declaration to its runtime `pyproject.toml`:

```toml
[tool.hosted-agent-validation]
commands = [
    ["python", "-m", "pytest", "tests", "-q"],
    ["ruff", "check", "."],
    ["ruff", "format", "--check", "."],
]
```

Choose commands appropriate to the runtime's existing test framework; stdlib
`unittest` is also supported. Each command is an argument array, never a shell
string. Keep checks credential-free: exercise the real SDK/host integration and
replace only external services/network. Tests and dev tools must not be copied
into production deployment packages.

## Selection and execution

[The runner](../../../.github/scripts/check_hosted_agent_runtime.py) discovers
Python service roots from `azure.yaml`, not sample names. Changes under a declared
runtime or to its service manifest select it. Changes to the shared runner,
dependency-discovery helper, runner tests, tooling requirements, or workflow run
all declared runtimes. Legacy runtimes without declarations are not claimed as
tested; removing an existing runtime's declaration fails validation. Deleting or
renaming its `pyproject.toml`, including a switch to `requirements.txt`, cannot
disable previously declared checks while the hosted service remains.
The guard follows the manifest and service name when `project` moves to another
directory. Git renames contribute both source and destination paths, so moving
code out of a runtime still selects its checks. Services sharing one runtime are
checked once without discarding any service's previous declaration.

For each selected runtime, the runner uses its service root as the working
directory, runs `uv sync --frozen --group dev`, then executes each declared command
with `uv run --frozen --group dev -- ...`. A failing command stops validation.
The runner supplies a temporary `AGENTSERVER_STATE_ROOT` and disables ordinary
tracing/content capture; telemetry tests must explicitly configure isolated
exporters and controls. Ambient LangSmith/LangChain tracing switches are also
disabled. Subprocesses must inherit test-owned state, not write to
the developer's `~/.agentserver`.

## Run locally

From the repository root, install the shared checker dependencies, then run one
working-tree runtime:

```bash
python -m pip install "uv==0.11.7" -r .github/scripts/requirements.txt
python .github/scripts/check_hosted_agent_runtime.py --runtime samples/python/hosted-agents/langgraph/responses/14-middleware/src/langgraph-middleware
```

To reproduce PR selection after committing, check out the intended head and use
the merge base with the target branch:

```bash
python .github/scripts/check_hosted_agent_runtime.py --base "<merge-base-SHA>" --head HEAD
```

This job does not deploy to Azure or establish Toolkit/Inspector UI acceptance.
Those remain separate validations with exact-head evidence.
