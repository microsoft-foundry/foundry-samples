# Hosted agent blueprint sign-in and AgentOnBehalfOfUser (C#)

This sample demonstrates two consecutive identity boundaries with a Microsoft Foundry hosted agent. A C# public client signs in a user and calls the agent using the agent blueprint's `access_agent` scope. The .NET Agent Framework agent uses a Foundry Toolbox backed by a scopes-only `AgentOnBehalfOfUser` (agent on behalf of user) connection to call a small, Entra-protected MCP server. The MCP tool returns only a greeting; it never returns a token or identity claims.

```text
signed-in user -> C# client -> AgentBlueprint endpoint -> hosted agent
                                              -> Toolbox -> AgentOnBehalfOfUser connection -> greet MCP tool
```

The file-based C# client signs in with a device code and makes one agent request per run. First-time downstream consent requires following the returned link and running the client again. It uses the OpenAI .NET Responses SDK with a blueprint-scoped bearer token policy. The hosted agent in `src/Program.cs` registers one Foundry Toolbox as server-side tools; Foundry brokers the delegated tool call, not the agent process. The MCP server's entry point and greeting tool share `mcp-server/Program.cs`; the small Functions project file keeps `azd` packaging compatible, and `host.json` sets the MCP webhook authorization level. This sample provisions its own resources and does not depend on another sample's deployment.

## Prerequisites

- .NET 10 SDK, Azure CLI, PowerShell 7, and [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) with the `microsoft.foundry`, `azure.ai.agents`, and `azure.ai.toolboxes` extensions.
- An Azure subscription where you can provision a Foundry project with hosted agents enabled, a model deployment, and a Windows App Service Standard plan. Provisioning these resources incurs charges. Choose a region where these resources and the `gpt-5-mini` `GlobalStandard` deployment are available with quota for your subscription. The model and SKU can be changed through `AZURE_AI_MODEL_NAME`, `AZURE_AI_MODEL_VERSION`, and `AZURE_AI_MODEL_SKU` before provisioning.
- Permission to assign **Foundry User** at the project scope, create two single-tenant Entra application registrations, update the Foundry-created agent blueprint as its owner (or with an applicable administrator role), and configure the MCP application. Directory policy can prevent preauthorization of the interactive client; the setup script fails rather than switching to broader consent.
- In Microsoft tenants, a Service Tree ID for the Entra applications. Set `SERVICE_MANAGEMENT_REFERENCE` to that ID in the azd environment before provisioning. Other tenants may leave it unset unless their policies require it.
- An account in the same tenant with the provisioning permissions above that can sign in to the sample client. You can use that same account throughout the walkthrough. A separate test user is optional if you want to verify the agent blueprint path without Foundry project RBAC.

Run these commands from this sample's root. The Azure CLI and `azd` sessions must use the **provisioning account in the same tenant**. When the C# client prompts for device-code sign-in, you may use that account again or a different user in the same tenant. The server and client use Entra identity; they do not require application secrets.

## 1. Provision and deploy

```powershell
az login --tenant <tenant-id>
az account set --subscription <subscription-id>
azd auth login --tenant-id <tenant-id>
azd ext install microsoft.foundry
azd ext install azure.ai.agents
azd ext install azure.ai.toolboxes
azd env new <environment-name>
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION <azure-region>
azd provision
azd deploy mcp
.\scripts\Provision-Toolbox.ps1
azd deploy hosted-greeting
.\scripts\Configure-HostedAgentAccess.ps1
```

In a Microsoft tenant, run `azd env set SERVICE_MANAGEMENT_REFERENCE <service-tree-id>` before `azd provision`. Other tenants may set it if their directory policy requires it.

Run the steps in order: provisioning creates the project, model, sample-owned MCP resource application and public client registration, Function App, and `AgentOnBehalfOfUser` project connection. Deploy the Functions MCP greeting tool before registering it in the Toolbox. `Provision-Toolbox.ps1` assigns the provisioning account **Foundry User** on the new project if needed, verifies the connection, and registers the Toolbox; then deploy the hosted agent. `Configure-HostedAgentAccess.ps1` does not create an agent or identity: it configures the deployed agent's two endpoint authorization schemes, reads its generated blueprint and agent identity, and updates App Service Authentication to allow only that agent identity as the downstream client. The project connection uses exactly one `Greeting.Read` delegated scope with no authored audience. If a step cannot be read back, setup stops with an error. Do not use `azd up` to skip the tool deployment and Toolbox ordering.

