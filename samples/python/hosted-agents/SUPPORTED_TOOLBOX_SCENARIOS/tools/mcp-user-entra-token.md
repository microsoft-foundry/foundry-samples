# MCP — User Entra Token (Microsoft first-party on-behalf-of)

Connect to a **Microsoft first-party** catalog MCP server that accepts the **calling user's Entra
token**. Foundry passes the caller's identity through on-behalf-of (OBO) — the tool acts as the user,
not the agent — so the server enforces the user's own permissions (useful for per-user mail, files,
etc.). Example server: the
[Microsoft Foundry MCP server](https://learn.microsoft.com/azure/foundry/mcp/get-started)
(`https://mcp.ai.azure.com`).

> This page covers only the **User Entra Token** parts — the audience, connection, and config-dialog
> fields. For the shared toolbox flow (create → publish → copy the endpoint), see the
> [README](../README.md#create-the-toolbox).
>
> **How this differs from the other passthrough modes.** All three run the tool as the signed-in
> **user**; they differ in the OAuth app and consent:
> - **User Entra Token** *(this page)* — No OAuth app to set up (Foundry uses its own). No user consent needed. Only some catalog MCP support it.
> - **[Managed OAuth passthrough](mcp-oauth-managed.md)** — No OAuth app to set up (Foundry uses its own). User consents on first use. Only some catalog MCP support it.
> - **[Custom OAuth passthrough](mcp-oauth-custom.md)** — You register your own OAuth app. User consents on first use. Works with any server, including non-catalog.

## Create the tool connection & toolbox

### Foundry Toolkit in VS Code

1. Follow the README's [Create the toolbox](../README.md#create-the-toolbox) steps to open the config dialog — for a first-party server, select it from the **Catalog** tab (e.g. **Foundry MCP**).
2. Fill in the config dialog and click **Connect**:

   > Note: on a **catalog** MCP server, the **User Entra Token** authentication is available only when that server supports it.

   | Field | Value |
   |-------|-------|
   | **Authentication** | `OAuth 2.0` (Foundry forwards the caller's Entra token — no Client ID or secret) |
   | **OAuth Provider** | `Managed OAuth` |
   | **Audience** | leave the prefilled default, or set the Entra resource the server validates tokens against, e.g. `https://mcp.ai.azure.com` (see [Finding the audience](#finding-the-entra-audience-for-an-mcp-server)) |

### `azd` CLI

Create the connection once, then create the toolbox one of two ways:

- **Way A — standalone toolbox** (`azd ai toolbox create`): builds the toolbox on its own. Best for
  testing, or when the toolbox is shared across agents.
- **Way B — toolbox in an agent project** (`azure.yaml` + `azd deploy`): declares the toolbox next to
  your agent and ships them together. Best when the toolbox belongs to one agent project.

#### 1. Create the connection (both ways)

```bash
azd ai connection create foundrymcpconn \
  --kind remote-tool \
  --target https://mcp.ai.azure.com \
  --auth-type user-entra-token \
  --audience https://mcp.ai.azure.com \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

> `--auth-type user-entra-token` forwards the calling user's Entra token — no `--client-id` /
> `--client-secret` / `--scopes`. Swap `--target` and `--audience` for another catalog server (see
> [Finding the audience](#finding-the-entra-audience-for-an-mcp-server)).

#### Way A — standalone toolbox (`toolbox.yaml`)

1. Write `toolbox.yaml` referencing the connection by name:

   ```yaml
   # toolbox.yaml
   description: user-entra-token-mcp toolbox
   tools:
     - type: mcp
       server_label: foundry-mcp
       project_connection_id: foundrymcpconn
       require_approval: "never"
   ```

2. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

3. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`:

   ```bash
   azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/agent-tools/versions/1/mcp?api-version=v1"
   ```

#### Way B — toolbox in an agent project (`azure.yaml`)

1. Declare the toolbox and agent together in `azure.yaml`, referencing the connection by name:

   ```yaml
   # azure.yaml
   requiredVersions:
     azd: '>=1.34.2'
     extensions:
       azure.ai.agents: '>=1.0.0-beta.19'
   name: my-agent-project
   services:
     agent-tools:
       host: azure.ai.toolbox
       tools:
         - type: mcp
           server_label: foundry-mcp
           project_connection_id: foundrymcpconn
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

2. Deploy the toolbox (and agent):

   ```bash
   azd deploy agent-tools
   ```


## Finding the Entra audience for an MCP server

An Entra pass-through connection requires an **audience** — the Entra resource that the MCP server validates tokens against. For the Microsoft Foundry MCP server (`https://mcp.ai.azure.com`), read it from the server's OAuth protected-resource metadata:

```bash
curl https://mcp.ai.azure.com/.well-known/oauth-protected-resource
```

```jsonc
{
  "resource": "https://mcp.ai.azure.com",
  "authorization_servers": ["https://login.microsoftonline.com/common/v2.0"],
  "scopes_supported": ["https://mcp.ai.azure.com/Foundry.Mcp.Tools"]
}
```

Use the `resource` value (`https://mcp.ai.azure.com`) as the audience.

> For connector-backed MCP servers (for example Microsoft 365 / WorkIQ servers such as Outlook Mail), the audience is instead published in the Foundry Tools Catalog. Look it up with the helper scripts in [`scripts/`](../../agent-framework/responses/04-foundry-toolbox/src/agent-framework-agent-with-foundry-toolbox-responses/scripts/): run `./scripts/list-foundry-connectors.ps1 -ConnectorName <name>` (or `./scripts/list-foundry-connectors.sh -n <name>`) and read `AzureActiveDirectoryResourceId` (equivalently `resourceUri`) under `properties.x-ms-connection-parameters`. Run the script with no connector name to list every connector with its name, title, and auth type.



## Notes

- The tool runs as the **calling user** — the downstream server enforces that user's permissions.
- For connector-backed servers (e.g. Microsoft 365 / Outlook Mail), find the audience in the
  Foundry Tools Catalog rather than the `.well-known` endpoint.


# Troubleshooting

-  Entra pass-through forwards the caller's identity

   The Foundry MCP tool authenticates with **Entra pass-through** (`foundrymcpconn`): Foundry forwards the
   calling user's Entra token to `https://mcp.ai.azure.com`. The token is forwarded both from the Foundry
   portal **Agent Playground** (signed-in user) and by `azd ai agent invoke` (the developer's Entra token),
   so the tools operate as that user and only act on resources the user can already access. The Foundry MCP
   server requires no extra license — just access to the Foundry project.

   `UserEntraToken` always forwards the invoking user's identity to the downstream service. A local
   invocation uses the signed-in `az login` user; **Agent Playground** and `azd ai agent invoke` use
   their signed-in user; and a raw request uses the user represented by its bearer token. It does not
   silently fall back to the hosted agent's managed identity. If the request has no valid user
   identity, or that user cannot access the target resources, the tool returns an authorization error
   even though it is discovered and called correctly.

   > Some other Entra pass-through MCP servers add their **own** entitlement checks on top of the token. For
   > example, the Microsoft 365 / WorkIQ servers (Outlook Mail, Teams) require the caller to hold a
   > **Microsoft 365 Copilot (Business Chat)** license; without it they fail with
   > `WorkIQ license check failed. Required service plan(s): [M365_COPILOT_BUSINESS_CHAT]`. That is a
   > property of those servers, not of Entra pass-through itself.

## References

- [MCP tool documentation](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Microsoft Foundry MCP server](https://learn.microsoft.com/azure/foundry/mcp/get-started)
