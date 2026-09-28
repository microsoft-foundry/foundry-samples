# Quick Guide: Creating and Validating Samples

This guide provides the minimum steps to create a sample in this repository and configure its validation.

---

## Minimal Requirements for a Sample

Samples live under `samples/<language>/<sample-folder>/` (build-readiness languages: `csharp`, `java`, `python`, `typescript`, and `go`; pass `typescript` to the validator for JavaScript samples, Go is local/PR-only, and Rust is currently unsupported by build readiness).

> **Note:** `validate-sample.sh` itself only accepts `csharp`, `python`, `typescript`, `java`, and `go` as a `--language` value. CI maps `javascript` samples to the `typescript` validator automatically, but if you invoke the script directly (see Option 2 below), pass `--language typescript` for JavaScript samples — passing `--language javascript` will fail. Daily cadence discovery does not currently enable Go samples.

A sample is **defined and discovered** by the presence of a `sample.yaml` file in its root directory.

---

## Scenario A: Create a File/Sample Added to Full Runs (CI & Daily Cadence)

To have your sample automatically discovered and validated in PR checks and the daily validation fleet:

1. **Place your sample files** under `samples/<language>/<sample-name>/`.
2. **Add a `sample.yaml` file** in the sample's root directory:

```yaml
name: Sample Name
description: Brief description of what the sample demonstrates.

# Optional: Custom build & compile overrides (language defaults used if omitted)
build: "pip install -r requirements.txt"
validate: "python -m py_compile *.py"

# Optional: Opt-in to live-service execution during full runs
live_service_validation:
  command: "python main.py"
  required_env:
    - FOUNDRY_PROJECT_ENDPOINT
    - FOUNDRY_MODEL_DEPLOYMENT
```

For completeness, here is the full `sample.yaml` as it looks for a real quickstart sample:

```yaml
name: Quickstart Create Agent
description: Basic quickstart sample demonstrating Microsoft Foundry agent creation.

build: "pip install -r requirements.txt"
validate: "python -m py_compile *.py"
live_service_validation:
  command: "python quickstart-create-agent.py"
  required_env:
    - FOUNDRY_PROJECT_ENDPOINT
    - MODEL_DEPLOYMENT
  cleanup_resources:
    - type: foundry_agent_versions
  substitutions:
    - file: quickstart-create-agent.py
      replacements:
        - placeholder: "your_project_endpoint"
          env: FOUNDRY_PROJECT_ENDPOINT
        - placeholder: "gpt-5-mini"
          env: MODEL_DEPLOYMENT
        - placeholder: "your-agent-name"
          generate: unique_name
```

### How Full Runs Process This:
- **Build Readiness:** Always runs build/compilation checks on PR touches and daily cadence.
- **Live-Service Run:** The sample-owned `live_service_validation.command` is run only during the daily validation pilot (and when invoked locally, as shown below); it is not executed by the PR workflow.
- **Environment variables:** Use the `FOUNDRY_PROJECT_ENDPOINT` / `FOUNDRY_MODEL_DEPLOYMENT` names in `required_env` — the daily cadence provides these. (The older `AZURE_AI_PROJECT_ENDPOINT` / `MODEL_DEPLOYMENT` names are still provided too, for backward compatibility, but new samples should use the `FOUNDRY_` names.)

### Handling Hardcoded "Provide Your Own" Placeholders

Some quickstart samples intentionally keep copy/paste instructional placeholders in
source (for example `"your_project_endpoint"`), so readers have an obvious spot to
paste their own values. Live-service validation still needs the real value at
runtime. Declare a `substitutions` list under `live_service_validation` to have the
validator patch the placeholder in the workflow checkout, using an environment
variable, before running the command:

```yaml
live_service_validation:
  command: "python quickstart-create-agent.py"
  required_env:
    - FOUNDRY_PROJECT_ENDPOINT
  substitutions:
    - file: quickstart-create-agent.py
      replacements:
        - placeholder: "your_project_endpoint"
          env: FOUNDRY_PROJECT_ENDPOINT
```

- `file` must be a path inside the sample directory to a regular, non-symlinked text file.
- Each `replacements` entry maps an exact-match `placeholder` string to an `env`
  variable that must be non-empty, or to `generate: unique_name` (see next section).
