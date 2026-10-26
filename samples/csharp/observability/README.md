# Application Insights for C# agent samples

Use this single setup reference for C# samples that already converse with a
Foundry agent, including [Chat with an agent](../quickstart/chat-with-agent).
The quickstart uses project/server tracing, so it does not need an extra
Application Insights SDK or client exporter.

## Configure once per project

Install Python 3.10+ for the shared setup command and Azure CLI, and sign in with
`az login`. From the repository root:

```powershell
$env:FOUNDRY_PROJECT_RESOURCE_ID = "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
python .github\scripts\agent_tracing_setup.py --project-id $env:FOUNDRY_PROJECT_RESOURCE_ID
```

The same command is used by all four SDK languages. An existing App Insights
connection is reused **unchanged**. If absent, setup creates workspace-based
App Insights, grants the project identity the necessary roles, and attaches a
project-managed-identity connection. Resource creation and role assignment
require appropriate Azure permissions.

When creating a connection, setup serializes cooperating runs with an ETag-protected
temporary `foundry-tracing-setup-lock` project tag. This requires project-write
permission and room for one tag; reusing a connection remains read-only.
An interrupted process can leave the tag behind. After a lock-wait timeout,
remove that tag only after confirming the original setup process has stopped.
Unrelated project tags are preserved.

Setup defaults to the system-assigned identity, or the sole attached user-assigned
identity if no system identity exists. With multiple user-assigned identities,
pass `--user-assigned-identity-resource-id <attached-identity-ARM-ID>`.
This selects the identity receiving RBAC, not the service's runtime identity;
ensure it matches the project's actual tracing identity. Setup does not change
project identities.

New identity/connection settings can take 2-5 minutes to propagate. Allow that
time before the first conversation; retry the sample if its initial trace check
preceded propagation. Setup reports configuration, not verified ingestion.
See the [Entra ingestion guidance](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-ingestion-entra-authentication).

Setup enables project-wide service traces, may capture prompts/responses, and
can incur Azure Monitor costs. Review access, collection, and retention first.
`--application-insights-resource-id <component-ARM-ID>` selects BYO workspace-based
App Insights with local authentication disabled, only when no connection exists.
A conflicting existing connection is not replaced.

`--disable` skips setup without removing existing telemetry. The agent can still
run without App Insights. Setup failures are explicit warnings with nonzero exit;
fix the reported prerequisites and rerun the command to attach tracing later.

## Run and verify

Keep the existing .NET sample flow and placeholders. Each completed turn prints
`Agent response ID: ...` after checking the response completed successfully.

Its `sample.yaml` live test executes the original two-turn conversation and
checks that **both** response IDs appear in connected App Insights. Set
`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_PROJECT_RESOURCE_ID`, `MODEL_DEPLOYMENT`,
and `SKIP_PROVISION=true` before using the
[live validator](../../../.github/scripts/validate-sample.README.md).
Use a disposable checkout because existing substitutions rewrite its placeholders.
The validator only verifies telemetry; it never provisions resources.

The querying identity needs read access to App Insights, plus protected-table
access where applicable. Validate the project identity separately rather than
assuming a developer's successful query proves its access. Missing traces fail;
known permission/cloud prerequisites are infrastructure errors.
`FOUNDRY_TRACE_TIMEOUT_SECONDS` controls the bounded ingestion wait.

This reference does not add ActivitySource subscriptions or exporters. For
framework/client instrumentation, use the matching .NET guidance and dispose
application-owned providers; do not duplicate a hosting-managed pipeline.
