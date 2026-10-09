# Meeting Assistant Autopilot

Deploy a Python Autopilot that responds to Teams meeting events:

- Greets the chat when the agent is added to a meeting.
- Extracts an explicit agenda from the invitation and posts a reminder at meeting start.
- After meeting end, compares the transcript with that agenda and reports each
  item's status: **Closed**, **Open**, **Not discussed**, or **Unclear**.
- Reads transcripts only when Teams signals transcript availability after the meeting-end event.

Microsoft 365 reads use **Work IQ MCP with the Autopilot's agent-user identity**.
Reports include transcript quotes and links to the recording viewer or meeting
chat's **Recap**. Reviewed-source links remain available even when no supporting
quote is found. The agent does not join audio/video or respond to ordinary chat
messages. Without an explicit agenda, it does not post reminders or closure reports.

This preview sample assumes familiarity with the
[Hello World walkthrough](../hello-world/README.md).

## Step 1: Check the prerequisites

Use the tools, tenant setup, and resource permissions described in
[Hello World prerequisites](../hello-world/README.md#step-1-install-the-prerequisites).
This sample requires **azd 1.32.0 or later** and the **azure.ai.agents extension
1.0.0-beta.18 or later**. Choose a Foundry model supporting the Responses API
and structured outputs.

Before the meeting demo, have your tenant administrator:

1. Enable Work IQ and grant the blueprint's delegated **WorkIQAgent.Ask**
   permission. Confirm the agent-user identity meets the tenant's access and
   licensing requirements; see [Work IQ setup](https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/mcp/quickstart/foundry)
   and [permissions](https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/permissions).
2. Enable **Meetings > Meeting settings > Transcript API access > Microsoft Graph access**.
   Follow [Manage transcript API access for Teams meetings](https://learn.microsoft.com/en-us/microsoftteams/meeting-transcript-api-access).
   Inviting the agent does not override this setting; disabled access returns
   `403` / `GraphAccessToTranscriptsDisabled`.
3. Configure an active spending policy covering **Work IQ API** and the invoking
   agent-user identity. See the [usage-based billing overview for Microsoft 365 Copilot credits](https://learn.microsoft.com/en-us/microsoft-365/copilot/usage-based-billing-overview-copilot-credits),
   [billing setup](https://learn.microsoft.com/microsoft-365/copilot/usage-based-billing-copilot-credits-setup),
   and [spending-policy management](https://learn.microsoft.com/microsoft-365/copilot/usage-based-billing-manage-copilot-credits).

## Step 2: Sign in and select an environment

From `samples\python\autopilot-agents`, enter this sample's directory. Run all
subsequent commands there in PowerShell 7. Keep the parent `scripts` directory
when copying the sample; provisioning and session updates use its shared helpers.

```powershell
Set-Location .\meeting-assistant
az login --tenant <tenant-id>
azd auth login --tenant-id <tenant-id>
azd env new my-meeting-assistant
```

No existing `azd` environment is required.

## Step 3: Provision and deploy

```powershell
azd provision
azd deploy
azd ai agent show
```

Provisioning lets you create or reuse a resource group, Foundry resource, project,
and model deployment. It does not grant permissions; arrange project and
model access as described in Hello World before deployment.
Deployment packages the Python code directly, without Docker, and creates the
hosted agent **meeting-assistant-autopilot**. It does not publish a Microsoft 365 app.
Resource creation and model/Work IQ usage can incur charges.

## Step 4: Publish and create an instance

Review the publication metadata and runtime settings in [azure.yaml](azure.yaml),
then publish:

```powershell
azd ai agent publish
```

Have an **AI Administrator** or **Global Administrator** approve the
**Meeting Assistant Autopilot** blueprint and grant its Work IQ permission.
Create an instance through Teams **Apps > Agents for your team**, following
[Hello World approval and instance creation](../hello-world/README.md#step-7-approve-the-blueprint).
Deployment and publication alone do not grant consent.

## Step 5: Try a meeting

Invite the agent user to a **scheduled, non-channel Teams meeting** with explicit
agenda items in the invitation body. Start transcription during the meeting.
Expect a greeting when the agent is added, an agenda reminder at actual meeting
start, and an end acknowledgment. A transcript-ready notification received after
meeting end triggers the transcript read and closure report. Recording-only
notifications and transcript notifications received before the end event are ignored.

The agent must be able to read its calendar invitation, meeting chat, and
transcripts through Work IQ. If no report appears, inspect logs for event
delivery, consent, billing, or transcript-access failures. The model is instructed
to quote transcript evidence, but quoted text is not checked for exact matches.
Review generated quotes and conclusions against the linked sources.

## Runtime configuration

Edit the service's `env` mapping in [azure.yaml](azure.yaml) and redeploy to change
hosted settings. For local runs, set environment variables before starting the agent.

| Environment variable | Sample setting | Purpose |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Supplied by provisioning/hosting; required. | Foundry project endpoint. Set explicitly for local runs. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Selected during provisioning; required. | Responses API model deployment supporting structured outputs. |
| `MEETING_LOG_ACTIVITY_PAYLOADS` | `"true"` in the manifest; `"false"` when unset. | Log raw incoming Activity bodies before SDK parsing and authorization. |
| `MEETING_LOG_WORKIQ_PAYLOADS` | `"true"` in the manifest; `"false"` when unset. | Log complete Work IQ arguments, responses, and errors. |
| `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__TYPE` | `AgenticUserAuthorization` | Use the agent-user identity for Work IQ authorization. |
| `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES` | `api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask` | Work IQ delegated scope; keep aligned with the published permission. |
| `FOUNDRY_AGENT365_TRACING_ENABLED` | `"true"` | Enable hosted Agent 365 tracing. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `"false"` | Disable SDK model-content capture; independent of raw payload logging. |

**Raw payload logging is unredacted and enabled by default in the hosted sample.**
Use synthetic meetings and restrict log access and retention. Captures can include
meeting descriptions, transcripts, personal data, and join URLs. The two
`MEETING_LOG_*` flags accept case-insensitive `true` or `false`; disabling them
preserves normal lifecycle logging and Work IQ error summaries.

Payload entries contain `capture_id`, `part`, `parts`, and a JSON-escaped `body`.
To reconstruct a capture, group by log label and `capture_id`, sort by `part`,
and concatenate the decoded `body` strings.

## Updating the agent

For code or runtime-setting changes:

```powershell
azd deploy
..\scripts\stop-agent-sessions.ps1 -AgentName meeting-assistant-autopilot
```

Stopping old sandboxes preserves logical sessions and lets subsequent invocations
use the updated deployment. Republish only when publication metadata or permissions
change. Avoid `azd down` on environments using shared resources.

## Sample limitations

This is an event-driven demo, not a production meeting service. It relies on Teams
start/end and artifact notifications; it does not recover missing events through
durable polling. If no transcript-ready notification arrives after the end event,
the report remains pending. Readiness retries are limited to three attempts,
five seconds apart, for empty matching results or Work IQ 404 responses.

Transcript-ready notifications bind their `Identifiers/Id` value with
`type="callId"` to the observed occurrence. Transcript listing uses a server-side
`callId` filter and checks returned call IDs before reading content. Notifications
without a call ID retain timestamp matching: transcription end time first, then
creation time if end time is absent. The sample reads one page only; calls with
additional transcript pages are unsupported and no partial report is posted.
Live Work IQ filter support and notification-to-Graph call-ID mapping still need
confirmation with agent credentials.

Occurrence history is retained without automatic pruning or a count limit, so
persisted chat state grows with each meeting. Long-running use needs a retention
policy. The sample refuses incomplete or oversized reads: eight transcript
segments, 120,000 transcript characters,
32,000 invitation characters, and 20 agenda items. Reserved deliveries can remain
undelivered after failures, and there is no cross-replica exactly-once guarantee.
Define your own access and disclosure policy before using real meeting data;
meeting content is sent to the configured Foundry model.

The pinned preview SDKs require the small compatibility bridge in
[agent/hosting.py](agent/hosting.py): AgentServer Activity `1.0.0b3` passes a
`ClaimsIdentity` argument removed by the M365 SDK. The bridge uses public APIs
without patching installed packages.

## Local offline checks

From this sample's directory, no Azure or Microsoft 365 sign-in is required:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Keep the pinned deployment dependencies in `requirements.txt` synchronized with
`pyproject.toml`. The optional [SDK payload replay](scripts/replay-sdk-payloads.py)
checks parsing and dispatch with sanitized fixtures; it does not contact Teams,
Work IQ, or the model.