The Windows Function App uses a Standard S1 plan and identity-based storage. Its MCP endpoint is `/runtime/webhooks/mcp`. The Functions MCP webhook does not require a Functions key, but App Service Authentication requires an Entra token for this MCP application and restricts callers to the generated agent identity. Before the agent exists, the App Service Authentication allowlist denies all callers.

## 2. Authorize the two legs

As the **provisioning account**, explicitly approve the narrow application changes:

```powershell
.\scripts\Configure-Authorization.ps1 -ConfirmAuthorization
```

The script declares the blueprint's exact `access_agent` delegated permission on the sample public client and preauthorizes that client on the blueprint. For the downstream leg, it declares the sample-owned MCP application's `Greeting.Read` scope on the agent blueprint and configures that MCP resource for inheritance of all allowed delegated scopes **but no application roles**. It removes this scope's preauthorization for the blueprint on the MCP application, if present, while preserving unrelated permissions. The MCP application exposes only `Greeting.Read`; the script does not enumerate individual scopes in the inheritance entry. The client-to-agent leg is preauthorized, but the downstream leg **needs user consent unless an administrator has already granted the delegated MCP permission**. The script does not grant that permission. It preserves other application permissions and checks Graph readback. It doesn't assign a separate test user Foundry RBAC or give the agent application-only access.

The client-to-agent token targets `api://<blueprint-client-id>/access_agent`; the Toolbox's MCP connection requests `api://<mcp-application-id>/Greeting.Read`. The MCP protected-resource metadata identifies its HTTPS endpoint separately. These are distinct tokens, audiences, and authorization decisions. `AzureRbac` remains on the endpoint for development tools, but this client uses `AgentBlueprint` and has no Foundry project RBAC requirement.

## 3. Run the client

In PowerShell, load the nonsecret identifiers that `azd` recorded for this environment:

```powershell
azd env get-values | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)="(.*)"$') {
        Set-Item "Env:$($Matches[1])" $Matches[2]
    }
}
```

When the client prints a device-code sign-in URL and code, open the URL and enter the code using **the account you want to test** in the same tenant. This can be your provisioning account:

```powershell
dotnet run --file client/AgentClient.cs
```

The client-to-agent `access_agent` permission is preauthorized during setup, but the **downstream MCP `Greeting.Read` permission still requires consent** unless an administrator has already granted that delegated permission. On an MCP `oauth_consent_request`, the client prints an HTTPS consent link and exits with code 2. As the **same user** who signed in to the client, open that link, review the requested permission, and consent if your tenant allows it. Then run `dotnet run --file client/AgentClient.cs` again. The new process prompts for a device-code sign-in again because this small sample does not persist user tokens or share the Azure CLI/`azd` credential cache. A successful greeting, not the consent page alone, confirms the tool call. If consent is blocked or requires an administrator, contact the tenant administrator; do not use a broader grant as a workaround. Each user needs their own consent unless an authorized administrator has already granted the exact delegated MCP permission for the tenant.

After consent, the client prints the agent's response to the greeting prompt, including the invocation ID returned by the Functions tool. A greeting with an invocation ID is evidence of an end-to-end agent-to-MCP tool call, not independent proof of the downstream token's user claims or `Greeting.Read` scope. The ID makes each greeting distinct but is not independently verified by the client. An agent request failure can point to the blueprint sign-in leg; if the agent reports a tool failure, inspect the downstream leg. The client requests a scoped token and does not print it. In automated or multi-user environments, use a dedicated client setup for each caller rather than sharing cached user credentials.

## Cleanup

From this sample's root, select the environment you deployed and save the two sample-owned Entra application object IDs **before** removing Azure resources. Confirm the Azure CLI is in the same tenant and subscription, and review the displayed applications before deleting anything:

