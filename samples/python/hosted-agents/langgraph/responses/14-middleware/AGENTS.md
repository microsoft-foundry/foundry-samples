# Coding Agent Instructions - LangChain Middleware (Responses)

This sample is a **Microsoft Foundry hosted agent**. It demonstrates native
LangChain middleware and human-reviewed simulated email tool calls over the
Responses protocol. It runs in
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents),
which manages hosting, security, scaling, and observability so contributors can focus on
the agent logic.

## Deployment mode

- **Direct code deployment (default):** `codeConfiguration` declares the Python
  runtime and entry point. `.agentignore` excludes container-only build files.
- **Container deployment:** initializing with `--deploy-mode container` uses the
  included Dockerfile. Repository cloud CI validates both deployment modes.

## Key files

- `azure.yaml` - `azd` manifest for the Foundry project, hosted agent, dependencies,
  environment variables, and deployment mode
- `src/langgraph-middleware/agent.py` - native `create_agent` middleware,
  message limit, and simulated email tool; keep it independent of hosting
- `src/langgraph-middleware/main.py` - explicit credential/model/checkpoint
  lifetime and stock-host factory; the stock host is the sole LangChain
  instrumentation owner, so do not also enable the SDK auto-tracer
- `src/langgraph-middleware/client.py` - JSON/SSE approve/edit/reject review
  client; one decision applies to all proposed actions and one review round
- `src/langgraph-middleware/pyproject.toml` and `uv.lock` - default, fully resolved Python runtime dependencies; use `requirements.txt` only as the backward-compatible fallback
- `src/langgraph-middleware/Dockerfile` and `.dockerignore` - frozen production
  image build and container context exclusions, aligned with neighboring samples
- `README.md` - prerequisites and supported local run, test, and deployment paths

Do not commit `.vscode` launch or
task files generated when the Foundry Toolkit scaffolds a local workspace.

## Dependency workflow

Follow the shared Python Hosted Agent dependency policy at
`samples/python/hosted-agents/DEPENDENCY_POLICY.md`.

Use `pyproject.toml` and `uv.lock` by default. A fully resolved
`requirements.txt` remains accepted as a backward-compatible fallback. The
selected artifact must pin the complete direct and transitive runtime graph; if
both forms exist, the uv pair is authoritative. Update the selected artifact
whenever a dependency input changes. Run the policy checker, including its
`--resolve` closure check when network access is available, before completing
dependency changes.

## Runtime logging

Use the standard `logging` module for diagnostics emitted by the running hosted
agent. Prefer `logger.info()`, `logger.warning()`, and `logger.exception()` over
`print()` when output must be observable while the long-running process remains
alive; Python stdout may remain buffered in hosted containers.

Use `print()` only when stdout is intentionally part of a CLI, provisioning
script, local test utility, or tool-result contract. If stdout is required from a
long-running process, flush it explicitly. E2E log assertions must target a
deliberate sample-owned log event, not mutable framework or dependency wording.

## Development workflow

The **Azure Developer CLI (`azd`)** manages the hosted-agent lifecycle. Follow
the README's new-project or reused-project path; provision only missing,
intentionally owned dependencies. From the initialized sample root:

```bash
azd ai agent run --no-client
azd ai agent invoke --local "Hello!"
```

A greeting only checks invocation. Exercise [the real review flow](README.md#review-an-email)
from `src/langgraph-middleware` in another terminal:

```bash
uv sync --frozen --group dev
uv run --frozen client.py --decision approve
uv run --frozen client.py --decision edit --recipient bob@example.com
uv run --frozen client.py --stream --decision reject
```

After local validation, run `azd deploy` from the initialized sample root and
repeat the review commands with the deployed `--agent-name`.

Keep the shared cloud behavior contract aligned with the sample's native review
flow. Validate and plan that contract using the shared hosted-agent tooling.
Use the real review client for local/deployed approve, edit, and reject checks;
the cloud harness automates approval only. Keep debug tooling out of production
packages. Follow the [Toolkit/Inspector acceptance](README.md#frontend-coverage-and-acceptance-boundary)
separately; headless startup and cloud E2E do not establish UI acceptance.

## Resource and state cleanup

Follow the README's [ownership-aware cleanup](README.md#cleanup-and-local-state).
`azd down` can delete an entire newly provisioned resource group; it does not
remove a hosted agent from a reused project. Delete only the agent/version owned
by this exercise, not shared projects/models or another owner's versions. Do not
use forced deletion to bypass active-session protection without checking scope.

Local state defaults to shared `~/.agentserver`. Prefer a sample-owned absolute
`AGENTSERVER_STATE_ROOT`, preserve it for paused-review recovery, and never
recursively delete the shared home directory. Tests and their subprocesses must
use owned temporary state roots. Content-capture flags do not erase persistence.

## Microsoft Foundry Skill

Install the **Microsoft Foundry Skill** for guided deployment, evaluation, and
troubleshooting workflows.

Direct install (preferred, works with any coding agent):

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

Or install the Azure Skills Plugin:

- **Copilot CLI**: `/plugin marketplace add microsoft/azure-skills` then
  `/plugin install azure@azure-skills`
- **Claude Code**: `/plugin install azure@claude-plugins-official`

Then ask naturally, for example:
`Use the Microsoft Foundry Skill to deploy this agent.`

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
