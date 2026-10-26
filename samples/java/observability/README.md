# Application Insights for Java agent samples

Use this setup reference for Java samples with an existing agent conversation,
including [Chat with an agent](../quickstart/chat-with-agent). Server-side traces
are collected through the Foundry project's App Insights connection; no Java
agent or additional client exporter is required for this quickstart.

## Configure once per project

Install Azure CLI and Python 3.10+ for the shared setup command. Sign in using
`az login`, then run from the repository root:

```powershell
$env:FOUNDRY_PROJECT_RESOURCE_ID = "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
python .github\scripts\agent_tracing_setup.py --project-id $env:FOUNDRY_PROJECT_RESOURCE_ID
```

The command reuses an existing App Insights connection **unchanged**. Otherwise,
it creates workspace-based App Insights and a project-managed-identity connection,
assigning the required project identity roles. The caller needs resource-creation
and role-assignment permissions.

New identity/connection settings can take 2-5 minutes to propagate. Allow that
time before the first conversation; retry the sample if its initial trace check
preceded propagation. Setup reports configuration, not verified ingestion.
See the [Entra ingestion guidance](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-ingestion-entra-authentication).

Project-wide service tracing can include prompts/responses and incur Azure Monitor
charges. Review collection, access, and retention before enabling it.
`--application-insights-resource-id <component-ARM-ID>` selects a BYO workspace-based
component with local authentication disabled, only if no connection exists.
A conflicting existing connection is not replaced.

Use `--disable` to skip setup. This does not disconnect existing telemetry;
the Java sample can still run without App Insights. Setup failures produce a
warning and nonzero exit; correct prerequisites and rerun for later attachment.

## Run and verify

Use the existing Maven command and fill its current instructional placeholders.
Both conversation turns retain their prompts. Successful responses emit
`Agent response ID: ...` so verification does not accept unrelated/stale traces.

The `sample.yaml` live test runs that conversation and verifies **both** response
IDs in the connected App Insights resource. Set `FOUNDRY_PROJECT_ENDPOINT`,
`FOUNDRY_PROJECT_RESOURCE_ID`, `MODEL_DEPLOYMENT`, and `SKIP_PROVISION=true`
before using the [live validator](../../../.github/scripts/validate-sample.README.md).
Use a disposable checkout because its existing substitutions modify placeholders.
The validator does not provision Azure resources.

The querying identity needs trace-read permission and protected-table access
where applicable. Validate project identity permissions separately. Missing
traces fail; known permission/cloud prerequisites are infrastructure errors.
`FOUNDRY_TRACE_TIMEOUT_SECONDS` adjusts the bounded ingestion wait.

For client-side/framework tracing elsewhere, use instrumentation compatible
with the sample's pinned Java dependencies and close application-owned providers.
Do not add a duplicate exporter to a hosting-managed pipeline.
