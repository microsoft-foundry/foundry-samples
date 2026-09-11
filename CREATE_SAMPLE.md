# Quick Guide: Creating and Validating Samples

This guide provides the minimum steps to create a sample in this repository and configure its validation.

---

## Minimal Requirements for a Sample

All samples live under `samples/<language>/<sample-folder>/` (supported languages: `csharp`, `java`, `javascript`, `python`, `typescript`, `go`).

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
    - AZURE_AI_PROJECT_ENDPOINT
    - MODEL_DEPLOYMENT
```

### How Full Runs Process This:
- **Build Readiness:** Always runs build/compilation checks on PR touches and daily cadence.
- **Live-Service Run:** Runs `live_service_validation.command` only if the `live_service_validation` section is present in `sample.yaml`.
- **Environment variables:** The daily cadence provides both `AZURE_AI_PROJECT_ENDPOINT`/`MODEL_DEPLOYMENT` and the equivalent `FOUNDRY_PROJECT_ENDPOINT`/`FOUNDRY_MODEL_DEPLOYMENT` aliases, so `required_env` can reference either naming convention.

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
    - AZURE_AI_PROJECT_ENDPOINT
  substitutions:
    - file: quickstart-create-agent.py
      replacements:
        - placeholder: "your_project_endpoint"
          env: AZURE_AI_PROJECT_ENDPOINT
```

- `file` must be a path inside the sample directory to a regular, non-symlinked text file.
- Each `replacements` entry maps an exact-match `placeholder` string to an `env`
  variable that must be non-empty.
- The validator rejects the whole declaration as an infrastructure error (`2`) if a
  target file is missing, outside the sample directory, malformed, or does not
  contain the placeholder — nothing is partially rewritten.
- Only the declared placeholder is replaced; other instructional strings (like an
  agent name meant to stay sample-owned) are left untouched.

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
- No live-service call is ever made by CI/daily cadence, because there's nothing
  declared for it to run.

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
