# Toolbox Autopilot

Build a Microsoft Foundry Autopilot that responds in Microsoft Teams and uses
tools from a centrally managed Foundry Toolbox.

The sample toolbox contains:

- **Web Search** for current public information.
- **Code Interpreter** for calculations and data analysis.
- A public **MCP server** for the Azure REST API specifications repository.

The MCP server is a non-Foundry external service. Requests sent to it can leave
Foundry's compliance boundary and are governed by that service's terms and data
handling practices. Replace or remove it when those terms do not fit your use
case.

The Autopilot supports Teams direct messages, group chats, and channel messages
that mention it.

## How it works

`azure.yaml` provisions a Foundry project, model deployment, and toolbox before
deploying the hosted agent. The toolbox exposes all three tools through one
MCP-compatible endpoint. The endpoint is injected into the agent as
`TOOLBOX_ENDPOINT`.

`agent/app.py` reuses one process-scoped model client and credential. For each
Teams message, it creates a request-scoped Agent Framework agent and
`FoundryToolbox`. Request scope is important because the toolbox connection
captures the current Foundry caller context used for authentication and
correlation. The model selects and invokes tools, then the Activity host sends
the final answer back to Teams.

Foundry manages the toolbox credentials, endpoint, tool definitions, and
versioning. The agent code only connects to the toolbox endpoint.

## Step 1: Install prerequisites

Install:

1. [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
   1.32.0 or later.
2. [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli).
3. Python 3.13 or later.
4. [PowerShell 7](https://learn.microsoft.com/powershell/scripting/install/installing-powershell).

Install the unified Foundry extension:

```powershell
azd ext install microsoft.foundry
```

You also need an Azure subscription and a tenant with Microsoft Agent 365 and
qualifying Microsoft 365 licensing. The model and external tool calls can incur
charges.

Arrange this access before deployment:

| Who | Required access |
| --- | --- |
| Person provisioning resources | Contributor on the target resource group or equivalent resource-management permissions. |
| Developer deploying the agent and toolbox | Foundry Project Manager on the Foundry project. |
| Person publishing the Autopilot | Microsoft 365 license and Foundry project data-plane access. |
| Administrator approving the blueprint | AI Administrator or Global Administrator, plus a Microsoft 365 license. |
| Person creating or using an instance | Microsoft 365 license and access allowed by tenant app policies. |

## Step 2: Sign in

Run commands from this sample directory. Authenticate both CLIs against the
tenant where you will deploy and publish:

```powershell
az login --tenant <tenant-id>
azd auth login --tenant-id <tenant-id>
```

## Step 3: Create an azd environment

```powershell
azd env new my-toolbox-autopilot
```

## Step 4: Provision and deploy

Provision the Foundry project, model, toolbox, and hosted agent:

```powershell
azd up
```

The `autopilot-tools` toolbox is deployed before the agent. Its generated MCP
endpoint is passed to `TOOLBOX_ENDPOINT`; you do not need to copy the URL.

After deployment, inspect the resources:

```powershell
azd ai toolbox show autopilot-tools
azd ai agent show
```

To use a different model, edit the `ai-project.deployments` block in
`azure.yaml`. To change the tool collection, edit
`services.autopilot-tools.tools` and run:

```powershell
azd deploy --all
```

For code-only changes, use `azd deploy`.

## Step 5: Publish to Microsoft 365

Review `services.toolbox-autopilot.activity.publish` in `azure.yaml`, especially
the display name, descriptions, developer details, privacy URL, terms URL, and
app version. Replace the sample organization and URLs when needed.

Publish the deployed hosted agent:

```powershell
azd ai agent publish
```

Publication submits the Autopilot blueprint to the tenant catalog. It does not
approve the blueprint.

## Step 6: Approve the blueprint

Ask an AI Administrator or Global Administrator to:

1. Open [Agents in the Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested).
2. Find and approve **Toolbox Autopilot**.
3. Verify that the blueprint appears in the Agent 365 registry.

## Step 7: Create an instance and try the tools

In Teams, open **Apps** > **Agents for your team**, select **Toolbox Autopilot**,
and create an instance.

Try prompts that make each tool choice clear:

- **Web Search:** `What changed in Microsoft Foundry this week? Include sources.`
- **Code Interpreter:** `Use Python to calculate the monthly payment on a $400,000 loan at 6.5% for 30 years.`
- **MCP:** `Find the Azure REST API specification for creating a Cognitive Services account and summarize the required request fields.`

You can also add the instance to a group chat or mention it in a channel.

## Customize the toolbox

Toolboxes can include built-in tools, remote MCP servers, OpenAPI tools, Azure
AI Search, file search, A2A agents, Work IQ, Fabric IQ, and other supported
types. Authentication and project connections belong in the toolbox
configuration rather than in agent code.

When a toolbox grows beyond roughly 10 tools, enable
[Tool Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-search)
so the model discovers relevant tools on demand instead of receiving every tool
definition on each turn.

Each toolbox version is immutable. Test a version-specific endpoint before
promoting it as the default when you operate shared production toolboxes.

## Update the agent

After changing agent code:

```powershell
azd deploy
..\scripts\stop-agent-sessions.ps1 -AgentName toolbox-autopilot
```

Stopping sessions preserves their logical state and lets the next invocation
resume on the latest agent version. Do not republish for code-only changes.

After changing toolbox configuration:

```powershell
azd deploy --all
```

## Observability

AgentServer configures Foundry and Agent 365 OpenTelemetry. Foundry injects the
Application Insights connection string for hosted execution. Toolbox calls are
correlated with the Activity request through the platform call ID.

The sample keeps generative-AI message content capture disabled. Its explicit
message log still records message text, so do not use sensitive test data.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Toolbox tools do not load | Confirm `azd up` or `azd deploy --all` completed and `TOOLBOX_ENDPOINT` was injected. |
| A toolbox call returns 401 or 403 | Verify the hosted agent identity and developer have the required Foundry project access. |
| MCP enumeration fails | Check the availability of the public `api_specs` MCP server. One failing source can prevent the toolbox from listing tools. |
| The wrong tool is selected | Improve tool descriptions and agent instructions; use Tool Search for larger collections. |
| The agent is unavailable in Teams | Confirm publication, administrator approval, Microsoft 365 licensing, and tenant app policies. |
| A channel message gets no response | Mention the agent in the channel message. |
| Updated code is not used | Stop existing hosted sessions after deployment. |

## References

- [What is Toolbox in Microsoft Foundry?](https://learn.microsoft.com/azure/foundry/agents/concepts/toolbox-overview)
- [Create and manage a toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
- [Foundry Toolkit Tool Catalog](https://code.visualstudio.com/docs/intelligentapps/tool-catalog)
- [Hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [What is an Autopilot?](https://learn.microsoft.com/azure/foundry/agents/concepts/autopilot-overview)
- [Publish an Autopilot](https://learn.microsoft.com/azure/foundry/agents/how-to/agent-365)