- The validator rejects the whole declaration as an infrastructure error (`2`) if a
  target file is missing, outside the sample directory, malformed, or does not
  contain the placeholder — nothing is partially rewritten.
- Only the declared placeholder is replaced; other instructional strings (like an
  agent name meant to stay sample-owned) are left untouched.

### Cleaning Up Live-Service Resources

If your sample's live-service command creates a Foundry Agent (most quickstarts
do), add `cleanup_resources` so the resource is deleted automatically after the
run instead of being left behind in the shared project:

```yaml
live_service_validation:
  command: "python quickstart-create-agent.py"
  cleanup_resources:
    - type: foundry_agent_versions
  substitutions:
    - file: quickstart-create-agent.py
      replacements:
        - placeholder: "your-agent-name"
          generate: unique_name
```

- `cleanup_resources` currently supports exactly one `type`:
  `foundry_agent_versions`. It needs no other fields.
- It must be paired with a `generate: unique_name` substitution (see above) —
  the validator generates one unique agent name per run and reuses it for
  every `generate: unique_name` placeholder in the sample, then passes that
  same name to cleanup. Declaring `cleanup_resources` without a paired
  `generate: unique_name` substitution is an infrastructure error, since
  cleanup would otherwise have no name to scope itself to.
- Nothing else is required — no environment variable, no workflow wiring, no
  sample-owned code to record or report what was created.
- Despite the single `type` name, this one declaration already sweeps more
  than just the agent: it deletes the agent's versions, the agent itself (if
  it did not exist before the run), and any conversations created against
  that agent name (via the Foundry conversations API's `agent_name` filter).
  This is safe without a separate snapshot for conversations, because an
  agent name that's fresh for this run cannot have pre-existing conversations
  attached to it. If your sample doesn't create a conversation, there's
  simply nothing to delete there.
- There is currently no other supported `type` value — `foundry_agent_versions`
  is the only one, and it's the one to use for any sample that creates an
  agent (with or without a conversation). A sample that creates a Foundry
  resource that can't be scoped this same way (for example, an actual Azure
  Resource Manager resource like a new project, which has no relationship to
  the generated agent name) isn't covered by `cleanup_resources` today; if you
  hit that case, check with the sample-validation maintainers before adding
  one — a new `type` would need matching support in
  `.github/scripts/live-resource-cleanup.py`.

---

## Scenario B: Create a File/Sample Validated Without Full Run

Use this when you don't want (or aren't ready) to opt into automatic live-service
runs in CI/daily cadence — either because you're still iterating, or because the
sample should never call a live service in automation. `sample.yaml` is still
recommended (and required for automation to discover the sample at all), but
these options avoid triggering a live-service run in the shared pipeline.

### Option 1: Build-Readiness Only (No Live Execution in CI)
Include `sample.yaml` but **omit** the `live_service_validation` block.
- The sample is still discovered and compiled/checked for build readiness by PRs
  and the daily cadence (that part of "full run" still happens automatically).
- No sample-owned live-service command is run by CI/daily cadence, because there's nothing declared for it to run. The PR `trusted` check still performs its repository-level warm-project smoke.

### Option 2: Run Validation Yourself, On Demand
Instead of waiting for CI or the daily cadence to pick up your sample, invoke the
same validator script yourself, locally, whenever you want a quick check. This
works whether or not the sample has a `sample.yaml` — without one, the script
falls back to the language's default build/compile check; with one, it honors any
declared `build`/`validate`/`test` commands or `live_service_validation` block.

```bash
# Validate build readiness locally
bash .github/scripts/validate-sample.sh \
  --language <language> \
  --sample-dir samples/<language>/<sample-name>

# Validate live-service execution locally (only meaningful if
# live_service_validation is declared in sample.yaml)
SKIP_PROVISION=true bash .github/scripts/validate-sample.sh \
  --mode live-service \
  --sample-dir samples/<language>/<sample-name>
```

This is just you running the script directly — it never registers the sample with
CI or the daily cadence. Those still only pick up samples that have `sample.yaml`.

---

## Reference Documentation
For detailed contracts and workflow specifications:
- [Per-Sample Validation Contract](.github/scripts/validate-sample.README.md)
- [Daily Validation Cadence](.github/validation-pilot.README.md)
- [Changed-Sample Detector](.github/scripts/detect-changed-samples.README.md)
- [Contributing Guide](CONTRIBUTING.md)
