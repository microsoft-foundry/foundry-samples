# Application Insights for TypeScript agent samples

Use this setup reference for TypeScript agent samples such as
[Chat with an agent](../quickstart/chat-with-agent). The quickstart's agent
conversation is traced by the Foundry service through its project connection.
It does not need an additional Node.js OpenTelemetry exporter.

## Configure once per project

Install Azure CLI and Python 3.10+ for the common setup command, then `az login`.
Run from the repository root:

```powershell
$env:FOUNDRY_PROJECT_RESOURCE_ID = "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
python .github\scripts\agent_tracing_setup.py --project-id $env:FOUNDRY_PROJECT_RESOURCE_ID
```

Existing App Insights connections are reused **without modification**. If none
exists, setup creates workspace-based App Insights, grants required project
identity roles, and attaches a project-managed-identity connection. The caller
needs the necessary resource-creation and role-assignment permissions.

New identity/connection settings can take 2-5 minutes to propagate. Allow that
time before the first conversation; retry the sample if its initial trace check
preceded propagation. Setup reports configuration, not verified ingestion.
See the [Entra ingestion guidance](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-ingestion-entra-authentication).

This enables project-wide service tracing, potentially including prompts and
responses, and may incur Azure Monitor charges. Review collection, retention,
and reader access before enabling. To supply workspace-based Entra-only App
Insights, add `--application-insights-resource-id <component-ARM-ID>`; setup
never replaces a conflicting existing connection.

`--disable` skips setup without disconnecting existing resources. Running the
agent without App Insights remains supported. A setup warning/nonzero exit means
tracing is not ready; fix the reported prerequisite and rerun the command later.

## Run and verify

Use the quickstart's current npm command and existing source placeholders. The
two conversation turns and cleanup are unchanged. Each successful response emits
`Agent response ID: ...` for execution-specific verification.

Its existing `sample.yaml` live test checks **both** response IDs in the
connected App Insights resource. Set `FOUNDRY_PROJECT_ENDPOINT`,
`FOUNDRY_PROJECT_RESOURCE_ID`, `MODEL_DEPLOYMENT`, and `SKIP_PROVISION=true`
before running the [live validator](../../../.github/scripts/validate-sample.README.md).
Use a disposable checkout for its existing placeholder substitutions.
Validation does not provision resources.

The querying identity needs read access and, for protected tables, appropriate
protected-data access. Check project identity permissions separately. Missing
traces fail verification; known query-access/cloud prerequisites are infrastructure
errors. `FOUNDRY_TRACE_TIMEOUT_SECONDS` adjusts the bounded ingestion wait.

This is project/server tracing, not generic HTTP auto-instrumentation. If adding
client/framework instrumentation elsewhere, initialize it before instrumented
operations, preserve asynchronous context, and await exporter shutdown without
duplicating a framework-managed provider.
