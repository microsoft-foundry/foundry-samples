# Hello World Autopilot

Build a minimal Microsoft Foundry Autopilot that responds to Microsoft Teams
messages using a model in your Foundry project. This walkthrough takes you from
local setup to a published blueprint and your first conversation with an agent
instance in Teams.

The agent supports:

- Teams direct messages
- Teams group chat messages
- Teams channel messages that tag the agent

You will deploy Python code directly to Foundry Agent Service, publish the
Autopilot with `azd ai agent publish`, and have a tenant administrator approve
it before creating an instance. All setup instructions are on this page.

## Step 1: Install the prerequisites

Install:

1. [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
   **1.31.2 or later**.
2. [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli)
   **2.80 or later**.
3. Python 3.11 or later. The hosted runtime is Python 3.13, as declared in
   `azure.yaml`.
4. [PowerShell 7 or later](https://learn.microsoft.com/powershell/scripting/install/installing-powershell).

Install the Foundry agent extension (**1.0.0-beta.16 or later**):

```powershell
azd ext install azure.ai.agents
```

If it is already installed, update it instead:

```powershell
azd ext upgrade azure.ai.agents
```

This sample uses `activity.digitalWorkerType: m365` in `azure.yaml`. Current
extensions reject the retired `activity.useCase` setting; update the sample
configuration as well as the extension if you started from an older revision.

You also need an Azure subscription and a tenant with Microsoft Agent 365 and
qualifying Microsoft 365 licensing. Step 4 lets you reuse a Foundry project and
model deployment or create them interactively. Choose a
[supported hosted-agent region](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents#region-availability)
with quota for your model, and a model that supports the Responses API.
New resources and model usage can incur Azure charges.

Arrange the following access before starting cloud operations:

| Who | Required access |
| --- | --- |
| Person provisioning resources | **Contributor** on the resource group, or equivalent resource-management permissions. Creating a resource group requires this access at subscription scope. The subscription-scoped Bicep deployment also requires `Microsoft.Resources/deployments/*` at subscription scope, even when reusing a resource group. |
| Developer deploying the agent and managing sessions | **Foundry Project Manager** at the Foundry project scope. This covers hosted-agent management and role assignments for the platform-created agent identity when needed. |
| Person publishing the Autopilot | A Microsoft 365 license and **Foundry Project Manager** on the Foundry resource, or inherited from its resource group or subscription. This includes the project access needed to read the agent version and submit publication. |
| Administrator approving the blueprint | **AI Administrator** or **Global Administrator**, plus a Microsoft 365 license. |
| Person creating or using an instance | A Microsoft 365 license and access allowed by the tenant's app policies. |

Installing tools and creating local settings do not grant cloud access. Signing
in authenticates your account but does not grant it additional permissions.
Provisioning does not inspect, create, or change role assignments. An
administrator must arrange the developer's project access and grant the
project's managed identity **Cognitive Services User** on the Foundry resource
if that access is not already in place. For a newly created project, arrange
this access after Step 4 and before deploying. Azure resource access is separate
from Microsoft 365 publication and approval.

## Step 2: Sign in

Run all remaining commands in PowerShell 7 from the directory containing this
README. Keep the sibling `scripts` directory from the repository; it contains
the helper used when updating code.

Authenticate both CLIs against the tenant where you will deploy and publish
the agent. Replace `<tenant-id>` with that tenant's Microsoft Entra tenant ID.
The commands may open a browser to sign in:

```powershell
az login --tenant <tenant-id>
azd auth login --tenant-id <tenant-id>
```

## Step 3: Create an `azd` environment

Create a local environment to store this sample's deployment settings. Use a
short name such as `my-hello-world`:

```powershell
azd env new my-hello-world
```

The new environment becomes the active environment for subsequent commands.

## Step 4: Provision or connect to Foundry resources

Run the guided provisioning workflow:

```powershell
azd provision
```

The workflow prompts for settings that have not already been saved in your
active environment:

| Prompt | Expected value |
| --- | --- |
| Azure subscription | A subscription name or ID. Press Enter to accept the displayed default. |
| Resource group | An existing name from the displayed list, or a new resource-group name. |
| Foundry resource | An existing Foundry resource in the selected group, or a new globally unique name. |
| Azure region | For a new Foundry resource, a region name such as `northcentralus`. Reused Foundry resources keep their existing region automatically. |
| Foundry project | An existing project in the selected Foundry resource, or a new project name. |
| Model deployment | An existing deployment in the selected Foundry resource, or a new deployment name. |
| OpenAI model name | For a new deployment only, a model name from the [Foundry model catalog](https://ai.azure.com/explore/models) that supports the Responses API. Do not enter a version or SKU. |

Each resource list is scoped to the parent you selected. Enter a listed name to
reuse that resource, or a new name to create it. A new parent requires new child
resources. The hook prints a create/reuse summary and continues without an
additional confirmation prompt.

For a new model deployment, the workflow resolves the catalog's current default
version supporting the `GlobalStandard` SKU in your region and uses capacity
`1`. Existing deployments keep their model, version, SKU, and capacity.

Provisioning creates only missing resources; it does not manage permissions.
Existing resources keep their configuration. It saves the project resource ID,
endpoint, region, subscription, and model deployment name in the active `azd`
environment. You do not need to copy these values or set them individually.
Wait for `azd provision` to complete successfully before deploying.

Later runs reuse the saved selections and recognize resources created by an
earlier run. To configure a separate deployment, create a new `azd` environment.
Do not use `azd down` as a reset command for an environment pointing to shared
resources: deleting its resource group would also delete resources you reused.

## Step 5: Deploy the agent

Deploy the Python code to your configured Foundry project:

```powershell
azd deploy
```

Direct code deployment packages the sample and creates a hosted-agent version
named `hello-world-autopilot`. It does not require Docker or Azure Container
Registry and does not publish a Microsoft 365 app.

After deployment completes, inspect the hosted agent:

```powershell
azd ai agent show
```

The agent name is a literal value in `azure.yaml`, not derived from the
environment name. A different local environment name alone does not give you a
separate agent in the same Foundry project.

## Step 6: Publish to Microsoft 365

Review the `services.hello-world-autopilot.activity.publish` block in
[`azure.yaml`](azure.yaml) before publishing. It supplies the app information
shown in Microsoft 365:

| Field | What to review |
| --- | --- |
| `agentDisplayName` | The name users will see. The sample defaults to **Hello World Autopilot**. |
| `shortDescription`, `fullDescription` | Descriptions of what your agent does. |
| `developerName`, `developerWebsiteUrl` | The responsible developer or organization and its HTTPS support website. |
| `privacyUrl`, `termsOfUseUrl` | HTTPS links to the privacy statement and terms that apply to your app. |
| `appVersion` | The Microsoft 365 app version; the sample starts at `1.0.0`. |

Replace the sample organization and URLs if they do not apply to your app.
Keep `publishScope: tenant` for this Autopilot.

Publish the deployed agent:

```powershell
azd ai agent publish
```

The command reads the publication metadata from `azure.yaml` and submits the
app for your tenant's catalog. Successful publication is not administrator
approval: complete the next step before trying to create an instance.

If no deployed agent is found, follow
[Publication cannot find the deployed agent](#publication-cannot-find-the-deployed-agent).

## Step 7: Approve the blueprint

Ask an **AI Administrator** or **Global Administrator** in your tenant to:

1. Open [Agents in the Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested).
2. Find and approve the pending **Hello World Autopilot** blueprint, or the
   display name you configured in Step 6.
3. Verify that the approved blueprint appears in the Agent 365 registry.

## Step 8: Create an instance and try it in Teams

After the blueprint is approved, sign in to Teams with a licensed account in
the same tenant:

1. Open **Apps** > **Agents for your team**.
2. Select **Hello World Autopilot**, or your configured display name, and create
   an instance by following the Teams prompts.
3. Open a direct chat with the new instance and send
   **Say hello and tell me what you can help with.**

Expect a model-generated response, not a fixed greeting. You can also add the
instance to a group chat, or mention it in a channel message. The sample only
handles channel messages that tag the agent.

Tenant app policies can restrict which users discover, create, or use an
instance. If the approved blueprint is not available, ask your tenant
administrator to check those policies and your license.

## Optional: Change the agent's code and behavior

Edit the agent code, then deploy a new version:

```powershell
azd deploy
```

Existing sessions can continue running on their previous sandbox. From the
`hello-world` directory, stop them so the next invocation resumes against the
latest active version:

```powershell
..\scripts\stop-agent-sessions.ps1 -AgentName hello-world-autopilot
```

Pass `-Environment <environment-name>` to the script if the active environment
is not the intended target. Stopping preserves each logical session and its
persisted filesystem state. Do not delete sessions just to pick up new code.

Do not republish for code-only changes. Run `azd ai agent publish` again only
when the Microsoft 365 app manifest, metadata, or other publication-owned
configuration changes. Edit the `activity.publish` block for persistent
metadata changes; `--display-name` and `--app-version` are also available as
one-time publish overrides.

## Understand how the agent works

`agent/app.py` hosts the M365 Agents SDK application at
`POST /activity/messages` and sends supported Teams messages to the configured
model deployment through the Responses API. Foundry manages hosting and
injects the project endpoint and agent identity configuration into the runtime.
`azure.yaml` passes `AZURE_AI_MODEL_DEPLOYMENT_NAME` from the active `azd`
environment.

## Observability

The agent initializes the
[Microsoft OpenTelemetry Distro](https://learn.microsoft.com/microsoft-agent-365/developer/microsoft-opentelemetry?tabs=python)
before importing the application stack.

- **Foundry traces:** Foundry injects `APPLICATIONINSIGHTS_CONNECTION_STRING`
  into the hosted container. The distro detects it and exports application,
  Microsoft Agents SDK, HTTP, Azure SDK, and model-call telemetry to Azure
  Monitor. This is the telemetry used by the Foundry traces experience.
- **Agent 365:** Activity baggage middleware adds agent, tenant, user, channel,
  session, and conversation context. Output middleware records response spans,
  and the Agent 365 exporter sends the enriched telemetry used by Microsoft 365
  administration, Defender, and Purview experiences.

## Troubleshooting

Start with the current sample and an up-to-date Foundry agent extension
(`azd ext upgrade azure.ai.agents`), then run:

```powershell
azd ai agent doctor
```

This checks the selected environment, authentication, and deployed agent, and
prints suggested recovery commands. Use `azd ai agent doctor --local-only` to
check local configuration without contacting Azure. A successful local check
does not establish that your sign-in or cloud permissions are correct.

| Symptom | What to check |
| --- | --- |
| Provisioning cannot resolve a new model deployment | Choose a Responses-compatible OpenAI model with a default version supporting `GlobalStandard` in the selected region, and check model quota. |
| Provisioning returns an authorization error | Check the provisioning permissions in Step 1. Foundry project access alone does not grant permission to create resources or subscription-scoped deployments. |
| Provisioning reports that a saved resource is missing | Check that you selected the right environment, subscription, and parent resources. The workflow does not silently recreate resources previously selected for reuse. |
| Deployment cannot resolve the project or model | Select the intended `azd` environment, rerun `azd provision`, and confirm it completes successfully before `azd deploy`. |
| Deployment or publication returns 401 or 403 | Sign both CLIs in to the intended tenant and verify the access listed in Step 1. Publication also requires a successfully deployed agent. |
| Foundry returns 403 mentioning `Microsoft.CognitiveServices/accounts/AIServices/agents/read` | Ask an administrator to grant your account **Foundry Project Manager** at the Foundry project scope, then allow time for permissions to propagate. Resource-management access such as subscription **Contributor** does not by itself grant Foundry data-plane access. Do not recreate identities or resources to fix this error. |
| The correct role appears in IAM but Foundry still returns 403 | Confirm the assignment applies to the signed-in user. A role assigned only to the project's managed identity does not authorize your user account. |
| A new role assignment still returns 403 | Azure RBAC changes can take up to 10 minutes to propagate. Refresh the `azd` sign-in for the intended tenant and retry after propagation before adding more roles. Confirm the error's object ID matches the role assignment's user. |
| `azd` cannot resolve your access to the configured subscription | Run `azd auth login --tenant-id <tenant-id>` for that subscription's tenant, then rerun `azd ai agent doctor`. Azure CLI and `azd` have separate sign-ins; successful `az login` alone does not authenticate `azd`. |
| Deployment reports `has no digital_worker_type` | The extension could not reconcile the deployed agent with `activity.digitalWorkerType: m365`. A version may already exist even though deployment failed. Confirm extension/service compatibility and inspect the agent in Foundry before retrying. For a newly created agent with this error, retain the request IDs and contact support rather than blindly deleting it or removing `digitalWorkerType` to bypass the check. |
| Publication cannot find a deployed agent, or an older helper reports `AGENT_*_NAME` / `AGENT_*_VERSION` values were not found | Follow **Publication cannot find the deployed agent** below. This is not evidence of a stale managed identity. |
| Microsoft 365 app-package generation or publication returns 502 and reports that it cannot mint a project identity token | Follow **Stale project managed identity** below. A 502 alone does not establish this cause. |
| The agent is not available in Teams | Confirm blueprint approval, your Microsoft 365 license, and tenant app policies in Steps 7 and 8. Deployment alone does not make the agent available in Teams. |
| A channel message gets no response | Mention the agent instance in the message; untagged channel messages are not handled. |
| Updated code is not being used | Stop existing sessions with the command under **Optional: Change the agent's code and behavior**, then send a new message. |
| Teams works but Foundry traces have no application spans | Confirm the hosted container received `APPLICATIONINSIGHTS_CONNECTION_STRING` and inspect session logs for Microsoft OpenTelemetry exporter errors. |

### Publication cannot find the deployed agent

A missing-agent error can mean missing local deployment outputs, not necessarily
an empty Foundry project. This includes the retired Python helper's
`Expected exactly one deployed agent ... found 0` error.

From this sample directory, select the environment used for deployment and
inspect its project and agent:

```powershell
azd env list
azd env select <environment-name>
azd env get-value AZURE_AI_PROJECT_ID
azd ai agent doctor
azd ai agent show hello-world-autopilot
```

Confirm the project ID matches the project you open in Foundry, then inspect
its agents list and the original `azd deploy` error. A failed deployment can
leave an agent version in Foundry without saving local outputs. Resolve any
authentication or permission errors rather than treating failed queries as
empty results.

If no agent was created, resolve the deployment error and run `azd deploy` in
that environment. If a version already exists, investigate the failed deployment
step before retrying; do not delete it, guess a version, or copy another
project's outputs to bypass the error. After deployment completes, retry
`azd ai agent publish`. Missing outputs alone are not evidence of a stale
project identity.

### Stale project managed identity

App-package generation can fail with HTTP 502 when the service cannot mint a
token for a stale or deleted **Foundry project's system-assigned managed
identity**. This is separate from your CLI sign-in, the Foundry account's
identity, and the agent or blueprint identity. Fix environment and sign-in
errors first; do not reset identities in response to a generic 401, 403, or 502.

Ask an administrator to inspect the project identity. These read-only commands
show the project selected by the active `azd` environment. Run each command as
one line and stop if a command fails:

```powershell
$projectId = azd env get-value AZURE_AI_PROJECT_ID; if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($projectId)) { throw "Select the intended azd environment and complete Step 4 first." }
az resource show --ids $projectId --api-version 2025-06-01 --query "{id:id,identity:identity}" --output json
$principalId = az resource show --ids $projectId --api-version 2025-06-01 --query identity.principalId --output tsv; if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($principalId)) { throw "No project principal could be read. Stop and ask the project administrator to investigate." }
az ad sp show --id $principalId --query "{id:id,displayName:displayName,servicePrincipalType:servicePrincipalType}" --output json
```

The administrator should check whether `identity.principalId` still identifies
an existing service principal in the project's Microsoft Entra tenant and
whether it has the required resource access. Lack of permission to read the
directory is not evidence that the identity was deleted. Retain the failed
request's timestamp, correlation ID, and service error for support; do not share
access tokens. ARM can still report `SystemAssigned` and an old principal ID
after the underlying identity is deleted. Reapplying `SystemAssigned` without
changing that stale state is not a reliable repair.

**Prefer support-assisted recovery.** For a shared or production project, open
an Azure support request before changing identity state. For an isolated sample,
another option is to create a new `azd` environment and choose a **new project**
in Steps 3–4, arrange its permissions, then deploy and publish there. Leave the
original project intact while evaluating this option. A new environment name
alone does not isolate an agent in the same project; migration can require new
publication, approval, and instances and can incur charges.

**Administrator-only, disruptive repair:** if a stale or deleted identity is
confirmed and support recommends recreating it, coordinate a maintenance window
with the project owner. Do not use identity reset as routine troubleshooting:

1. Record the old principal ID, full project configuration, identity type,
   user-assigned identities (if any), and all access dependencies. Record role
   definitions, scopes, and conditions before changing anything. This read-only
   command lists the old principal's assignments in the project's subscription;
   also inventory access in other subscriptions, directory roles, and non-RBAC
   access separately:

   ```powershell
   az role assignment list --assignee-object-id $principalId --all --include-inherited --fill-principal-name false --subscription ($projectId.Split('/')[2]) --output json
   ```

2. Confirm that an administrator can regrant the recorded access to a **new
   principal ID**. Disabling a system-assigned identity interrupts every
   operation using it; re-enabling does not recover the old principal or its
   permissions. Do not proceed without a recovery plan.
3. Follow the support-approved procedure to disable and re-enable the project's
   system-assigned identity, preserving other project settings. **Read back the
   resource after every update, including failed updates**, using the
   `az resource show` command above. A request setting `identity.type=None` has
   been observed to return HTTP 400 (`Unsupported configuration`) while still
   disabling the identity. Do not assume a 400 means the state is unchanged,
   blindly retry rejected requests, or leave the project with identity `None`.
   If the API rejects an operation, inspect the actual state and have support
   guide recovery rather than improvising further PATCH requests.
4. Verify that the project reports `SystemAssigned`, the new principal exists
   in the correct tenant, and all required access has been regranted, including
   **Cognitive Services User** on the Foundry resource. Refresh `$principalId`
   with the read-only command above; do not reuse the old ID for new assignments.

After the administrator confirms that the new identity is enabled and its
permissions have propagated, retry `azd ai agent publish`. If token issuance
still fails, escalate with the captured diagnostics rather than repeatedly
recreating identities. The sample's provisioning workflow deliberately does
not perform this repair or manage role assignments. Do not use `azd down` or
delete the project, agent, or blueprint as a reset.

## References

- [What is an Autopilot in Microsoft Foundry?](https://learn.microsoft.com/azure/foundry/agents/concepts/autopilot-overview)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Publish an Autopilot in Microsoft Agent 365](https://learn.microsoft.com/azure/foundry/agents/how-to/agent-365)
- [Hosted agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions)
- [Create a Foundry project](https://learn.microsoft.com/azure/foundry/how-to/create-projects)
- [Deploy Foundry models](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/create-model-deployments)
- [Agent 365 observability concepts](https://learn.microsoft.com/microsoft-agent-365/developer/observability-concepts)
