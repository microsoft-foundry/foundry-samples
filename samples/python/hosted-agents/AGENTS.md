# Coding Agent Instructions — Python hosted-agent samples

Conventions for AI agents creating or editing samples under
`samples/python/hosted-agents/`. Agents read the nearest `AGENTS.md` up the
tree, so this applies to Python hosted-agent samples. Treat these as shared
conventions and a starting point — adapt to what each sample actually needs.

## Starting a new sample

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

## Python dependency policy

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

## Cloud E2E contract for new samples

Every new Python hosted-agent sample must add a public `test-spec.yml` with a
responsible Microsoft owner alias, supported experiences, deterministic turns,
and assertions for its defining behavior. Legacy payload/default support is for
migration and is not sufficient for a new sample.

Read and follow the authoritative [hosted-agent cloud E2E test-spec schema and
onboarding checklist](../../../.azure-pipelines/hosted-agent-tests/README.md).
Run both the documented `validate` and protocol-aware `plan` commands before
submitting changes.

## Runtime logging

Use the standard `logging` module for diagnostics emitted by a running hosted
agent. Prefer `logger.info()`, `logger.warning()`, and `logger.exception()` over
`print()` when output must be observable while the long-running process remains
alive; Python stdout may remain buffered in hosted containers.

Use `print()` only when stdout is intentionally part of a CLI, provisioning
script, local test utility, or tool-result contract. If stdout is required from a
long-running process, flush it explicitly. E2E log assertions must target a
deliberate sample-owned log event, not mutable framework or dependency wording.

## README conventions

Most samples follow the shared template,
[`README-template.md`](./README-template.md). It keeps a familiar section flow:

1. What this sample demonstrates
2. How it works — plus any sample-specific background (e.g. "Environment
   variables", "Architecture", "Features")
3. Prerequisites — what the *sample* needs: a Foundry project + model deployment,
   **Python 3.10+**, and (only if applicable) RBAC roles, extra Azure resources,
   and environment variables / secrets
4. Option 1: Azure Developer CLI (`azd`) — init → provision → run → invoke →
   deploy → invoke-deployed
5. Option 2: VS Code (Foundry Toolkit) — the one-click **F5** run-and-debug flow
   (Agent Inspector opens automatically) and/or a manual run (`python main.py`)
   → open the Agent Inspector → deploy
6. Any sample-specific deep-dive sections (customization, advanced demos, reference)
7. Troubleshooting
8. Next steps

## Conventions worth keeping

- Prefer the current CLI commands (the template reflects these; avoid older
  forms such as `azd ext install azure.ai.agents`).
- Prefer self-contained READMEs over deferring run/deploy steps to a parent
  README or hiding steps inside collapsible `<details>` blocks.
- Keep Toolkit-generated `.vscode` launch/task files out of the sample; document
  that the Toolkit creates them in the scaffolded workspace.

## When a sample legitimately differs

Not every sample fits the two-option shape, and that's fine — adapt rather than
force it:

- **Command-line-only samples** (e.g. VoiceLive, WebSocket, some A2A samples) may
  have no VS Code / Agent Inspector path. Document the flow they actually support
  (curl / `azd` / a browser client) and omit Option 2 when it doesn't apply.
- **Deploy-first samples** (e.g. A2A) may lead with deployment instead of a local
  run. Keep the section order sensible for the scenario.

Use the template for structure and shared vocabulary, and keep whatever
sample-specific sections a reader needs.
