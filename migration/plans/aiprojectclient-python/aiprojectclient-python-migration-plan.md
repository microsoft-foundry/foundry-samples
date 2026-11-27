---
ai-usage: ai-assisted
---

# AIProjectClient Python snippet migration plan

Status: Proposed, pending review. Publishing these planning assets doesn't
authorize sample migration, live-service execution, or implementation pull
requests.

Review the [CSV manifest](aiprojectclient-python-migration-manifest.csv) or the
[full JSON manifest](aiprojectclient-python-migration-manifest.json).

Scope: 170 snippets in 106 tracked files, plus the local `.github\AGENTS.md`
example: 171 locations total. Include short snippets and both escaped Python
examples. The destination is
[microsoft-foundry/foundry-samples](https://github.com/microsoft-foundry/foundry-samples),
on `main`.

## 1. Create the migration manifest

Map every location to its scenario, SDK generation, dependencies, destination
file, and named snippet region. Record whether to reuse, extend, or create a
sample. Deduplicate equivalent examples without combining behaviorally different
scenarios or SDK generations. The 171 locations don't automatically become 171
sample files.

Capture source revisions and content hashes so shifting line numbers don't lose
migration coverage.

## 2. Establish canonical, runnable samples

Search existing samples before adding files. Use the destination's existing
organization:

| Source scenarios | Destination |
|---|---|
| Current Foundry examples | Existing scenario folders under `samples\python\`. |
| Classic examples | `samples-classic\python\`, with isolated dependencies. |
| Embedded Python examples | Canonical Python files, with their surrounding templates updated separately. |

Include necessary imports, helpers, assets, setup instructions, dependencies, and
cleanup. Preserve existing behavior. Don't bundle SDK upgrades or unrelated
rewrites into the migration. Review every addition for public-release suitability.

Add stable named regions for documentation excerpts, plus `sample.yaml` and
sample-specific validation. Named regions avoid fragile line-range references.
See the destination's
[sample requirements](https://github.com/microsoft-foundry/foundry-samples/blob/main/CREATE_SAMPLE.md).

## 3. Prove the approach with a small pilot

Use five representative articles: the current SDK overview, file-search tools,
cloud evaluation, the classic SDK overview, and the escaped Codex example.

Review the destination layout, runnable context, rendered excerpts, and
preservation of the teaching sequence before bulk rollout. Embedded examples need
deliberate template edits, not a `:::code` directive inserted inside an existing
Markdown fence.

## 4. Roll out in focused batches

Proceed through SDK and quickstarts; tools, runtime, and structured inputs; hosted
agents, sessions, memory, and voice; observability, evaluation, models, and search;
and remaining classic examples.

For each batch, merge the samples first, then replace documentation fences with
named `:::code` references. Reuse `~/foundry-samples-main/`, which is already
configured in the documentation repository's `.openpublishing.publish.config.json`.
No dependency change is planned. Preserve headings, language tabs, monikers, and
instructional order.
Capture expected output from actual runs rather than inventing it.

Keep the local `.github\AGENTS.md` update separate from the tracked documentation
pull requests.

## 5. Apply release and completion gates

Use same-repository sample branches targeting `main`. Sample-changing fork pull
requests require maintainer promotion to satisfy the required `trusted` gate. See
[CONTRIBUTING.md](https://github.com/microsoft-foundry/foundry-samples/blob/main/CONTRIBUTING.md).

Require sample build-readiness, explicitly authorized live-service runs, valid
named-region references, and successful documentation rendering. Classic
validation needs explicit coverage: the current
[changed-sample detector](https://github.com/microsoft-foundry/foundry-samples/blob/main/.github/scripts/detect-changed-samples.README.md)
scans `samples/`, not `samples-classic/`.

Completion means all 171 manifest entries have a canonical destination and
replacement disposition, every published reference resolves, and none of the
inventoried inline or escaped Python implementations remain duplicated. Any
blocked scenario stays explicitly open rather than being counted as migrated.
