# Prompt-Agent E2E Tools

Tools for the separate prompt/managed Azure Pipeline, without changing hosted
orchestration or the GitHub contract policy:

- `discover_samples.py`: sample discovery and matrix hydration.
- `run-prompt-agent.sh`: azd lifecycle orchestration and cleanup.
- `prompt_agent_helpers.py`: local manifest/contract validation and evidence handling.
- `cleanup-prompt-agent.sh`: recovery of recorded resources from a retained workspace.
- `summarize_results.py`: aggregation of expected matrix-cell results.

Python 3.10+ and PyYAML are required. Discovery and validation reuse the
shared fixture resolver and contract planner/evaluator under `.github/scripts/`.

## Discovery

Run from the repository root:

```sh
python .azure-pipelines/scripts/prompt-agents/discover_samples.py discover
python .azure-pipelines/scripts/prompt-agents/discover_samples.py discover --mode changed --base-ref origin/main
python .azure-pipelines/scripts/prompt-agents/discover_samples.py discover --sample-filter 01-basic,03-mcp-tools
python .azure-pipelines/scripts/prompt-agents/discover_samples.py discover --validate-contracts
```

Discovery scans `azure.yaml` under the configured sample roots and excludes
exact sample paths listed in the CI-local `blacklist.json`. The blacklist maps
repository-relative sample directories to nonempty exclusion reasons; use `{}`
for no exclusions. No marker files are needed in sample directories, and prompt
discovery does not consult `.ci-skip`. Contracts are not the source of the sample list.

Discovery emits a JSON document to stdout; errors go to stderr with a nonzero
exit code. Each sample produces one record. `matrix_all`, `matrix_prompt`, and
`matrix_managed` contain only combo IDs, with their full records in `entries`.
Publish that `entries` array as `entries.json` for later job hydration:

```sh
python .azure-pipelines/scripts/prompt-agents/discover_samples.py hydrate --entries entries.json --combo-id cli-prompt-agents-01-basic
```

Hydration emits exactly one JSON record, rejecting missing or duplicate matches.
It does not emit Azure logging commands or execute the record.

Changed mode compares committed HEAD against the merge base, not staged or
working-tree edits. Sample and fixture changes select their owning sample;
changes to this CI directory, the prompt pipeline, or the shared fixture/planner
modules select all candidates, including when `blacklist.json` changes. Deleted
manifests are not discovered. PR runs use changed mode against their target
branch; pushes, schedules, and default manual runs use all mode. The blacklist
takes precedence; the optional filter (`*` for all) narrows selected candidates
by case-insensitive OR substring matching
on combo ID, sample path, or sample name. Invalid selected manifests fail before
manual filtering rather than disappearing from a successful matrix.

Discovery does not deploy or invoke agents. A discovered sample must also satisfy
the lifecycle runner's manifest and contract requirements before execution.

`--validate-contracts` requires a valid contract for every non-skipped sample
before applying changed/manual filters. Unsupported manifests, invalid profiles,
and incompatible contracts fail validation. Existing fixture paths must map to
real samples, even for skipped samples, but the blacklist exempts a sample from
contract/capability validation. Removing a contract does not remove its sample
from discovery; validation fails instead. Each profile matrix is limited to 256 jobs.

