# Azure DevOps sample pipelines

This directory contains the cloud validation pipeline source for public sample
contributions. Azure DevOps runs these YAML files; committing them does not create
or authorize an Azure DevOps pipeline.

| Pipeline | Scope | Execution |
|---|---|---|
| [hosted-agents-samples-ci.yml](hosted-agents-samples-ci.yml) | Python/C# hosted agents and their test fixtures | Changed samples on PRs; full discovery on relevant `main` pushes, daily at 09:00 UTC, and manual runs |
| [private-bicep-pr-ci.yml](private-bicep-pr-ci.yml) | Bicep infrastructure templates and diagnostic tooling | Changed templates on PRs and `main` pushes; manual `samplePath` or `validateAll` |

The GitHub [policy checks](../.github/workflows/hosted-agent-policies.yml) remain
credential-free. The public `trusted` check and
[daily validation cadence](../.github/validation-pilot.README.md) are separate
from these deployment pipelines.

## Files and shared contracts

```text
.azure-pipelines/
  hosted-agents-samples-ci.yml
  private-bicep-pr-ci.yml
  hosted-agent-tests/<language>/<full-sample-path>/
    test-spec.yml
    test-payload.txt
  scripts/
    hosted-agents/
    bicep/
```

Fixture paths preserve the complete path below `samples/<language>/hosted-agents/`.
The [test-spec reference](hosted-agent-tests/README.md) defines owners, turns,
assertions, approvals, and supported evidence. Legacy payloads remain supported;
`test-spec.yml` takes precedence when both exist.

Both the GitHub policy and ADO runner use
[`hosted_agent_fixture.py`](../.github/scripts/hosted_agent_fixture.py) and
[`hosted_agent_test_spec.py`](../.github/scripts/hosted_agent_test_spec.py).
Keep these helpers shared rather than copying a separate schema into the ADO
scripts.

## Activation prerequisites

A repository/pipeline administrator must complete these separately:

1. Create Azure DevOps pipeline definitions connected to
   `microsoft-foundry/foundry-samples`, selecting the YAML paths above and `main`
   as the default branch.
2. Authorize the GitHub connection to read this repository and report build
   results. Authorize each variable group and Azure service connection only for
   the intended pipelines.
3. Disable fork PR builds for these credentialed pipelines in Azure DevOps.
   Keep fork secrets and full-access tokens disabled. Use resource approvals and
   checks to enforce the intended trust boundary before granting cloud access.
4. Supply the test-resource configuration below. Use separate disposable test
   resources with permissions for deployment, invocation, evidence retrieval and
   cleanup; never production resources.

The YAML also gates PR runs on `System.PullRequest.IsFork` being explicitly
`False`. Missing or true values skip the cloud path. This is defense in depth,
not a substitute for Azure DevOps authorization: a PR can change its YAML.
Skipped cloud runs are not evidence of a successful live test.

Service-connection, variable-group and required-status settings are external to
this repository. These files do not alter GitHub merge rules or activate a
deployment workflow in GitHub Actions.

## Hosted-agent configuration

The pipeline reads the existing variable-group name `samples-hosted-agents-ci`.
It fails when required configuration is absent. `CLOUD_E2E_ENABLED=false` is an
explicit operational opt-out, not a passing validation result.

| Setting | Purpose |
|---|---|
| `AZURE_SERVICE_CONNECTION` | Azure DevOps service connection used by `AzureCLI@2` |
| `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` | Test subscription/resource group |
| `AZURE_AI_PROJECT_ID`, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_PROJECT_NAME` | Foundry test project |
| `AZURE_CONTAINER_REGISTRY_ENDPOINT`, `AZURE_OPENAI_*`, `MODEL_*` | Registry and model configuration required by selected samples |
| `SKIP_PROVISION` | Use the configured warm resources instead of provisioning where supported |
| `TOOLBOX_ENDPOINT_NCUS` | Toolbox combinations, one `label=url\|query` per line; empty skips toolbox samples |
| `TOOLBOX_PROJECT_*`, `TOOLBOX_MODEL_DEPLOYMENT_NAME` | Optional dedicated toolbox project/model settings |
| `CLOUD_E2E_CODE_DEPLOY_ENABLED` | Set `false` to run only the container deployment variant |
| `GH_PAT`, `PLAYWRIGHT_SERVICE_ACCESS_TOKEN` | Optional sample-specific secrets; store as secret variables, never in YAML |
| `AZURE_AI_RAI_POLICY_ID`, `CONTENT_SAFETY_TEST_PROMPT` | Optional content-safety validation configuration |

The runner forwards configured variables through its existing prefix allow-list.
Read the runner's configuration phase when a sample introduces a new variable.
Missing optional configuration may exclude combinations or skip special probes;
review the discovery log rather than treating a smaller matrix as full coverage.

Discovery reads hosted-agent `azure.yaml` files. Exclusions are maintained in two
central lists:

- [`scripts/hosted-agent-samples-ci-skiplist`](scripts/hosted-agent-samples-ci-skiplist)
  excludes the whole sample and exempts it from the new-sample contract policy.
- [`scripts/hosted-agent-samples-code-ci-skiplist`](scripts/hosted-agent-samples-code-ci-skiplist)
  excludes only code deployment; container validation and the contract policy remain.

Use one exact repository-relative sample directory per line, without globs or a
trailing slash. Blank lines and full-line `#` comments are allowed; add a comment
explaining each exclusion. Missing or malformed lists fail validation.
PR changes to either list or shared runner code exercise the full matrix;
sample or fixture changes select the
affected samples. The matrix is sharded by language and expanded by deployment
mode and applicable toolbox combinations.

