# Application Insights for Python agent samples

Use this setup reference for Python samples that already converse with a
Foundry agent, including [Chat with an agent](../quickstart/chat-with-agent).
The project connection enables **server-side agent tracing**; a client-side
OpenTelemetry exporter is not required for this quickstart.

## Configure once per project

Install Python 3.10+ and Azure CLI, then sign in with `az login`. Run from
the repository root, using your **existing** project's ARM resource ID:

```powershell
$env:FOUNDRY_PROJECT_RESOURCE_ID = "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
python .github\scripts\agent_tracing_setup.py --project-id $env:FOUNDRY_PROJECT_RESOURCE_ID
```

Setup reuses an existing App Insights connection **without modifying it**.
Otherwise, it creates workspace-based App Insights and a project-managed-identity
connection, with the necessary project identity roles. Creating resources and
role assignments requires appropriate Azure permissions. Setup can incur Azure
Monitor charges and enables project-wide trace collection, which can include
prompts/responses. Review access, content collection, and retention before enabling.

New identity/connection settings can take 2-5 minutes to propagate. Allow that
time before the first conversation; retry the sample if its initial trace check
preceded propagation. Setup reports configuration, not verified ingestion.
See the [Entra ingestion guidance](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-ingestion-entra-authentication).

To attach your own workspace-based, Entra-only App Insights when the project
has no connection, add `--application-insights-resource-id <component-ARM-ID>`.
An existing connection pointing elsewhere is reported as a conflict, never replaced.

To opt out of setup, add `--disable`. This does not disconnect existing shared
telemetry or disable traces already emitted by the service. The agent sample
itself can run without App Insights. A failed setup returns a warning and nonzero
status; correct the reported prerequisites and rerun the same command later.

## Run and verify

Fill the quickstart's existing endpoint, agent-name, and model placeholders and
run it normally. Its two France questions are unchanged. Each successful turn
prints `Agent response ID: ...`, allowing trace checks to identify this execution.

The existing `sample.yaml` live test now verifies **both** responses in the
connected App Insights resource, with bounded ingestion polling. Before invoking
the [live validator](../../../.github/scripts/validate-sample.README.md), set
`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_PROJECT_RESOURCE_ID`, `MODEL_DEPLOYMENT`,
and `SKIP_PROVISION=true`. Validate in a disposable checkout: its existing
placeholder substitutions modify source in that checkout.

The querying identity needs trace-read access; protected tables may also require
Privileged Monitoring Data Reader. Developer query access is not proof of the
project identity's permissions. Missing traces fail verification, while missing
permissions or other known cloud prerequisites are infrastructure errors.
`FOUNDRY_TRACE_TIMEOUT_SECONDS` optionally overrides the default ingestion wait.

The validator never creates resources. Setup is a separate, explicit operation.
For client-side tracing, frameworks, and hosted agents, use their own documented
instrumentation and exporter lifecycle; do not add another exporter to a
hosting-managed pipeline.
