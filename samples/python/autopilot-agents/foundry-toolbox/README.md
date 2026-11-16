# Foundry Toolbox Autopilot

Deploy a Python Autopilot that answers questions in Teams:

- Finds official Microsoft documentation and code samples with Microsoft Learn.
- Searches the public web for recent announcements and other current information.
- Combines documentation and web results into an answer with source links.

Microsoft Agent Framework accesses both sources through **one Foundry Toolbox**:
[Microsoft Learn MCP](https://learn.microsoft.com/training/support/mcp) and
[Bing-backed Foundry Web Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search).
Both are read-only and require no downstream user credentials. The hosted agent
uses managed identity to access the Foundry project, model, and Toolbox.

Agent Framework discovers the Toolbox functions, exposes them to the model,
and invokes the tools the model selects. It returns tool results to the model
and manages additional calls when needed, letting one answer draw on both
sources without a hand-written tool-dispatch loop.

The agent responds to Teams direct messages, group chats, and channel messages
that mention it. Each question is standalone; include the context it needs
in your message.

This preview sample assumes familiarity with the
[Hello World walkthrough](../hello-world/README.md).

## Step 1: Check the prerequisites

Use the tools, tenant setup, and resource permissions described in
[Hello World prerequisites](../hello-world/README.md#step-1-install-the-prerequisites).
This sample requires **Python 3.13**, **azd 1.32.0 or later**, and the
**azure.ai.agents extension 1.0.0-beta.16 or later**. Choose a Foundry project
with Toolbox support and a model supporting the Responses API and function calling.
Check [Web Search model and region support](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions#tool-support-by-region-and-model)
and that subscription policy allows Web Search.

Install the additional Toolbox extension **1.0.0-beta.9 or later**:

```powershell
azd ext install azure.ai.toolboxes
```

If already installed, use `azd ext upgrade azure.ai.toolboxes`.
The developer needs **Foundry User** or equivalent Toolbox data-plane permissions
at project scope. Arrange runtime model and Toolbox access for the hosted
identity as well; see [Toolbox prerequisites](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox#prerequisites)
and [hosted-agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions).

General Web Search needs no separate Bing resource, API key, or project connection,
but **incurs Bing grounding charges in addition to model usage**. Search data
is processed outside Foundry's compliance and geographic boundaries.
Review the [Web Search terms, pricing, and data handling](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search).
Use public inputs only; do not send secrets, private code, personal information,
or confidential questions to either source.

## Step 2: Sign in and select an environment

From `samples\python\autopilot-agents`, enter this sample's directory. Run all
subsequent commands there in PowerShell 7. Keep the parent `scripts` directory
when copying the sample; provisioning and session updates use its shared helpers.

```powershell
Set-Location .\foundry-toolbox
az login --tenant <tenant-id>
azd auth login --tenant-id <tenant-id>
azd env new my-toolbox-autopilot
```

No existing `azd` environment is required.

## Step 3: Provision, configure the Toolbox, and deploy

```powershell
azd provision
```

Provisioning lets you create or reuse a resource group, Foundry resource, project,
and model deployment. It does not grant permissions; arrange project and
model access as described in Hello World before deployment.

Create the Toolbox in that project using [toolbox.yaml](toolbox.yaml):

```powershell
$projectEndpoint = azd env get-value FOUNDRY_PROJECT_ENDPOINT
azd ai toolbox create public-docs `
  --project-endpoint $projectEndpoint `
  --from-file .\toolbox.yaml `
  --output json
azd ai toolbox show public-docs --project-endpoint $projectEndpoint
azd env set TOOLBOX_ENDPOINT (azd env get-value TOOLBOX_PUBLIC_DOCS_MCP_ENDPOINT)
```

The definition combines an anonymous Microsoft Learn MCP source with native
Foundry Web Search. Keep its tool names and allowlists unchanged: the sample
accepts only the three Learn functions and `web_search`.
The create command saves the version-specific MCP endpoint in the active
environment; the last command copies it to the agent's `TOOLBOX_ENDPOINT`.

```powershell
azd deploy
azd ai agent show
```

Deployment packages the Python code directly, without Docker, and creates the
hosted agent **foundry-toolbox-autopilot**. It does not publish a Microsoft 365 app.
Resource creation and model/Web Search usage can incur charges.

## Step 4: Publish and create an instance

Review the publication metadata in [azure.yaml](azure.yaml), then publish:

```powershell
azd ai agent publish
```

Have an **AI Administrator** or **Global Administrator** approve the
**Foundry Toolbox Autopilot** blueprint. Create an instance through Teams
**Apps > Agents for your team**, following
[Hello World approval and instance creation](../hello-world/README.md#step-7-approve-the-blueprint).
Deployment and publication alone do not make an instance available;
tenant approval, app policies, and licensing still apply.

## Step 5: Try the agent in Teams

In a direct chat with the instance, try each source:

> Find Microsoft documentation about Foundry Toolboxes and include source links.

Expect an answer grounded in Microsoft Learn documentation with links.

> Use web search to find recent public Microsoft Foundry announcements.
> Include source links and publication dates.

Expect a summary of recent announcements with source links and publication
dates when available. Then ask a question combining both sources:

> Use Microsoft Learn to explain Foundry Toolboxes, then use web search to
> find recent public announcements about them. Distinguish the documentation
> from the announcements, include publication dates, and link to both sources.

The reply should combine official guidance with recent announcements and
include source links for both. You can also add the instance to a group chat
or mention it in a channel.

## Updating the agent

For code or runtime-setting changes:

```powershell
azd deploy
..\scripts\stop-agent-sessions.ps1 -AgentName foundry-toolbox-autopilot
```

Stopping old sandboxes preserves logical sessions and lets subsequent invocations
use the updated deployment. Republish only when publication metadata changes.
Avoid `azd down` on environments using shared resources.

## References

- [Use a toolbox with a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/use-toolbox-hosted-agent)
- [Microsoft Agent Framework Toolbox integration](https://learn.microsoft.com/agent-framework/integrations/by-component/tools/foundry-toolbox)
- [Bing-backed Foundry Web Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search)
