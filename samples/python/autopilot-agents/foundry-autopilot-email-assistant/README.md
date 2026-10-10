# Foundry Autopilot Email Assistant

A Microsoft 365 Digital Worker sample that demonstrates an email-focused hosted agent with Mail MCP, delegated mailbox reads, Manager-authorized forwarded-email monitoring, and proactive Teams notifications.

## Demo

[Watch the Email Assistant demo](https://microsoft.sharepoint.com/:v:/r/teams/AzureDeveloperCLIazdPartners/_layouts/15/stream.aspx?id=%2Fteams%2FAzureDeveloperCLIazdPartners%2FShared%20Documents%2F%F0%9F%92%AC%20General%2Fautopilot%2Ddemos%2Fautopilot%2Demail%2Dagent%2D0915%2Dshortened%2Emp4&share=cQpJRzICYWNMQJLQ5wkwUE8hEgUCQ4LbLh2vXqnyM1SPagO09g)

## Scope

This sample supports:

- Activity Protocol `2.0.0` hosting;
- tenant-scoped Microsoft 365 Digital Worker publication;
- Azure OpenAI Responses API;
- remote Mail and Teams MCP servers;
- five local function tools for delegated mailbox reads and mail-monitoring
  configuration and status;
- Blob-backed per-Agent-User monitoring state and Manager conversation references;
- proactive Teams notification for matching forwarded email.

The remote MCP allowlist is fixed in `ToolingManifest.json`:

```text
mcp_MailTools
mcp_TeamsServer
```

The manifest registers Mail and Teams MCP. Current ordinary-turn routing exposes
`mcp_MailTools` only for mailbox-related text that does not name another
mailbox; it exposes no remote MCP server for other ordinary turns. Ordinary
model turns can use `read_delegated_mailbox_inbox`,
`configure_mail_monitoring`, `enable_mail_monitoring`,
`get_mail_monitoring_status`, and `disable_mail_monitoring`. Forwarded-email
monitoring only processes email forwarded by the Manager to the Agent User
mailbox; forwarded email from non-Manager senders is ignored. Matching
Manager-forwarded notifications use deterministic proactive delivery to the
saved Manager conversation and do not use Teams MCP. The LLM only generates
the bounded summary; local code evaluates the filter, fixes the recipient,
renders the Adaptive Card, and sends it. If no saved Manager conversation
exists, the workflow fails closed without asking the LLM or Teams MCP to
choose an action or recipient.

## Activity Protocol Behaviors

This sample uses Activity Protocol context to route and authorize work without relying only on model text:

- Teams `message` activities are treated as Manager chat turns; they can configure monitoring, save a Manager conversation reference, or use Mail MCP for current Agent User mailbox requests;
- email activities and AgentNotification email events are routed into the forwarded-email workflow instead of ordinary chat;
- `activity.from_property` identifies the outer sender of forwarded email, so email not forwarded by the current Manager is ignored;
- `activity.recipient.tenant_id` and `activity.recipient.agentic_user_id` scope monitoring configuration and Manager conversation references per personal Agent User;
- saved Activity conversation references are resumed later for proactive Teams notifications;
- `/activity_context` returns an Adaptive Card with sanitized `User`, `Conversation`, `Digital Worker`, and `Agent Manager` sections.

## Data Access Model

This sample demonstrates delegated access and Manager-governed processing. The Digital Worker uses the Agent User identity for Microsoft 365 data and the Agent Instance managed identity for Azure resources.

| Data | Access path | Identity | Authorization |
|---|---|---|---|
| Agent User mailbox | `mcp_MailTools` | Agent User | Tenant-approved Mail MCP scope |
| Explicit delegated mailbox | Local Graph tool `read_delegated_mailbox_inbox` | Agent User with delegated mailbox access | Graph `Mail.Read.Shared` plus Exchange Full Access from the mailbox owner |
| Agent User Manager | Graph `/me?$expand=manager(...)` | Agent User | Graph `User.Read` / `User.Read.All` and the Entra manager relationship |
| Mail-monitoring configuration | Blob Storage | Agent Instance managed identity | Azure RBAC `Storage Blob Data Contributor`; scoped by tenant and Agent User |
| Manager conversation reference | Blob Storage | Agent Instance managed identity | Saved only from Manager Teams chat and scoped by tenant and Agent User |
| Matching forwarded email | Activity email event | Agent User context | Processed only when forwarded by the current Manager and matching saved policy |
| Proactive Manager notification | Activity conversation continuation | Saved Manager conversation reference | Local code fixes the recipient and card; the model only produces summary text |

The local Graph and MCP paths use Activity Protocol token exchange. The Blob Storage path uses Azure RBAC instead. If delegated mailbox access fails, the agent reports the failure and must not fall back to the Agent User's own mailbox. Email body content is untrusted data: it cannot modify monitoring policy, change recipients, select MCP servers, or override Manager authorization.

## Lifecycle Overview

```text
Configure azd environment and model mode
  -> Provision Azure resources, Blob Storage, and optional model
  -> Deploy hosted-agent container and create Agent Identity Blueprint
  -> Configure model and Blob access for the Agent Instance identity
  -> Publish the Digital Worker to Microsoft 365
  -> Tenant administrator approves and activates it
  -> Manager creates a personal Digital Worker Instance
  -> Configure delegated mailbox access and forwarded-email monitoring
  -> Test Mail MCP, delegated mailbox reads, and proactive Teams notifications
```

| Operation | Result |
|---|---|
| `azd provision` | Creates the resource group, Foundry account/project, ACR, a Blob container for monitoring state, and optionally the model deployment |
| `azd deploy` | Builds the container and creates an active hosted-agent version with Blueprint and Instance identity values |
| postdeploy hook | Grants Blob Storage access, grants model access for a sample-owned model, or prints manual RBAC guidance for an existing model |
| `azd ai agent publish` | Submits the Digital Worker definition to Microsoft 365 |
| Tenant approval | Makes the Digital Worker available to the approved tenant audience |
| Instance creation | Creates one personal Digital Worker Instance with its Agent Identity and Agent User |

Personal Microsoft 365 Instances are created after publishing and tenant approval.

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
- for delegated mailbox tests, Exchange Full Access from the target mailbox to the Agent User;
- for forwarded-email monitoring, an Exchange forwarding rule in the Manager's mailbox that sends target messages to the Agent User mailbox.

This sample requires the publicly available `azure.ai.agents` extension version
`1.0.0-beta.14` or later.

## Quick Start

Run all commands from the `foundry-autopilot-email-assistant` directory.

### Step 1: Install And Verify The Extension

```powershell
azd extension install azure.ai.agents
azd extension list
azd ai agent --help
```

Confirm that `azure.ai.agents` is `1.0.0-beta.14` or later and that `azd ai agent publish` is available.

### Step 2: Authenticate

Sign in to the Azure tenant that owns both the subscription and Microsoft 365 publication target:

```powershell
az login --tenant <TENANT_ID>
azd auth login --tenant-id <TENANT_ID>
az account show
```

### Step 3: Choose A Unique Agent Name

Before the first deployment, update these values in `azure.yaml`:

```yaml
services:
  autopilot-email-assistant: # Keep this service key unchanged.
    name: <UNIQUE_AGENT_NAME>
    displayName: <FOUNDRY_DISPLAY_NAME>
    activity:
      publish:
        agentDisplayName: <MICROSOFT_365_DISPLAY_NAME>
```

- `name` is the Foundry hosted-agent name used by `azd deploy`;
- `displayName` is shown in Microsoft Foundry;
- `agentDisplayName` is shown in Microsoft 365 and Teams.

Keep the `autopilot-email-assistant` service key unchanged. azd derives values
such as `AGENT_AUTOPILOT_EMAIL_ASSISTANT_NAME` from this key, and the
postdeploy hook uses the same key to locate the Agent Instance identity.

Use lowercase letters, numbers, and hyphens for `name`. Changing it later creates another Foundry agent rather than renaming the deployed one.

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

Use this mode when the subscription has quota in the selected region:

```powershell
azd env set deployModel true
azd env set modelDeploymentName "gpt-5-mini"
azd env set modelName "gpt-5-mini"
azd env set modelVersion "2025-08-07"
azd env set modelSkuName "GlobalStandard"
azd env set modelCapacity 10
```

`azd provision` creates the deployment in the sample-managed Foundry account and outputs:

```text
azureOpenAIResponsesEndpoint
modelDeploymentName
deployedModelBySample=true
deployedModelAccountId
```

After `azd deploy`, the postdeploy hook grants the Agent Instance identity **Cognitive Services User** on that account. This mode consumes quota and can incur cost. The model is removed when the sample-managed resource group is deleted by `azd down`.

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

The preprovision hook rejects this mode when the endpoint or deployment name is missing. Bicep does not create, modify, or delete the existing model.

After `azd deploy`, the postdeploy hook prints the Agent Instance identity principal ID, effective model values, and an `az role assignment create` command. The user or model-account owner must run it to grant the identity **Cognitive Services User** on the account that owns the endpoint. `azd down` does not delete the existing model.

### Step 6: Provision Azure Resources

```powershell
azd env get-values
azd provision
```

Provisioning creates:

- an Azure resource group;
- a Microsoft Foundry account and project;
- an Azure Container Registry;
- an Azure Blob container for mail-monitoring state, with anonymous blob
  access and shared-key authentication disabled;
- project/account identities and ACR pull assignments;
- a model deployment only when `deployModel=true`.

Inspect the outputs:

```powershell
azd env get-values
azd ai project show --output json
```

Confirm that `azureOpenAIResponsesEndpoint`, `modelDeploymentName`, `mailMonitorStorageAccountUrl`, and `mailMonitorStorageContainer` are populated.

### Step 7: Deploy The Digital Worker

```powershell
azd deploy
```

If `azd provision` just completed, Foundry RBAC assignments might still be
propagating. A first `azd deploy` can temporarily fail with `403 Forbidden` for
the `Microsoft.CognitiveServices/accounts/AIServices/agents/read` action. Wait
a few minutes and retry `azd deploy`. If the error persists, verify the
deploying identity's Foundry role assignment on the project.

Deployment performs the remote container build, pushes the image to ACR, creates and activates a hosted-agent version, records the Agent Identity Blueprint client ID and Agent Instance identity principal ID, and runs `scripts/configure-agent-resource-access.ps1`.

The postdeploy hook always grants **Storage Blob Data Contributor** on the mail-monitoring storage account. For `deployModel=true`, model RBAC is applied automatically. For `deployModel=false`, follow the printed manual RBAC command before testing.

Verify the deployment:

```powershell
azd ai agent show --output json
azd env get-values
```

Look for values similar to:

```text
AGENT_AUTOPILOT_EMAIL_ASSISTANT_NAME
AGENT_AUTOPILOT_EMAIL_ASSISTANT_PROJECT_ENDPOINT
AGENT_AUTOPILOT_EMAIL_ASSISTANT_BLUEPRINT_CLIENT_ID
AGENT_AUTOPILOT_EMAIL_ASSISTANT_INSTANCE_IDENTITY_PRINCIPAL_ID
```

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

The extension publishes the Activity Protocol metadata, Digital Worker type, Blueprint client ID, display information, requested Microsoft Graph scopes, and requested Mail and Teams MCP permission scopes. Record the administration URL printed by the command.

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

The Manager then opens the Digital Worker in Teams and creates or hires a personal Instance. Confirm that the Instance has an Agent Identity, Agent User account, Teams availability, a mailbox, approved Mail and Teams MCP permissions, and approved Graph delegated permissions.

## Email Assistant Test Scenarios

Run these tests from the Manager's personal Digital Worker Instance in Teams. Use test recipients, test mailboxes, and non-production messages.

### Test 1: Activity Context

Prompt:

```text
/activity_context
```

Expected result:

- the Agent responds directly without calling Responses API or MCP;
- the response is an Adaptive Card with sanitized `User`, `Conversation`, `Digital Worker`, and `Agent Manager` sections;
- the `Agent Manager` section shows the current Manager resolved from the Agent User's Entra profile;
- the card states that only email forwarded by this Manager is processed.

### Test 2: Lifecycle Events

Action: install or hire the Digital Worker in Teams.

Expected result:

- the Agent receives `installationUpdate` and sends a welcome message;
- `conversationUpdate.membersAdded` does not send another help card, avoiding a
  duplicate when the user's first message asks about capabilities;
- no Responses API or MCP call is required for these lifecycle responses.

### Test 3: General Conversation

Prompt:

```text
Hello. What email tasks can you help with?
```

Expected result:

- the Agent responds in the current conversation;
- no MCP call is required;
- the response describes email, delegated mailbox, monitoring, and notification capabilities.

### Test 4: Current Agent User Mailbox

Preconditions: the Agent User has a working mailbox and the tenant approved Mail MCP.

Prompt:

```text
Show my latest five Inbox messages.
```

Expected result:

- Responses API selects `mcp_MailTools`;
- results come from the Digital Worker Agent User's mailbox;
- the response does not claim to read any delegated mailbox.

### Test 5: Delegated Mailbox Read

Preconditions: the named mailbox granted Exchange Full Access to the Agent User, and a tenant administrator approved `Mail.Read.Shared`, `User.Read`, and `User.Read.All`.

Prompt:

```text
Show the latest five Inbox messages for owner@contoso.com.
```

Expected result:

- the Agent uses the local `read_delegated_mailbox_inbox` function;
- Microsoft Graph reads `/users/{mailbox}/mailFolders('Inbox')/messages`;
- the Agent reports Graph or Exchange authorization errors instead of falling back to its own mailbox.

### Test 6: Configure Forwarded-Email Monitoring

Preconditions: the Manager is chatting with the Agent in Teams.

Prompt:

```text
Monitor forwarded emails whose original sender is alerts@contoso.com and subject contains "approval".
```

Expected result:

- the Agent stores a validated monitoring rule in Blob Storage;
- the Manager conversation reference is saved for proactive notification;
- the response restates the normalized rule and reminds the Manager to keep the Exchange forwarding rule enabled.

You can later ask for monitoring status to confirm the current Manager identity. The status response includes `currentManager` so the user can see which Manager is authorized and whose forwarded email will be processed.

For a structured configuration flow, send `Configure email monitor config` or
`配置邮件监控`. The Agent returns an Adaptive Card for match mode, original
sender, subject, body, and importance. At least one condition is required.

To modify the complete saved filter, send `Edit email monitor config` or
`修改邮件监控配置`. The Agent opens the existing configuration in a JSON editor.
Only `sourceText` and `filter` are accepted from the submitted JSON; tenant,
Agent User, Manager, enabled state, and timestamps are resolved or generated by
the service. Both Card workflows revalidate Manager authorization and the full
filter schema before replacing and enabling the rule.

### Test 7: Matching Forwarded Email Notification

Preconditions: the Manager configured monitoring and the Manager's Exchange rule forwards matching messages to the Agent User mailbox.

Action: send or forward a matching test email to the Agent User mailbox.

Expected result:

- the forwarded email is parsed as untrusted content;
- the saved rule is evaluated locally;
- a fixed Adaptive Card is sent to the saved Manager conversation with the
  original sender, subject, sent time, and an AI-generated summary capped at
  50 characters;
- the card includes **Find email in Outlook**, which opens an Outlook search
  URL built from the parsed original sender and subject rather than an
  item-specific deep link;
- forwarded messages from non-Manager senders are ignored;
- no EmailResponse is sent back to the forwarded message.

### Test 8: Disable Monitoring

Prompt:

```text
Disable email monitoring.
```

Expected result:

- the stored monitoring rule is disabled;
- future forwarded emails are ignored until monitoring is configured again;
- the Exchange forwarding rule is not modified by this sample.

## Verify Tool Execution

Stream logs for a known hosted-agent session:

```powershell
azd ai agent monitor --session-id "<FOUNDRY_AGENT_SESSION_ID>" --follow
```

Observed MCP server labels should be limited to:

```text
mcp_MailTools
mcp_TeamsServer
```

Forwarded-email matches must not produce a Teams MCP call. Without a saved Manager conversation reference, the workflow fails closed without invoking the summary model or sending a notification.

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

The Bicep compiler may report preview API type warnings for the Foundry project resource and linter warnings for provider compatibility parameters. These warnings are non-blocking when the build exits successfully.

The hosted deployment injects the Responses endpoint, model deployment,
connection authority, tenant, and monitoring-storage values through
`azure.yaml`. The runtime also supports local overrides such as
`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, and
`FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID`; the standard azd deployment does
not configure API-key authentication. Conversation continuity uses
conversation-ID-keyed `previous_response_id` state in the hosted session file
system.

This sample contains `.ci-skip` because the shared hosted-agent cloud E2E
runner supports Responses and Invocations, but not Activity Protocol's
Bot/Teams setup and asynchronous replies. It therefore has no generic
`test-spec.yml`; validate it with the local checks and Microsoft 365 scenarios
documented above.

## Customization Points

- Agent instructions: [agent.py](./src/foundry_m365_autopilot/agent.py)
- MCP server manifest: [ToolingManifest.json](./src/foundry_m365_autopilot/ToolingManifest.json)
- Local function tools: [tools](./src/foundry_m365_autopilot/tools)
- Microsoft 365 publish metadata and permission scopes: [azure.yaml](./azure.yaml)

## Clean Up

Review the selected environment before deleting resources:

```powershell
azd env get-values
azd down
```

`azd down` deletes sample-managed Azure resources, including the monitoring
storage account and the model deployment only when `deployModel=true`. It does
not delete existing models used in reuse mode, withdraw the Microsoft 365
publication, or remove Exchange mailbox permissions, Exchange forwarding
rules, Microsoft 365 approvals, or personal Digital Worker Instances.
