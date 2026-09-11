# Daily public validation cadence

The [Daily public validation cadence](workflows/validation-pilot.yml) runs at
07:00 UTC and supports manual dispatch from GitHub Actions. A newer run cancels
an older in-progress run.

## Discovery and eligibility

At the checked-out commit, discovery sorts every
`samples/**/sample.yaml`, derives a stable ID from its path, and emits the
schema-v2 manifest and matrices used by that run. There is no static sample
matrix to update.

Discovery handles ineligible metadata deterministically:

- Unreadable or invalid YAML remains in the manifest and produces
  `skipped/not-completed` with the metadata error as its reason.
- A language not enabled by cadence discovery remains in the manifest and
  produces `skipped/not-completed` with an unsupported-language reason.
- Duplicate derived IDs, metadata that is not a regular file inside the
  repository, and the legacy top-level `l4` key fail discovery.

The cadence currently enables C#, Java, Python, and TypeScript. JavaScript maps
to the TypeScript/Node.js validator. Go is supported by the local and
pull-request validator but is not yet enabled by full-fleet discovery. Rust
Build readiness is not supported.

This eligibility handling does not move files, count strikes, or quarantine
samples. Automated reaction and quarantine remain unfinished.

## Validation sequence and caller policy

Samples without a `live_service_validation` declaration run in the
credential-free Build-readiness matrix. Declared samples run in a separate
credentialed matrix leg that performs Build readiness first and runs the
sample-owned Live-service command only after readiness passes. The matrices use
`fail-fast: false`, so one sample result does not cancel unrelated samples.

The current cadence uses an existing warm project and sets
`SKIP_PROVISION=true`; it does not provision resources. Its GitHub environment
is named `L4-validation` only because that legacy external identifier is part
of the GitHub/Entra OIDC configuration. `L4` is not a current validation
concept.

See the [per-sample validation contract](scripts/validate-sample.README.md) for
local commands, Build-readiness behavior, Live-service metadata, and result
classification.

## Results and report

Every matrix leg uploads a `validation-pilot-{sample-id}` artifact containing
`sample-result.json` and `diagnostics.log` for 30 days. The completeness job
combines those artifacts with the exact generated manifest and uploads
`validation-pilot-run-{run-id}-{attempt}` for 90 days.

Producers write schema v2. Completeness and report readers also accept
historical schema-v1 artifacts and translate their legacy completed-stage
labels for display. A result contains sample identity, outcome, completed
stage, duration, artifact references, completion time, and GitHub run metadata.

The `report / report` job writes the run-scoped report to the GitHub Actions job
summary. It puts actionable records first, includes sanitized diagnostic
excerpts and links to samples at the validated commit, and collapses passing
records. Use the per-sample or consolidated artifact for full diagnostics.

Outcomes mean:

| Outcome | Interpretation |
|---|---|
| `passed` | The requested validation sequence completed successfully. |
| `sample failure` | Sample-owned code, dependencies, or assertions failed. |
| `infrastructure/error` | The validator or caller environment could not complete a valid check. |
| `skipped/not-completed` | Discovery retained the sample but current eligibility prevented execution. |

Completeness fails when a discovered sample has no result, a duplicate or
malformed result, an identity mismatch, or a missing diagnostic. A reported
sample failure is complete data even though it requires maintainer attention.

Open the
[workflow runs](https://github.com/microsoft-foundry/foundry-samples/actions/workflows/validation-pilot.yml)
to inspect the latest report and artifacts.

## Dashboard

The `publish-dashboard` job renders every manifest sample's latest outcome to
a durable static page on GitHub Pages, so "what's currently passing" has one
stable URL instead of requiring you to open the latest scheduled run. It only
publishes from scheduled/dispatched runs on this repository's `main` branch,
uses its own `pages` concurrency group so a manual dispatch can't race a
scheduled deployment, and republishes (with a visible banner) even when a run
is incomplete rather than leaving a stale prior deployment looking current.
New samples require no dashboard changes: like the report, it renders
whatever discovery's manifest already contains, so a sample with a
`sample.yaml` appears the next time the cadence runs. The dashboard doesn't
inline diagnostic text — instead it links each sample's status to its job
run for logs, and links to that sample's diagnostics artifact for download
when one was uploaded, alongside stage, duration, completion time, and
codeowner. Failed and errored rows also provide a **Fix with Copilot** action.
The action opens a prefilled issue for review with the sample, run, job, and
artifact context and assigns it to Copilot when submitted; Copilot then
investigates the failure and opens a pull request.

The dashboard's **Validation** column uses short reader-facing labels: **Build
check** for local/static validation, **Live run** for samples executed against
the warm Azure AI Foundry project, and setup/reporting labels for infrastructure
or handoff failures. Its filter panel is collapsed by default with a one-line
summary of the visible rows; expanding it exposes filters for status, language,
validation type, and codeowner.

## Current limits

The delivered cadence is daily/manual and warm-project only. Cold provisioning,
automated reaction or quarantine, broader Live-service coverage, and Rust Build
readiness remain unfinished. The daily report is diagnostic evidence; it does
not replace the pull request's required `trusted` merge check.
