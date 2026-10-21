# MCP — Key-based

Connect to an MCP server that authenticates with a **static key** — for example the GitHub MCP
server with a Personal Access Token injected as a Bearer token.

> This page covers only the **key-based auth** parts — the connection and config-dialog fields. For the
shared toolbox flow (create → publish → copy the endpoint), see the
[README](../README.md#create-the-toolbox).


## Create the tool connection & toolbox
### Foundry Toolkit in VS Code

1. Follow the README's [Create the toolbox](../README.md#create-the-toolbox) steps to open the **Model Context Protocol (MCP)** config dialog.
2. Fill in the config dialog and click **Connect**:

   > Note: on a **catalog** MCP server, the **Key Based** option is available only when that server supports it.

   | Field | Value |
   |-------|-------|
   | **Authentication** | `Key Based` |
   | **Credentials → Authorization** | header name (e.g. `Authorization`) `:` your key (e.g. `Bearer <github_pat>`) |

### `azd` CLI

Create the connection once, then create the toolbox one of two ways:

- **Way A — standalone toolbox** (`azd ai toolbox create`): builds the toolbox on its own. Best for
  testing, or when the toolbox is shared across agents.
- **Way B — toolbox in an agent project** (`azure.yaml` + `azd deploy`): declares the toolbox next to
  your agent and ships them together. Best when the toolbox belongs to one agent project.

#### 1. Create the connection (both ways)

Store the key in a `custom-keys` connection. `ghmcppat` is the connection name the toolbox references.

```bash
azd ai connection create ghmcppat \
  --kind remote-tool \
  --target https://api.githubcopilot.com/mcp \
  --auth-type custom-keys \
  --custom-key "Authorization=Bearer <github_pat>" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

> `<github_pat>` — a classic `ghp_...` or fine-grained `github_pat_...` token.

#### Way A — standalone toolbox (`toolbox.yaml`)

1. Write `toolbox.yaml` referencing the connection by name:

   ```yaml
   # toolbox.yaml
   description: github-mcp toolbox
   tools:
     - type: mcp
       server_label: github
       project_connection_id: ghmcppat
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
           project_connection_id: ghmcppat
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
