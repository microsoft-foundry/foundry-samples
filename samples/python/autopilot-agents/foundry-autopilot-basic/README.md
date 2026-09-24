# Foundry Autopilot Basic

A minimal Microsoft 365 Digital Worker sample that demonstrates the complete Microsoft Foundry hosted-agent lifecycle and remote Microsoft 365 MCP tool calls.

## Scope

This sample supports:

- Activity Protocol `2.0.0` hosting;
- tenant-scoped Microsoft 365 Digital Worker publication;
- Azure OpenAI Responses API;
- remote Mail, Teams, and Calendar MCP servers;
- conversation continuity through conversation-ID-keyed `previous_response_id`
  state stored under the hosted session home directory.

The remote MCP allowlist is fixed in code and `ToolingManifest.json`:

```text
mcp_MailTools
mcp_TeamsServer
mcp_CalendarTools
```

The application controls the MCP server URLs and allowlist. Every tool sent to
Responses API has `type: mcp`.

## Activity Protocol Behaviors

This sample also exposes a few Activity Protocol capabilities that are not visible in a text-only model invocation:

- `conversationUpdate` and `installationUpdate` handlers send welcome/help messages without calling Responses API or MCP;
- ordinary model-backed turns send an immediate acknowledgement and typing
  activities before the final response; help, capability, lifecycle, and
  `/activity_context` responses bypass that path;
- an expired `previous_response_id` is cleared and the request is retried once
  without prior conversation state;
- `/activity_context` returns a sanitized Adaptive Card summary of the current Activity envelope, including sender, conversation, channel, tenant, Agent app, and Agent User context.

## Data Access Model

This sample demonstrates the simplest Digital Worker data access pattern: the Agent User accesses its own Microsoft 365 work data through tenant-approved MCP servers.

| Data | Access path | Identity | Authorization |
|---|---|---|---|
| Agent User mailbox | `mcp_MailTools` | Agent User | Tenant-approved Mail MCP scope and mailbox availability |
| Teams messages | `mcp_TeamsServer` | Agent User | Tenant-approved Teams MCP scope and Teams policy |
| Calendar events | `mcp_CalendarTools` | Agent User | Tenant-approved Calendar MCP scope and calendar availability |
| Model access | Azure OpenAI Responses API | Agent Instance managed identity, or configured API key | Azure RBAC when using managed identity |

The Activity Protocol turn provides the sender, conversation, tenant, Agent app, and Agent User context. The MCP token is acquired through token exchange and sent only to the selected MCP server. The sample does not persist tokens, does not read delegated mailboxes, and does not apply Manager-owned policy.

Azure RBAC and Microsoft 365 permissions are separate. Azure RBAC controls model access for the Agent Instance managed identity; Microsoft 365 data access is controlled by MCP scopes, tenant approval, and resource policies for the Agent User.

## Lifecycle Overview

```text
Configure azd environment and model mode
  -> Provision Azure resources and optional model
  -> Deploy hosted-agent container and create Agent Identity Blueprint
  -> Configure model access for the Agent Instance identity
  -> Publish the Digital Worker to Microsoft 365
  -> Tenant administrator approves and activates it
  -> User creates a personal Digital Worker Instance
  -> Test Mail, Teams, and Calendar MCP calls
```

| Operation | Result |
|---|---|
| `azd provision` | Creates the resource group, Foundry account/project, ACR, and optionally the model deployment |
| `azd deploy` | Builds the container and creates an active hosted-agent version with Blueprint and Instance identity values |
| postdeploy hook | Grants model access for a sample-owned model, or prints manual RBAC guidance for an existing model |
| `azd ai agent publish` | Submits the Digital Worker definition to Microsoft 365 |
| Tenant approval | Makes the Digital Worker available to the approved tenant audience |
| Instance creation | Creates one personal Digital Worker Instance with its Agent Identity and Agent User |

Personal Microsoft 365 Instances are created after publishing and tenant
approval.

## Prerequisites

- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd);
- Azure CLI;
- Python 3.11 or later;
- PowerShell 7 for the azd hooks;
- an Azure subscription and active Microsoft Entra tenant;
- permission to create resources and role assignments in the target subscription;
- access to Microsoft 365 Digital Worker preview capabilities;
- a tenant administrator who can approve and activate the Digital Worker;
- either quota to deploy a supported model or access to an existing Azure OpenAI or Foundry model deployment.

This sample requires the publicly available `azure.ai.agents` extension version
`1.0.0-beta.14` or later.

## Quick Start

