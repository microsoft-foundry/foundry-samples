# Coding Agent Instructions — Python Hosted Agent Samples

Conventions for creating or editing samples under
`samples/python/hosted-agents/`. Follow these shared instructions and any
framework- or sample-specific `AGENTS.md`. Apply new requirements to new
samples and changed parts of existing samples.

## Sample Code

- Read the target README and relevant shared README before editing.
- Give each sample one clear goal. Use native framework and hosting SDK features;
  add custom wrappers or host subclasses only when the goal requires them.
- Follow the framework's directory and naming conventions, use an unused sample
  number where applicable, and update the relevant sample indexes.
- Include an entrypoint, dependencies, `.env.example`, and deployment
  configuration for each supported setup path. Keep names and defaults consistent
  across code, configuration, and documentation. Declare required versions and extras.
- Keep credentials out of committed files. Label simulated tools and data, and
  preserve input validation, error handling, and resource cleanup.
- Keep blocking I/O off the async event loop; use async SDK calls or
  `asyncio.to_thread` for necessary synchronous calls.

## Starting a New Sample

Copy both shared templates into the new sample:

1. Copy [`README-template.md`](./README-template.md) to `README.md`.
2. Copy [`AGENTS-template.md`](./AGENTS-template.md) to `AGENTS.md`.
3. Replace the placeholders, update paths and commands, and remove sections or
   bullets that do not apply.

The Foundry Toolkit generates `.vscode/launch.json` and `.vscode/tasks.json` in
the scaffolded workspace to support the **F5** flow. Do not commit those generated
files to the sample.

Match deployment guidance to the sample's `azure.yaml`: direct code deployment
uses `codeConfiguration` and does not require a Dockerfile; Dockerfile guidance
applies only when the sample uses container deployment through `docker.path`.

