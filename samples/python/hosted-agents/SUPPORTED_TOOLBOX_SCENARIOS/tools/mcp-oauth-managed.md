# MCP — OAuth Identity Passthrough (Managed)

Connect to a catalog MCP server via OAuth2 where **Foundry manages the app registration** — you
supply no client ID or secret. Example server: **GitHub**
(`https://api.githubcopilot.com/mcp`, connector `foundrygithubmcp`). On first use, the tool returns a
**consent URL**; the user opens it and completes the consent flow before the tool can run.

> This page covers only the **managed OAuth passthrough** parts — the connection and config-dialog
> fields. For the shared toolbox flow (create → publish → copy the endpoint), see the
> [README](../README.md#create-the-toolbox).
>
> **How this differs from the other passthrough modes.** All three run the tool as the signed-in
> **user**; they differ in the OAuth app and consent:
> - **Managed OAuth passthrough** *(this page)* — No OAuth app to set up (Foundry uses its own). User consents on first use. Only some catalog MCP support it.
> - **[Custom OAuth passthrough](mcp-oauth-custom.md)** — You register your own OAuth app. User consents on first use. Works with any server, including non-catalog.
> - **[User Entra Token](mcp-user-entra-token.md)** — No OAuth app to set up (Foundry uses its own). No user consent needed. Only some catalog MCP support it.

## Create the tool connection & toolbox

### Foundry Toolkit in VS Code

1. Follow the README's [Create the toolbox](../README.md#create-the-toolbox) steps to open the config dialog — for a managed connector, select the server from the **Catalog** tab (e.g. **GitHub**).
2. Fill in the config dialog and click **Connect**:

   > Note: on a **catalog** MCP server, the **OAuth Identity Passthrough** authentication and its **Managed** OAuth provider are available only when that server supports them.

   | Field | Value |
   |-------|-------|
   | **Authentication** | `OAuth 2.0` |
   | **OAuth Provider** | `Managed OAuth` (vs `Custom OAuth` — see [MCP OAuth custom app](mcp-oauth-custom.md)) |

### `azd` CLI

Create the connection once, then create the toolbox one of two ways:

- **Way A — standalone toolbox** (`azd ai toolbox create`): builds the toolbox on its own. Best for
  testing, or when the toolbox is shared across agents.
- **Way B — toolbox in an agent project** (`azure.yaml` + `azd deploy`): declares the toolbox next to
  your agent and ships them together. Best when the toolbox belongs to one agent project.

#### 1. Create the connection (both ways)

```bash
azd ai connection create ghmcpoauth \
  --kind remote-tool \
  --target https://api.githubcopilot.com/mcp \
  --auth-type oauth2 \
  --connector-name foundrygithubmcp \
  --metadata type=gateway_connector \
  --metadata "toolEntityId=azureml://location/eastus/apiCenter/registry-prod-bl/type/tools/objectId/github-mcp-server/version/1" \
  --metadata 'connectionproperties={"connectorName":"foundrygithubmcp"}' \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

> `--connector-name` names the Foundry-managed OAuth connector (`foundrygithubmcp` for GitHub). No
> `--client-id` / `--client-secret` / `--scopes` — Foundry supplies them.
>
> GitHub's managed OAuth is brokered through a **Connector Namespace gateway**. The three `--metadata`
> flags register the connection into that gateway:
> - `type=gateway_connector` — routes the connection through the connector gateway.
> - `toolEntityId` — identifies the catalog tile.
> - `connectionproperties` — a **stringified JSON** object (not a nested object) naming the connector.


#### Way A — standalone toolbox (`toolbox.yaml`)

1. Write `toolbox.yaml` referencing the connection by name:

   ```yaml
   # toolbox.yaml
   description: github-mcp-oauth toolbox
   tools:
     - type: mcp
       server_label: github
       project_connection_id: ghmcpoauth
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
           server_label: github
           project_connection_id: ghmcpoauth
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


## Notes

- The **first** invocation triggers OAuth consent — the tool call returns MCP code `-32006` with a
  consent URL. Complete consent, then retry.
- Use a managed connector when you don't need control over the OAuth app. For custom scopes, your
  own tenant, or a non-catalog server, use [MCP OAuth custom app](mcp-oauth-custom.md).
