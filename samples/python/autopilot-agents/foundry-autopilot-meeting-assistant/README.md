# Foundry Autopilot Meeting Assistant

A Microsoft 365 Digital Worker sample that demonstrates Manager-owned Teams meeting chat delegation with Activity Protocol context, Teams/Calendar MCP boundaries, and Blob-backed meeting delegate state.

## Demo

[Watch the Meeting Assistant demo](https://microsoft.sharepoint.com/:v:/r/teams/AzureDeveloperCLIazdPartners/_layouts/15/stream.aspx?id=%2Fteams%2FAzureDeveloperCLIazdPartners%2FShared%20Documents%2F%F0%9F%92%AC%20General%2Fautopilot%2Ddemos%2Fautopilot%2Dmeeting%2Dagent%2Ddemo%2D0916%2Dshortened%2Emp4&share=cQptxMLkk6UMSKFAxiJ%2D6rFqEgUCeClJi4MFlAZuCMBZ18rY0A)

## Scope

This MVP supports:

- Activity Protocol `2.0.0` hosting;
- tenant-scoped Microsoft 365 Digital Worker publication;
- Azure OpenAI Responses API for ordinary meeting-related chat;
- remote Teams and Calendar MCP servers;
- Manager-only meeting delegate configuration;
- per-Tenant + per-Agent-User + per-meeting state in an Azure Blob container
  accessed through Microsoft Entra authentication and Azure RBAC;
- configured answer rules for meeting chat @mentions;
- a fixed unknown response for @mention questions outside Manager-approved rules;
- `/meeting` Calendar queries for future meetings attended by both the Agent User and current Manager, returned as an Adaptive Card;
- `/activity_context` Adaptive Card output with `User`, `Conversation`, `Digital Worker`, and `Agent Manager` sections.

This sample is a meeting-chat delegate. It does not create, inspect, update, reschedule, cancel, or delete Calendar meetings. It also does not join meeting audio/video, read microphone media, perform speech-to-text, or use real-time participant roster triggers.

The remote MCP allowlist is fixed in `ToolingManifest.json`:

```text
mcp_TeamsServer
mcp_CalendarTools
```

## Manager-Only Boundary

A Digital Worker Instance can only become a meeting assistant for its own current Manager. The Manager is resolved from the Agent User's Entra profile with Microsoft Graph. Only that Manager can create, update, inspect, or disable meeting delegate configuration.

Meeting delegate state is scoped by:

```text
Tenant ID + Agent User ID + Meeting ID
```

Another user cannot configure this Digital Worker as their meeting assistant, even if they can talk to the agent. Meeting chat content also cannot change the configured Manager, meeting, recipient, MCP server, or answer rules.

## Activity Protocol Behaviors

This sample uses Activity Protocol context to route and authorize meeting work without relying only on model text:

- Teams `message` activities are treated as Manager configuration turns or meeting chat turns, depending on command text, mention state, and meeting context;
- Manager configuration is explicitly restricted to `msteams`; meeting-answer
  routing separately requires a meeting identity, enabled stored delegate, and
  Agent mention without an additional channel-ID gate;
- `activity.from_property` identifies the sender, so only the current Manager can configure, inspect, or disable meeting delegation;
- `activity.recipient.tenant_id` and `activity.recipient.agentic_user_id` scope meeting delegate state per personal Agent User;
- `/activity_context` returns an Adaptive Card with sanitized `User`, `Conversation`, `Digital Worker`, and `Agent Manager` sections.

## Data Access Model

This sample demonstrates Manager-owned meeting policy. Microsoft 365 meeting operations use the Agent User identity; meeting delegate state uses the Agent Instance managed identity and Azure RBAC.

| Data | Access path | Identity | Authorization |
|---|---|---|---|
| Meeting delegate configuration | Blob Storage | Agent Instance managed identity | Azure RBAC `Storage Blob Data Contributor`; writes require current Manager authorization |
| Meeting chat message | Activity Protocol turn | Agent User context | Requires configured meeting ID, enabled delegate, and Agent mention |
| Approved answer rules | Stored meeting delegate policy | Manager-owned policy | Only the current Manager can create or change rules |
| Upcoming meeting list | `mcp_CalendarTools` | Agent User | Tenant-approved Calendar MCP scope; results require both the Agent User and current Manager as participants |
| Meeting and thread aliases | Graph `/me/events/{id}` and `/me/onlineMeetings` | Agent User | Graph `OnlineMeetings.Read`; enriches Calendar candidates and resolves join URLs when aliases are persisted |
| Teams and Calendar operations | `mcp_TeamsServer` / `mcp_CalendarTools` | Agent User | Tenant-approved Teams and Calendar MCP scopes |
| Agent User Manager | Graph `/me?$expand=manager(...)` | Agent User | Graph `User.Read` / `User.Read.All` and the Entra manager relationship |

A Digital Worker Instance can only become a meeting assistant for its own current Manager. Another user cannot configure this worker for their meetings, even if they can send messages to the agent. Meeting chat content is untrusted data: it cannot change the configured Manager, meeting, recipient, MCP server, or answer rules.

Calendar MCP supplies structured candidate meetings. Microsoft Graph enriches
each selected event and resolves online-meeting details used to persist aliases
for the Calendar event ID, join URL, online-meeting ID, and Teams thread ID.

## Lifecycle Overview

```text
Configure azd environment and model mode
  -> Provision Azure resources, Blob Storage, and optional model
  -> Deploy hosted-agent container and create Agent Identity Blueprint
  -> Configure model and Blob access for the Agent Instance identity
  -> Publish the Digital Worker to Microsoft 365
  -> Tenant administrator approves and activates it
  -> Manager creates a personal Digital Worker Instance
  -> Manager configures one meeting delegate
  -> Meeting chat @mentions are answered from approved rules or receive a fixed unknown response
```

| Operation | Result |
|---|---|
| `azd provision` | Creates the resource group, Foundry account/project, ACR, a Blob container for delegate state, and optionally the model deployment |
| `azd deploy` | Builds the container and creates an active hosted-agent version with Blueprint and Instance identity values |
| postdeploy hook | Grants Blob Storage access, grants model access for a sample-owned model, or prints manual RBAC guidance for an existing model |
| `azd ai agent publish` | Submits the Digital Worker definition to Microsoft 365 |
| Tenant approval | Makes the Digital Worker available to the approved tenant audience |
| Instance creation | Creates one personal Digital Worker Instance with its Agent Identity and Agent User |

## Prerequisites

- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd);
- Azure CLI;
- Python 3.11 or later;
- PowerShell 7 for the azd hooks;
- an Azure subscription and active Microsoft Entra tenant;
- permission to create resources and role assignments in the target subscription;
- access to Microsoft 365 Digital Worker preview capabilities;
- a tenant administrator who can approve and activate the Digital Worker;
- either quota to deploy a supported model or access to an existing Azure OpenAI or Foundry model deployment;
- an Agent User whose Entra `manager` relationship points to the human Manager who will configure meeting delegation.

