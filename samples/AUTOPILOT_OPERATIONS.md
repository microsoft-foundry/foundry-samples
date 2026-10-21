# Autopilot sample operations

Use these steps after you deploy updated code to an autopilot sample in this
repository. Each sample README lists the values to substitute: the command
that deploys a new version, the `azd` environment value that stores the
Foundry project endpoint, the agent name, the span query to run, and how the
sample handles message content.

## Before you begin

Run the commands in PowerShell 7 from the sample directory, with the `azd`
environment that you deployed selected. The session commands come from the
`azure.ai.agents` extension for `azd`. If `azd ai agent sessions --help`
fails, install it:

```powershell
azd ext install azure.ai.agents
```

## Confirm the running version

1. Deploy the updated code with the command in your sample's README, and
   record the agent version that the deployment reports.
2. Confirm in the Foundry portal that this version is selected for new
   invocations. Creating a version alone does not prove that traffic uses it.
3. List the agent's sessions:

   ```powershell
   $env:FOUNDRY_PROJECT_ENDPOINT = azd env get-value "<endpoint-setting>"
   $agentName = "<agent-name>"
   azd ai agent sessions list --agent-name $agentName --output json
   ```

   Find the session for your conversation by its timestamps, or by the
   `sessionId` of an earlier span when your sample records one. Inspect its
   `agent_session_id`, `status`, and `version_indicator.agent_version`. If the
   response includes a continuation token, pass it to `--pagination-token` to
   retrieve the next page. An existing session can still be running the
   previous version.

## Resume a session on the new version

1. Stop only the session you intend to test:

   ```powershell
   azd ai agent sessions stop "<session-id>" --agent-name $agentName
   ```

   Stopping interrupts the session's running work but preserves the logical
   session and its persistent filesystem. Coordinate with anyone using that
   instance first. Do not delete the session just to pick up new code.
2. Send one message to the same instance in Teams. The invocation resumes the
   stopped session.
3. Repeat the session-list command and confirm that the session reports the
   intended version. If it does not, check which version the endpoint selects
   for new invocations rather than waiting for an idle timeout.

## Find the application spans

Allow time for telemetry ingestion, then open the **Logs** view of the
Application Insights resource connected to your Foundry project. Run the
query that your sample's README names, replacing the placeholders with the
values you confirmed.

For samples that emit their own `invoke_agent <agentName>` spans:

```kusto
let expectedAgentId = "<agent-name>:<version>";
dependencies
| where timestamp > ago(30m)
| where name startswith "invoke_agent "
| where tostring(customDimensions["gen_ai.agent.id"]) == expectedAgentId
| project timestamp, name, type, success, operation_Id,
    agentId = tostring(customDimensions["gen_ai.agent.id"]),
    responseId = tostring(customDimensions["gen_ai.response.id"]),
    sessionId = tostring(customDimensions["azure.ai.agentserver.session_id"]),
    projectId = tostring(customDimensions["microsoft.foundry.project.id"])
| order by timestamp desc
```

For samples whose spans come from an SDK or an OpenTelemetry distribution:

```kusto
union withsource=TelemetryTable requests, dependencies
| where timestamp > ago(30m)
| where cloud_RoleName endswith "<service-name>"
| project timestamp, TelemetryTable, name, application_Version,
    operation_Id, customDimensions
| order by timestamp desc
```

Keep these points in mind when you read the results:

- The table depends on the implementation. The custom `invoke_agent` spans in
  these samples are internal spans, which appear in `dependencies` with `type`
  set to `InProc`. Other span kinds and SDK integrations can use `requests`,
  so do not assume that one table holds every application span.
- The trailing space in `"invoke_agent "` excludes the platform's own bare
  `invoke_agent` span. A platform span or a successful reply alone does not
  prove that the application's instrumentation works.
- When a sample sets `service.namespace`, the cloud role name combines it with
  `service.name`, so the SDK query matches the end of the value.
- Use `operation_Id` to inspect the related spans of one interaction together.

## Protect message content

Message-content capture must be a deliberate choice. Each sample README
describes the setting that controls it and, where the sample sets one, its
default. After you change the setting, deploy a new version and repeat the
steps above.

- The GenAI capture setting controls message attributes on GenAI spans. It is
  not an application-wide redaction switch: application logs, exceptions, and
  other SDKs can still record message text.
- Use non-sensitive test messages, and review logging, telemetry access, and
  retention before you use real conversations.
- Message envelopes without text keep a trace structurally complete, but they
  do not give quality evaluators the conversation content they need.