Configure `PYTHONNOUSERSITE: "1"` in each Python hosted service's `env` map
and `ENV PYTHONNOUSERSITE=1` in Python Dockerfiles, not in individual run
commands or inside `main.py`.
See the shared [Python startup configuration](./README.md#python-startup-configuration)
for deployment environment and dependency guidance.

## Python Dependency Policy

Follow [`DEPENDENCY_POLICY.md`](./DEPENDENCY_POLICY.md) whenever you create a
Python Hosted Agent runtime or change its dependencies.

- Use `pyproject.toml` and `uv.lock` by default in each executable runtime
  project referenced by `services.<name>.project` in `azure.yaml`.
- A fully resolved `requirements.txt` remains accepted as a backward-compatible
  fallback for existing samples or concrete compatibility constraints.
- The selected artifact must pin the complete direct and transitive runtime
  dependency graph. When both forms exist, the uv pair is authoritative.
- Preserve required extras, prereleases, and environment markers. Do not leave
  bare names, version ranges, wildcard pins, editable/local paths, or mutable
  source references in the consumer artifact.
- When a dependency input changes, update the selected lock artifact in the
  same change.
- Do not update dependency versions during unrelated work. Existing legacy
  samples are grandfathered until a dependency input changes.
- Before finishing a dependency change, run the checker documented in
  `DEPENDENCY_POLICY.md`, including `--resolve` when network access is available.

A uv-native sample may omit `requirements.txt`. Keep `pyproject.toml` and
`uv.lock` synchronized, and run the frozen resolution check before submitting
dependency changes.

## Cloud E2E Contract for New Samples

Every new Python hosted-agent sample must add a public `test-spec.yml` with a
responsible Microsoft owner alias, supported experiences, deterministic turns,
and assertions for its defining behavior. Legacy payload/default support is for
migration and is not sufficient for a new sample.

Read and follow the authoritative [hosted-agent cloud E2E test-spec schema and
onboarding checklist](../../../.azure-pipelines/hosted-agent-tests/README.md).
Run both the documented `validate` and protocol-aware `plan` commands before
submitting changes.

## Runtime Logging

Use the standard `logging` module for diagnostics emitted by a running hosted
agent. Prefer `logger.info()`, `logger.warning()`, and `logger.exception()` over
`print()` when output must be observable while the long-running process remains
alive; Python stdout may remain buffered in hosted containers.

Use `print()` only when stdout is intentionally part of a CLI, provisioning
script, local test utility, or tool-result contract. If stdout is required from a
long-running process, flush it explicitly. E2E log assertions must target a
deliberate sample-owned log event, not mutable framework or dependency wording.

## README Conventions

Write in plain, concise English. Open with what the sample demonstrates, when
to use it, and the expected outcome. Use title case for headings.

Most samples follow the shared template,
[`README-template.md`](./README-template.md). It keeps a familiar section flow:

1. What This Sample Demonstrates
2. How It Works — plus any sample-specific background (e.g. "Environment
   Variables", "Architecture", "Features")
3. Prerequisites — what the *sample* needs: a Foundry project + model deployment,
   its declared Python version, and (only if applicable) RBAC roles, extra Azure
   resources, and environment variables / secrets
4. Option 1: Azure Developer CLI (`azd`) — init → provision → run → invoke →
   deploy → invoke-deployed
5. Option 2: VS Code (Foundry Toolkit) — the one-click **F5** run-and-debug flow
   (Agent Inspector opens automatically) and/or a manual run (`python main.py`)
   → open the Agent Inspector → deploy
6. Any sample-specific deep-dive sections (customization, advanced demos, reference)
7. Troubleshooting
8. Next Steps

- Explain only what the reader needs for the sample's goal. Link to related
  samples or shared reference material for other topics while keeping the
  supported run and deploy paths self-contained.
- Include required resources, versions, authentication, permissions, and variables,
  including cloud requirements for local runs. Distinguish developer and agent access.
- Provide runnable client code with commands, inputs, and expected results. A
  request snippet is enough for a simple call; use a script for stateful flows
  such as approval/resume, stream reconnection, or artifact downloads.
- Keep snippets consistent with the code. Explain relevant limits, persistence,
  content exposure, and cleanup beside the affected steps. Keep review history
  and development plans in the PR description.

## Telemetry

- Enable telemetry by default locally and when hosted. Include the required
  runtime dependencies and initialize instrumentation and export at startup.
- Reuse the framework or hosting SDK's instrumentation and exporter setup.
  Keep one instrumentation owner for each framework to avoid duplicate spans.
- Document exporter and content-recording defaults for each supported run path.
  Telemetry enablement does not require enabling content capture.

## Build and Startup

- When the default `main.py` command does not start the host, set `startupCommand`
  in `azure.yaml` to the actual local hosting command. `codeConfiguration.entryPoint`
  and Docker `CMD` do not set azd's local command.
- For container deployment, include a Dockerfile and `.dockerignore`. Exclude
  local environments, caches, and secrets from the build context.
- Install dependencies before copying application code to preserve Docker layer caching.
- With uv, use `uv sync --compile-bytecode` for dependencies and `compileall` for
  the standard library and application code at build time, using the runtime
  interpreter and final paths. Dependency and standard-library compilation is
  best-effort; application compilation must fail the build on syntax errors and
  exclude `.venv`.
- With pip, use `--no-cache-dir`. Pip compiles dependency bytecode by default;
  avoid redundant dependency-wide `compileall` steps.

Example uv Dockerfile fragment for a sample run directly from source, assuming uv
is installed. Copy any runtime-specific uv configuration with the dependency files.

```dockerfile
WORKDIR /app/user_agent
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode
COPY . .
RUN .venv/bin/python -m compileall -q \
    $(.venv/bin/python -c "import sysconfig as s; print(s.get_paths()['stdlib'])") || true; \
    uv run --no-sync python -m compileall -q -x '[.]venv' .
```

## Validation

- For documentation changes, check affected commands, configuration, and links.
  For runtime or dependency changes, exercise the entrypoint and client flow in a
  clean environment with the documented versions and extras; test new sample logic.
- For startup changes, verify readiness and that the host stays running.
- When changing telemetry or image builds, check default tracing initialization,
  dependency-layer order, and bytecode in the resulting image as applicable.
- Use the existing dependency-policy and cloud E2E tooling for their respective
  checks. Report actual results and distinguish source inspection, offline/mock
  checks, live Foundry validation, and Toolkit/Inspector UI validation.

## Conventions Worth Keeping

- Prefer the current CLI commands (the template reflects these; avoid older
  forms such as `azd ext install azure.ai.agents`).
- Prefer self-contained READMEs over deferring run/deploy steps to a parent
  README or hiding steps inside collapsible `<details>` blocks.
- Keep Toolkit-generated `.vscode` launch/task files out of the sample; document
  that the Toolkit creates them in the scaffolded workspace.

## When a Sample Legitimately Differs

Not every sample fits the two-option shape, and that's fine — adapt rather than
force it:

- **Command-line-only samples** (e.g. VoiceLive, WebSocket, some A2A samples) may
  have no VS Code / Agent Inspector path. Document the flow they actually support
  (curl / `azd` / a browser client) and omit Option 2 when it doesn't apply.
- **Deploy-first samples** (e.g. A2A) may lead with deployment instead of a local
  run. Keep the section order sensible for the scenario.

Use the template for structure and shared vocabulary, and keep whatever
sample-specific sections a reader needs.
