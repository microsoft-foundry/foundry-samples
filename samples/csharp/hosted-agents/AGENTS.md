# Coding Agent Instructions — C# hosted-agent samples

Conventions for AI agents creating or editing samples under
`samples/csharp/hosted-agents/`. Agents read the nearest `AGENTS.md` up the
tree, so this applies to C# hosted-agent samples. Treat these as shared
conventions and a starting point — adapt to what each sample actually needs.

## Cloud E2E contract for new samples

Every new C# hosted-agent sample must add a public `test-spec.yml` with a
responsible Microsoft owner alias, supported experiences, deterministic turns,
and assertions for its defining behavior. Legacy payload/default support is for
migration and is not sufficient for a new sample.

Read and follow the authoritative [hosted-agent cloud E2E test-spec schema and
onboarding checklist](../../../.azure-pipelines/hosted-agent-tests/README.md).
Run both the documented `validate` and protocol-aware `plan` commands before
submitting changes.

## README conventions

Most samples follow the shared template,
[`README-template.md`](./README-template.md): a good default is to copy it and
fill in the `{{placeholders}}`. It keeps a familiar section flow:

1. What this sample demonstrates
2. How it works — plus any sample-specific background (e.g. "Environment
   variables", "Architecture", "Features")
3. Prerequisites — what the *sample* needs: a Foundry project + model deployment,
   the **.NET 10 SDK**, and (only if applicable) RBAC roles, extra Azure
   resources, and environment variables / secrets
4. Option 1: Azure Developer CLI (`azd`) — init → provision → run → invoke →
   deploy → invoke-deployed
5. Option 2: VS Code (Foundry Toolkit) — the one-click **F5** run-and-debug flow
   (Agent Inspector opens automatically) and/or a manual run (`dotnet restore` →
   configure env → `az login` → `dotnet run`) → open the Agent Inspector → deploy
6. Any sample-specific deep-dive sections (customization, advanced demos, reference)
7. Troubleshooting
8. Next steps

## Conventions worth keeping

- Prefer the current CLI commands (the template reflects these; avoid older
  forms such as `azd ext install azure.ai.agents`).
- Prefer self-contained READMEs over deferring run/deploy steps to a parent
  README or hiding steps inside collapsible `<details>` blocks.

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

> The per-sample `AGENTS.md` (hosted-agent overview, `azd` lifecycle, Microsoft
> Foundry Skill) still applies; this file only adds README conventions.