This sample requires the publicly available `azure.ai.agents` extension version
`1.0.0-beta.14` or later.

## Quick Start

Run all commands from the `foundry-autopilot-meeting-assistant` directory.

### Step 1: Install And Verify The Extension

```powershell
azd extension install azure.ai.agents
azd extension list
azd ai agent --help
```

Confirm that `azure.ai.agents` is `1.0.0-beta.14` or later and that `azd ai agent publish` is available.

### Step 2: Authenticate

```powershell
az login --tenant <TENANT_ID>
azd auth login --tenant-id <TENANT_ID>
az account show
```

### Step 3: Choose A Unique Agent Name

Before the first deployment, update these values in `azure.yaml`:

```yaml
services:
  autopilot-meeting-assistant: # Keep this service key unchanged.
    name: <UNIQUE_AGENT_NAME>
    displayName: <FOUNDRY_DISPLAY_NAME>
    activity:
      publish:
        agentDisplayName: <MICROSOFT_365_DISPLAY_NAME>
```

Keep the `autopilot-meeting-assistant` service key unchanged. azd derives
values such as `AGENT_AUTOPILOT_MEETING_ASSISTANT_NAME` from this key, and the
postdeploy hook uses the same key to locate the Agent Instance identity.

### Step 4: Create The azd Environment