The runner deploys, waits for readiness, creates sessions, invokes declared
turns, evaluates available evidence, and cleans up session/toolbox resources.
Each job publishes diagnostics and its result. The summary publishes
`sample-status` and a build summary; it does not publish private commit statuses.
Voice Live uses a dedicated smoke client and audio fixture under the hosted-agent
scripts.

### Migration coverage limits

The initial port includes 29 behavior contracts and 45 legacy payloads for
samples already present publicly.

The two lists preserve the existing 16 whole-sample and five code-only exclusions.
Their comments record the reasons rather than per-sample marker files; this
avoids turning unsupported protocols or credential-dependent samples into
accidental new CI targets.

The contract for
`python/agent-framework/responses/21-harness-scaling-capabilities` expects the
`place_trade` MCP approval sequence. The public sample currently declares
`never_require`, unlike the implementation that supplied the contract, so its
live assertion will fail until the public sample restores that approval
behavior. The contract is preserved; this migration does not relax the assertion
or add a new skip to hide the mismatch.

## Bicep configuration

For compatibility, the pipeline retains the existing variable-group name
`foundry-samples-private-bicep-ci` and service-connection name
`infrastructure-template-validation`. These names refer to Azure DevOps resources,
not a GitHub repository binding. Authorize them for the new public-connected
definition, or change both the YAML and the corresponding configuration.

Configure `AZURE_SUBSCRIPTION_ID`, `CI_LOCATION`, and `CI_LOCATION_FALLBACK`.
`CI_MODEL_NAME` and `CI_MODEL_VERSION` can override the deployment model defaults.
The identity needs permission to create/delete temporary resource groups and
their resources, and to configure the diagnostic project's data-plane access.

The pipeline compiles selected Bicep files, validates the Azure connection, then
deploys temporary resource groups. Pipeline/diagnostic-only changes select
`00-basic` as a smoke template. A primary-region deployment failure remains a
failure even if fallback-region diagnostics succeed.

Diagnostics use the existing public
[diagnostic-agent sample](../samples/python/hosted-agents/bring-your-own/invocations/diagnostic-agent).
When no Foundry project is deployed, or the runner cannot reach a private-only
project, the helper reports that data-plane diagnostics were skipped; ARM
deployment success alone is not proof of data-plane connectivity.
Set `DIAGNOSTIC_PRIVATE_ENDPOINT_ACCESS=true` only on a runner with that access.
The deployment job schedules resource-group cleanup on exit.

## Offline regression checks

The existing [scripts self-test workflow](../.github/workflows/scripts-selftest.yml)
runs the migrated Python/shell harnesses, checks all published fixture mappings
and schemas, exercises Bicep file selection with a mocked Azure CLI, and parses
shell scripts. These tests do not authenticate to Azure or deploy samples.

Run from the repository root on Linux or Git Bash with Python 3.13, Bash, Git,
`jq`, and Mike Farah's `yq` available:

```bash
python -m pip install -r .github/scripts/requirements.txt
python -m unittest discover -s .azure-pipelines/scripts/hosted-agents/tests -p 'test_*.py'
bash .azure-pipelines/scripts/hosted-agents/tests/test-hosted-agent-ci-toolboxes.sh
bash .azure-pipelines/scripts/hosted-agents/tests/test-hosted-agent-session-quota.sh
python .github/scripts/test/test_ado_pipeline_fixtures.py
python .azure-pipelines/scripts/bicep/test_bicep_pipeline.py
```

Live coverage requires an authorized Azure DevOps run after setup. Successful
offline tests do not claim that service connections, cloud quota, or deployments
have been validated.