Run all commands from the `foundry-autopilot-basic` directory.

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
  autopilot-basic: # Keep this service key unchanged.
    name: <UNIQUE_AGENT_NAME>
    displayName: <FOUNDRY_DISPLAY_NAME>
    activity:
      publish:
        agentDisplayName: <MICROSOFT_365_DISPLAY_NAME>
```

- `name` is the Foundry hosted-agent name used by `azd deploy`;
- `displayName` is shown in Microsoft Foundry;
- `agentDisplayName` is shown in Microsoft 365 and Teams.

Keep the `autopilot-basic` service key unchanged. azd derives values such as
`AGENT_AUTOPILOT_BASIC_NAME` from this key, and the postdeploy hook uses the
same key to locate the Agent Instance identity.

Use lowercase letters, numbers, and hyphens for `name`. Changing it later creates another Foundry agent rather than renaming the deployed one.

### Step 4: Create The azd Environment

```powershell
azd env new <ENVIRONMENT_NAME>
azd env set AZURE_SUBSCRIPTION_ID "<SUBSCRIPTION_ID>"
azd env set AZURE_LOCATION "westus2"
```

For bug bash testing, use `westus2`. This is the recommended region for the
sample's tested deployment path and helps keep test environments consistent.
For other environments, choose a region that supports Foundry hosted agents
and, when deploying a model, the selected model version and SKU.

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
- project/account identities and ACR pull assignments;
- a model deployment only when `deployModel=true`.

Inspect the outputs:

```powershell
azd env get-values
azd ai project show --output json
```

Confirm that `azureOpenAIResponsesEndpoint` and `modelDeploymentName` are populated.

### Step 7: Deploy The Digital Worker

```powershell
azd deploy
```

If `azd provision` just completed, Foundry RBAC assignments might still be
propagating. A first `azd deploy` can temporarily fail with `403 Forbidden` for
the `Microsoft.CognitiveServices/accounts/AIServices/agents/read` action. Wait
a few minutes and retry `azd deploy`. If the error persists, verify the
deploying identity's Foundry role assignment on the project.

Deployment performs the remote container build, pushes the image to ACR, creates and activates a hosted-agent version, records the Agent Identity Blueprint client ID and Agent Instance identity principal ID, and runs `scripts/configure-agent-model-access.ps1`.

For `deployModel=true`, model RBAC is applied automatically. For `deployModel=false`, follow the printed manual RBAC command before testing.

Verify the deployment:

```powershell
azd ai agent show --output json
azd env get-values
```

Look for values similar to:

```text
AGENT_AUTOPILOT_BASIC_NAME
AGENT_AUTOPILOT_BASIC_PROJECT_ENDPOINT
AGENT_AUTOPILOT_BASIC_BLUEPRINT_CLIENT_ID
AGENT_AUTOPILOT_BASIC_INSTANCE_IDENTITY_PRINCIPAL_ID
```

#### Start A New Activity Session After Redeploying

Each successful deployment creates an immutable hosted-agent version. Existing
Teams conversations can continue using a session bound to the previous version,
so a code change might not appear immediately in an existing chat.

For development and testing, replace only the session associated with your
current Teams conversation:

1. Confirm that the newly deployed version is `active`:

  ```powershell
  azd ai agent show --output json
  ```

2. In the existing Teams chat, send:

  ```text
  /activity_context
  ```

3. Copy the complete **Session id** shown in the Conversation section of the
  Adaptive Card.
4. Delete that session:

  ```powershell
  azd ai agent sessions delete <SESSION_ID>
  ```

5. Send `/activity_context` again. The next Activity creates a session on the
  currently active hosted-agent version.
6. Verify that the new session uses the expected version:

  ```powershell
  azd ai agent sessions list --output table
  ```

Deleting a session permanently removes its compute, persistent files, and
session-backed state. Do not bulk-delete sessions or delete another user's
session in a shared environment. Stopping a session is not sufficient for this
workflow because a stopped session preserves its state and can be resumed.

Code-only changes do not require publishing the Agent again or creating a new
Microsoft 365 Agent Instance. Republish only when the Microsoft 365 publication
metadata, permissions, or audience changes.

### Step 8: Publish To Microsoft 365

```powershell
azd ai agent publish --scope tenant
```

The extension publishes the Activity Protocol metadata, Digital Worker type, Blueprint client ID, display information, and requested Mail, Teams, and Calendar MCP permission scopes. Record the administration URL printed by the command.

### Step 9: Approve, Activate, And Create An Instance

A tenant administrator completes the Microsoft 365 flow:

1. Open [Requested agents in the Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested).
2. Locate the Digital Worker by `agentDisplayName`.
3. Review its publisher, purpose, audience, and requested MCP permissions.
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

The test user then opens the Digital Worker in Teams and creates or hires a personal Instance. Confirm that the Instance has an Agent Identity, Agent User account, Teams availability, a mailbox and calendar for the relevant tests, and approved MCP permissions.

## Basic Test Scenarios

Run these tests from the personal Digital Worker Instance in Teams. Use test recipients and meetings rather than production data.

### Test 1: Activity Context

Prompt:

```text
/activity_context
```

Expected result:

- the Agent responds directly without calling Responses API or MCP;
- the response is an Adaptive Card with sanitized `User`, `Conversation`, and `Digital Worker` sections;
- the response shows Activity Protocol context such as channel, conversation id, tenant id, Agent app id, and Agent User id;
- long identifiers are shortened and `serviceUrl` is reported only as present or absent.

### Test 2: Lifecycle Events

Action: install or hire the Digital Worker in Teams.

Expected result:

- the Agent receives `installationUpdate` and sends a welcome message;
- when a member is added, the Agent receives `conversationUpdate` and sends the help message;
- no Responses API or MCP call is required for these lifecycle responses.

### Test 3: General Conversation

Prompt:

```text
Hello. Introduce yourself and tell me which Microsoft 365 tasks you can help with.
```

Expected result:

- the Agent responds in the current conversation;
- no MCP call is required;
- the response identifies its Mail, Teams, and Calendar capabilities.

### Test 4: Send A Teams Message

Preconditions: the recipient can be resolved in the tenant and the Agent User can use Teams MCP.

Prompt:

```text
Send a Teams message to Alice saying "Hello from my Digital Worker."
```

Expected result:

- Responses API selects `mcp_TeamsServer`;
- exactly one message is sent to the intended recipient or chat;
- the sender is attributable to the Digital Worker Agent User;
- the final response reports success and only one message is delivered.

### Test 5: Send An Email

Preconditions: the Agent User has a working mailbox, the recipient is a test address, and the tenant approved Mail MCP.

Prompt:

```text
Send an email to alice@contoso.com with subject "Digital Worker test" and body "This is a basic MCP validation message."
```

Expected result:

- Responses API selects `mcp_MailTools`;
- one message appears in the recipient mailbox;
- the sender is the Digital Worker Agent User;
- subject and body match the request.

This scenario uses the Digital Worker Agent User's mailbox through the remote
Mail MCP server.

### Test 6: Schedule A Meeting

Preconditions: the Agent User has a working calendar, attendee addresses are valid test users, and the tenant approved Calendar MCP.

Prompt:

```text
Schedule a 30-minute Teams meeting with Alice tomorrow at 10:00 AM. Use the subject "Digital Worker calendar test".
```

Expected result:

- the Agent asks for a timezone or other missing information when necessary;
- Responses API selects `mcp_CalendarTools`;
- one calendar event is created with the requested subject, duration, and attendee;
- the invitation is sent by the Digital Worker Agent User;
- a Teams meeting link is present when supported by the MCP tool.

### Test 7: Missing Required Information

Prompt:

```text
Send a message about the release.
```

Expected result:

- the Agent asks whether this should be a Teams message or email;
- it asks for recipient and content details;
- it invokes the selected MCP server only after the required details are known.

## Verify Tool Execution

Stream logs for a known hosted-agent session:

```powershell
azd ai agent monitor --session-id "<FOUNDRY_AGENT_SESSION_ID>" --follow
```

The Basic runtime logs the MCP server label, tool name, and success status.
Observed server labels should be limited to:

```text
mcp_MailTools
mcp_TeamsServer
mcp_CalendarTools
```

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
connection authority, and tenant through `azure.yaml`. The runtime also
supports local overrides such as `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_API_VERSION`, and `FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID`;
the standard azd deployment does not configure API-key authentication.

This sample contains `.ci-skip` because the shared hosted-agent cloud E2E
runner supports Responses and Invocations, but not Activity Protocol's
Bot/Teams setup and asynchronous replies. It therefore has no generic
`test-spec.yml`; validate it with the local checks and Microsoft 365 scenarios
documented above.

## Clean Up

Review the selected environment before deleting resources:

```powershell
azd env get-values
azd down
```

When the current azd environment created the resource group, `azd down` removes
the sample-managed Foundry account, project, ACR, hosted agent, and any model
deployed with `deployModel=true`. Models supplied through existing-model mode
remain managed by their owning Azure resource.

`azd down` does not withdraw the Microsoft 365 publication or remove tenant
approval and personal Digital Worker Instances. Clean up those resources
separately in Microsoft 365.
