# MCP — Unauthenticated (public server)

Connect the agent to a **public MCP server** that requires no authentication — for example the
[Microsoft Learn MCP server](https://learn.microsoft.com/training/support/mcp)
(`https://learn.microsoft.com/api/mcp`). The server URL is given inline on the tool; no connection
resource is needed.

> This page covers only the **unauthenticated** parts — the config-dialog fields. For the shared
> toolbox flow (create → publish → copy the endpoint), see the
> [README](../README.md#create-the-toolbox).

## Create the tool connection & toolbox

### Foundry Toolkit in VS Code

1. Follow the README's [Create the toolbox](../README.md#create-the-toolbox) steps to open the **Model Context Protocol (MCP)** config dialog.
2. Fill in the config dialog and click **Connect**:

   > Note: on a **catalog** MCP server, the **Unauthenticated** option is available only when that server supports it.

   | Field | Value |
   |-------|-------|
   | **Authentication** | `Unauthenticated` |


### `azd` CLI

Create the toolbox one of two ways (no connection to create — the server URL is inline):

- **Way A — standalone toolbox** (`azd ai toolbox create`): builds the toolbox on its own. Best for
  testing, or when the toolbox is shared across agents.
- **Way B — toolbox in an agent project** (`azure.yaml` + `azd deploy`): declares the toolbox next to
  your agent and ships them together. Best when the toolbox belongs to one agent project.

#### Way A — standalone toolbox (`toolbox.yaml`)

1. Write `toolbox.yaml` with the server URL inline:

   ```yaml
   # toolbox.yaml
   description: public-mcp toolbox
   tools:
     - type: mcp
       server_label: learn_mcp
       server_url: "https://learn.microsoft.com/api/mcp"
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

1. Declare the toolbox and agent together in `azure.yaml`, with the server URL inline:

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
           server_label: learn_mcp
           server_url: "https://learn.microsoft.com/api/mcp"
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