```powershell
azd env new <ENVIRONMENT_NAME>
azd env set AZURE_SUBSCRIPTION_ID "<SUBSCRIPTION_ID>"
azd env set AZURE_LOCATION "<SUPPORTED_REGION>"
```

Choose a region that supports Foundry hosted agents and, when deploying a model, the selected model version and SKU.

### Step 5: Choose A Model Mode

`deployModel` defaults to `false`, so this sample does not create a billable model without an explicit choice.
`azd provision` reads these azd environment values through `infra/main.bicepparam` and passes them to `infra/main.bicep`.

#### Option A: Deploy A Model

```powershell
azd env set deployModel true
azd env set modelDeploymentName "gpt-5-mini"
azd env set modelName "gpt-5-mini"
azd env set modelVersion "2025-08-07"
azd env set modelSkuName "GlobalStandard"
azd env set modelCapacity 10
```

#### Option B: Use An Existing Model

```powershell
azd env set deployModel false
azd env set existingModelResponsesEndpoint "<YOUR_RESPONSES_ENDPOINT>"
azd env set modelDeploymentName "<YOUR_MODEL_DEPLOYMENT>"
```

The endpoint must be a Responses API endpoint, for example:

```text
https://<account>.services.ai.azure.com/openai/v1/responses
```

The preprovision hook rejects existing-model mode when the endpoint or
deployment name is missing. Bicep does not create, modify, or delete that
model. After deployment, grant the Agent Instance identity **Cognitive
Services User** on the account that owns the endpoint by using the command
printed by the postdeploy hook.

### Step 6: Provision Azure Resources

```powershell
azd env get-values
azd provision
```

Confirm that these outputs are populated:

```text
azureOpenAIResponsesEndpoint
modelDeploymentName
meetingDelegateStorageAccountUrl
meetingDelegateStorageContainer
```

### Step 7: Deploy The Digital Worker

```powershell
azd deploy
```

If `azd provision` just completed, Foundry RBAC assignments might still be
propagating. A first `azd deploy` can temporarily fail with `403 Forbidden` for
the `Microsoft.CognitiveServices/accounts/AIServices/agents/read` action. Wait
a few minutes and retry `azd deploy`. If the error persists, verify the
deploying identity's Foundry role assignment on the project.

The postdeploy hook always grants **Storage Blob Data Contributor** on the meeting delegate storage account. For `deployModel=true`, model RBAC is applied automatically. For `deployModel=false`, follow the printed manual RBAC command before testing.

The storage account keeps its public Azure Storage endpoint enabled. Anonymous
blob access and shared-key authentication are disabled, and the Agent Instance
uses Microsoft Entra authentication with **Storage Blob Data Contributor**.

Each successful deployment creates an immutable hosted-agent version. Existing
Teams conversations can remain bound to a previous version; delete only the
affected hosted session with `azd ai agent sessions delete <SESSION_ID>` to
start that conversation on the active version. Code-only changes do not require
republishing unless publication metadata, permission scopes, or audience
changed.

### Step 8: Publish To Microsoft 365

```powershell
azd ai agent publish --scope tenant
```

The extension publishes the Activity Protocol metadata, Digital Worker type, Blueprint client ID, display information, requested Microsoft Graph scopes, and requested Teams/Calendar MCP permission scopes.

### Step 9: Approve, Activate, And Create An Instance

A tenant administrator completes the Microsoft 365 flow:

