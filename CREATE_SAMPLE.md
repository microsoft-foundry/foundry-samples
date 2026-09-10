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

---

## Scenario B: Create a File/Sample Validated Without Full Run

To validate a sample without running live cloud services during full runs, or to run validation locally on demand:

### Option 1: Build-Readiness Only (No Live Execution in CI)
Include `sample.yaml` but **omit** the `live_service_validation` block.
- The sample will be compiled/checked for build readiness in PRs and daily runs.
- **No live service calls** will be executed during full runs.

### Option 2: Local On-Demand Validation
To test and validate locally before or without committing to full pipeline runs, use the local validation script:

```bash
# Validate build readiness locally
bash .github/scripts/validate-sample.sh \
  --language <language> \
  --sample-dir samples/<language>/<sample-name>

# Validate live-service execution locally
SKIP_PROVISION=true bash .github/scripts/validate-sample.sh \
  --mode live-service \
  --sample-dir samples/<language>/<sample-name>
```

---

## Reference Documentation
For detailed contracts and workflow specifications:
- [Per-Sample Validation Contract](.github/scripts/validate-sample.README.md)
- [Daily Validation Cadence](.github/validation-pilot.README.md)
- [Changed-Sample Detector](.github/scripts/detect-changed-samples.README.md)
- [Contributing Guide](CONTRIBUTING.md)