The [Azure Pipeline](../../prompt-agents-samples-ci.yml) enables contract
validation; see its [configuration](../../README.md#prompt-and-managed-agent-e2e).

Tests do not access Azure:

```sh
python -m pip install -r .azure-pipelines/scripts/prompt-agents/requirements.txt
python -m unittest discover -s .azure-pipelines/scripts/prompt-agents/tests -p 'test_*.py'
```

## Adding Sample Roots

Discovery currently scans `samples/cli/prompt-agents`. To add another sample
root, update `SAMPLE_ROOTS` in `discover_samples.py` and its matching layout
in `.github/scripts/hosted_agent_fixture.py`.

The record's `sampleLanguage` is `cli` for these language-agnostic manifests;
classification, filtering,
IDs, profile matrices, and hydration need no language-specific branches. Every
configured root must exist. Update offline CI path triggers to include newly
enabled roots.

## azd Prompt Lifecycle

`run-prompt-agent.sh` validates the azd end-to-end user experience, not direct
SDK invocation. Bash owns command sequencing, timeouts, and EXIT-trap cleanup.
`prompt_agent_helpers.py` handles only local manifest/contract validation, text
evidence, and exact-target absence parsing; the shared Python evaluator is reused.
The runner supports string inputs and assistant-text assertions for plain prompt
agents and managed-harness prompt agents (any valid `harness.type` identifier). Managed manifests must declare
one project, one agent, and one toolbox containing only built-in
`web_search`. Skills, connections, additional dependencies, and lifecycle hooks
are rejected before deployment. This is capability validation, not a sample-name
allowlist.

`requirements.txt` contains only PyYAML; Azure/OpenAI Python SDKs are not used.
The runner requires Bash, jq, GNU timeout/coreutils, and Python 3.10+. Set
`PYTHON` if the interpreter is not available as `python3`. Live execution needs
Azure CLI and azd authenticated to the same tenant, the `microsoft.foundry`
extension, access to a Foundry project and model deployment (existing or
created for the disposable mode).
The pipeline defaults to `SKIP_PROVISION=true` in its variable group. To test
disposable provisioning instead, set `SKIP_PROVISION=false`, configure
`AZURE_SUBSCRIPTION_ID` and `AZURE_LOCATION`, and grant the service connection
permission to create/delete resource groups, Foundry projects, and model
deployments in a dedicated test subscription. The provisioning helper copies
the selected sample's model declaration into an isolated workspace, checks the
resource group is unused, records ownership before creation, and verifies its
project endpoint against ARM. Init creates the azd environment inside a fresh
target directory; the runner then pins and verifies its subscription, location,
and resource group before provisioning. After agent cleanup, a separate authenticated
step checks ownership and runs `azd down` only for the cell-owned resource
group; its verified deletion is required for a passing summary. Failed
provisioning or worker loss can still require manual orphan cleanup.

Before enabling `SKIP_PROVISION=false` for automatic PR builds, validate one
authorized manual `01-basic` cell in a disposable subscription: record its
`provision-ledger.json`, check that `result.json` passed and
`teardown-result.json` reports `passed`, then independently query the recorded
resource group and confirm it no longer exists. Repeat with an intentionally
failed deployment to exercise partial-provision teardown. The shell tests use
fake Azure commands and do not establish that the real provider or service
connection can provision, invoke, or delete resources.

The following command deploys and invokes a temporary agent and can incur model
charges. Use a dedicated CI project. The runner resolves the sample's fixture
`test-spec.yml` by default; use `--spec <path>` to supply a different contract:

```sh
bash .azure-pipelines/scripts/prompt-agents/run-prompt-agent.sh \
  --sample samples/cli/prompt-agents/01-basic \
  --project-id /subscriptions/SUB/resourceGroups/RG/providers/Microsoft.CognitiveServices/accounts/ACCOUNT/projects/PROJECT \
  --project-endpoint https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT \
  --model-deployment EXISTING_DEPLOYMENT \
  --artifacts /path/to/new-run-artifacts
```

The adapter verifies the endpoint against the ARM project, adopts a temporary
manifest with a unique agent name, replaces the literal model with the selected
existing deployment, and removes model provisioning declarations. Managed runs
also give the toolbox a unique name and update both `uses` and `toolbox.name`.
The runner deploys the owned toolbox before the agent and verifies that the
agent's MCP attachment matches its versioned endpoint. It never calls
`provision`, `up`, or `down`. The original sample is unchanged. The artifacts
directory must be new and outside the sample.

Each turn executes `azd ai agent invoke <service> --input-file <text-file>`.
The first turn of every test adds `--new-conversation`; azd manages subsequent
turn state. Inputs must be strings. Raw assertions and structured message arrays
are rejected before any Azure call, including when their test is filtered out.
The adapter records exit codes, stdout, and stderr. Assistant text is stdout
minus azd's single display newline; original stdout is preserved. CLI semantic
error handling is part of what this test validates, not duplicated via an SDK.
The runner never retries invoke; retry behavior inside azd is left unchanged.
MCP approval metadata is marked unobserved, not claimed to be inspected. Managed
toolbox approval policy is left as generated by azd. A premature stream closure
is a failed invoke, not a reason to repost work or switch to SDK polling.

Artifacts include the adopted manifest, commands and versions, ownership ledger,
per-command JSON records and stdout/stderr, normalized text evidence, the shared
evaluator report, and final result. Treat artifacts as restricted: they can contain
prompts, model output, project identifiers, and deployment diagnostics. Tokens
are not passed on command lines or intentionally logged.

Cleanup uses `azd ai agent delete` for the complete uniquely named agent, then
`azd ai agent show` to check absence. Only an exact-target prompt GET reporting
HTTP 404 counts as absent; auth/network/configuration errors fail verification.
This check parses azd's error text and must be revalidated when CLI formatting
changes. Cleanup failures fail the run even if behavior assertions pass.
Logging failures do not prevent an agent deletion attempt.
For managed runs, toolbox deletion is attempted after agent cleanup even if
agent cleanup fails. A successful project-scoped `azd ai toolbox list` must omit
the owned name before or after its deployment; malformed/failed list responses
cannot confirm absence. This relies on the CLI's list pagination and visibility.
Only resources recorded as deployment-attempted are deleted. The in-process
cleanup uses short per-command timeouts to leave cancellation time for the
independently authenticated recovery and infrastructure teardown tasks.
The isolated azd working directory is removed; the ownership ledger remains for
manual recovery. This is not an orphan-cleanup service.

Set `PROMPT_AGENT_KEEP_WORKSPACE=true` to retain the workspace for a subsequent
cleanup task on the same worker. `cleanup-prompt-agent.sh` takes `--artifacts`,
`--project-id`, `--project-endpoint`, and `--model-deployment`; it checks the
ownership ledger and retained manifest before attempting pending cleanup. It
never initializes a missing workspace or upgrades a failed/missing E2E result
to passed. Its `recovery-result.json` describes cleanup only; a missing or
failed recovery result cannot produce a passing matrix summary. A missing worker
or a deployment completing after recovery still requires orphan reclamation.

The runner does not collect raw response JSON or per-turn response IDs, or delete
individual responses. Response/conversation retention is explicitly unverified
in the result; agent deletion is not proof that those records were deleted.
Terminal output is not raw response evidence.

`--turn-timeout` uses GNU timeout with a ten-second kill grace period. The EXIT
trap attempts cleanup on failure, INT, and TERM; SIGKILL or worker loss cannot
run the trap. Terminating local processes does not prove service-side work
stopped. Deployment timeouts have the same remote-work caveat. Azd stores
conversation pointers in user config; use a dedicated CI worker/config and
serialize invocations on that config rather than running parallel jobs against
a developer's azd state. Unique names prevent intentional cross-test reuse but
do not solve concurrent config-write races. Agent deletion also does not verify
identity/RBAC reclamation.

The lifecycle and recovery tests execute the real Bash runner against fake
az/azd executables without calling Azure. Set
`PROMPT_AGENT_TEST_BASH` to Git Bash on Windows and put jq on PATH to run them
there. They skip explicitly if shell tools are absent.