1. Open [Requested agents in the Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested).
2. Locate the Digital Worker by `agentDisplayName`.
3. Review its publisher, purpose, audience, and requested permissions.
4. Select **Approve request and activate**.
5. When applying the agent template in a non-EEA bug bash tenant, open the
  **Licenses** tab. The default license can be preselected even when it has no
  available seats.
6. Clear the default license selection and manually select **Microsoft 365
  Frontier for Autopilots (Non EEA)**, which has seats available for the bug
  bash Agent Instances.
7. Complete **Apply template**, then assign permitted users or groups when
  required by tenant policy.

The **Non EEA** license can be assigned only to Agent Instances. It does not
provide an Exchange Online mailbox license for a test user. Do not select it
for an EEA tenant; use the Agent Instance license that matches the tenant's
geography, available seats, and organizational policy.

The Manager then opens the Digital Worker in Teams and creates or hires a personal Instance.

Confirm that the Instance has an Agent Identity, Agent User account, Teams
availability, approved Teams/Calendar MCP permissions, and approved Graph
`User.Read`, `User.Read.All`, and `OnlineMeetings.Read` permissions.

## Meeting Assistant Commands

### List Upcoming Meetings

```text
/meeting
```

`/meetings` remains a compatibility alias. Natural-language requests such as `Show meetings my Manager and I will both attend` are classified as the same query and use the identical Calendar and eligibility-filtering path. Title and custom time-range filters are intentionally not supported.

Expected result:

- the Agent queries Calendar through `mcp_CalendarTools` using the Agent User identity;
- only meetings whose start time is at or after the current UTC time are returned;
- the current Manager must be an organizer or attendee; querying the Agent User's own calendar provides the Agent User participation boundary;
- results are ordered by start time and limited to the next 10 meetings;
- the response is an Adaptive Card showing Meeting ID, subject, start, end, time zone, location, organizer, and a safe HTTPS meeting link when available;
- an empty-state or error card is returned instead of model-generated HTML when no meetings are found or Calendar is unavailable.

The Calendar event ID returned by `/meeting` is the canonical persisted key for
meeting delegate and automatic-reply configuration. Runtime aliases can map a
join URL, online-meeting ID, Teams thread ID, or uniquely matching schedule
back to that key. This does not enable Calendar meeting management.

### Configure A Meeting Delegate

Only the current Manager can open and save the configuration card in Teams:

```text
/meeting_delegate configure meeting-1
```

The Adaptive Card supports:

- automatically carrying the selected Meeting ID and other system metadata without editable fields;
- adding and deleting question-and-answer items before saving;
- enabling or disabling automatic replies for the meeting;
- enabling or disabling each individual question;
- reopening an existing configuration by Meeting ID;
- saving the validated configuration to the meeting delegate Blob Storage container.

The JSON command remains available for compatibility:

```text
/meeting_delegate configure {
  "meetingId": "meeting-1",
  "chatId": "meeting-chat-id",
  "subject": "AZD Release Planning",
  "openingMessage": "Hello everyone. I am Huajie's Digital Worker.",
  "answerRules": [
    {
      "questions": ["When is the latest AZD release?"],
      "answer": "The latest AZD release is planned for October 1."
    }
  ]
}
```

Expected result:

- the command succeeds only when the sender is this Digital Worker's current Manager;
- the delegate is stored under `Tenant ID + Agent User ID + Meeting ID`;
- Adaptive Card Save writes through `AzureBlobMeetingDelegateStore` when the deployed storage environment variables are present;
- the saved card is redrawn with the persisted values and a success message.

### Bind An Existing Meeting Chat

For a configuration saved before meeting schedule metadata was persisted, the current Manager can run this once inside the target meeting chat:

```text
/meeting_delegate bind meeting-1
```

Use the Calendar Meeting ID shown by `/meeting` when the rules were configured. The command stores aliases from the current Teams meeting identity to that configuration. The aliases remain valid after the meeting ends.

### Check Status

```text
/meeting_delegate status meeting-1
```

### Disable Delegation