```powershell
azd env select <environment-name>
$tenantId = azd env get-value AZURE_TENANT_ID
$subscriptionId = azd env get-value AZURE_SUBSCRIPTION_ID
$clientObjectId = azd env get-value GREETING_CLIENT_OBJECT_ID
$mcpObjectId = azd env get-value MCP_API_APPLICATION_OBJECT_ID
$account = az account show -o json | ConvertFrom-Json
if ($account.tenantId -ne $tenantId -or $account.id -ne $subscriptionId) { throw 'Sign in to the deployment tenant and subscription first.' }
az ad app show --id $clientObjectId --query '{id:id,displayName:displayName}' -o table
az ad app show --id $mcpObjectId --query '{id:id,displayName:displayName}' -o table
```

Once you have confirmed those are this sample's interactive client and MCP resource application, use the **same PowerShell session** to remove the sample's Azure resources, then its two Entra registrations:

```powershell
azd down
az ad app delete --id $clientObjectId
az ad app delete --id $mcpObjectId
```

`azd down` deletes the sample's Azure resource group and its Foundry account, project, model, Toolbox, connection, Function App, App Service plan, and storage account. It does **not** reliably remove applications created through the [Microsoft Graph Bicep extension](https://github.com/Azure/azure-dev/issues/4724); deleting these two single-tenant registrations also removes their home-tenant service principals. Do not delete the Foundry-generated blueprint or agent identity by substituting their IDs into these commands. `azd down` does not remove your local source files or `.azure` environment.

## Troubleshooting and validation boundaries

- **Provisioning or agent setup fails:** check available `gpt-5-mini` `GlobalStandard` quota and hosted-agent availability in the selected region. A newly created Foundry account can report an in-progress operation; wait for it to succeed before retrying `azd provision`. A fresh **Foundry User** assignment can take time to propagate before Toolbox setup can read the project; confirm the assignment and retry `Provision-Toolbox.ps1` if it returns 403. Do not assume a broader role assignment is required.
- **401 from the agent:** check the public client registration, blueprint `access_agent` preauthorization, token audience, and endpoint schemes. Obtaining a token and satisfying endpoint authorization are separate gates.
- **Tool call fails after consent:** check that the hosted runtime registered the `hosted-greeting-tools` Toolbox, its `AgentOnBehalfOfUser` connection has the exact scope, the blueprint has the MCP permission declaration and inheritance entry, and the Function App is available with the generated agent identity in its App Service Authentication allowlist.
- **Consent or policy challenge:** a consent link is expected when the user has not consented and no administrator has granted the delegated MCP permission. If a later run still requests consent, confirm the same user completed consent and check tenant policy. If the user cannot consent, ask an authorized administrator to review the exact permission; do not claim a successful greeting or grant tenant-wide access automatically.
- **Identity evidence:** App Service Authentication validates the Entra token, audience, and calling application before the Functions MCP tool runs. `Greeting.Read` is exposed on the resource registration and requested by the connection; this greeting-only sample does not separately inspect the delegated scope or user claims inside the function. The greeting and invocation ID do not expose claims or independently prove the downstream token's contents, and no raw bearer token should appear in prompts, output, or logs.

`sample.yaml` checks build readiness; it does not opt into live-service validation because that would provision billable infrastructure and tenant applications without dedicated cleanup. This sample is explicitly excluded from the shared hosted-agent cloud CI matrix in the [whole-sample CI skiplist](../../../../../.azure-pipelines/scripts/hosted-agent-samples-ci-skiplist). Its end-to-end walkthrough requires interactive blueprint-scoped user sign-in, downstream delegated consent, and tenant application configuration and cleanup that the shared runner does not supply. Validate this identity flow manually using the walkthrough above; an application-only or Azure RBAC call is not equivalent coverage.

The sample uses the current preview authorization contract described in [agent endpoint authorization](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-endpoint-authorization) and [user delegation](https://learn.microsoft.com/azure/foundry/agents/concepts/user-delegation); confirm availability in your tenant and region before deploying.