```text
/meeting_delegate disable meeting-1
```

## Meeting Chat Behavior

When the agent receives a meeting chat message with a configured `meetingId`:

- meeting start and end times are used only to associate Calendar and Teams meeting identities when needed;
- automatic replies have no time window and continue to work in the same meeting chat after the meeting ends;

- messages without an Agent mention are ignored;
- messages for unconfigured meetings are ignored;
- an LLM matches the user's question against the enabled standard QA list,
  including equivalent paraphrases and minor wording differences;
- matched questions receive only the configured Manager-approved standard answer;
- unmatched questions, model matching failures, and configurations with no
  enabled answer rule receive the fixed response `I don't know.`; no unmatched
  question record is persisted;
- duplicate Activity IDs are ignored by the process-local in-memory
  deduplicator; no occurrence count is stored.

Example configured question:

```text
@Agent When is the latest AZD release? meetingId=meeting-1
```

Example unmatched question:

```text
@Agent Does this release support offline deployment? meetingId=meeting-1
```

## Activity Context

Prompt:

```text
/activity_context
```

Expected result:

- the Agent responds directly without calling Responses API or MCP;
- the response is an Adaptive Card with sanitized `User`, `Conversation`, `Digital Worker`, and `Agent Manager` sections;
- the `Agent Manager` section shows who can configure this Digital Worker as a meeting assistant;
- long identifiers are shortened and `serviceUrl` is reported only as present or absent.

## Lifecycle Events

Action: install or hire the Digital Worker in Teams.

Expected result:

- the Agent receives `installationUpdate` and sends a welcome message;
- when a member is added, the Agent receives `conversationUpdate` and sends the help message;
- no Responses API or MCP call is required for these lifecycle responses.

## Local Validation

Install the pinned runtime dependencies before running the local checks:

```powershell
python -m pip install -r src/foundry_m365_autopilot/requirements.txt
```

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
python -m unittest discover -s src/foundry_m365_autopilot/tests
python -m compileall -q src/foundry_m365_autopilot
az bicep build --file infra/main.bicep --stdout | Out-Null
```

The hosted deployment injects the Responses endpoint, model deployment,
connection authority, tenant, and delegate-storage values through `azure.yaml`.
The runtime also supports local overrides such as `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_API_VERSION`, and `FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID`;
the standard azd deployment does not configure API-key authentication.

This sample contains `.ci-skip` because the shared hosted-agent cloud E2E
runner supports Responses and Invocations, but not Activity Protocol's
Bot/Teams setup and asynchronous replies. It therefore has no generic
`test-spec.yml`; validate it with the local checks and Microsoft 365 scenarios
documented above.

## Customization Points

- Agent instructions and command routing: [agent.py](./src/foundry_m365_autopilot/agent.py)
- Meeting delegate state: [meeting_store.py](./src/foundry_m365_autopilot/meeting_store.py)
- Manager authorization: [graph.py](./src/foundry_m365_autopilot/graph.py)
- MCP server manifest: [ToolingManifest.json](./src/foundry_m365_autopilot/ToolingManifest.json)
- Microsoft 365 publish metadata and permission scopes: [azure.yaml](./azure.yaml)

## Current MVP Limits

- No real-time audio/video meeting participation.
- No participant-count or attendee-presence triggers.
- No durable scheduler for the opening message yet.
- Configuration normally starts from the Calendar event ID returned by
  `/meeting`. The runtime can persist join URL, online-meeting, Teams-thread,
  and legacy bind aliases, but it does not discover or manage arbitrary
  meetings.
- Answer matching is intentionally conservative and only uses configured Manager-approved answer rules.

## Clean Up

```powershell
azd env get-values
azd down
```

`azd down` deletes sample-managed Azure resources, including the delegate-state
storage account and the model deployment only when `deployModel=true`. It does
not delete existing models used in reuse mode, withdraw the Microsoft 365
publication, or remove Microsoft 365 approvals, personal Digital Worker
Instances, or Teams meetings.
