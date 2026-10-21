# Built-in Tools

Foundry provides a set of **built-in** tools you add to a toolbox from the **Configured** tab — no
custom endpoint to register. Some are fully connectionless; others reference an existing resource
(a vector store, an Azure AI Search index, a Bing Custom Search instance, or a Playwright workspace).

| Tool | Description |
|------|-------------|
| [**Web search** (basic Bing)](#web-search-basic-bing) | Public web results via Grounding with Bing Search. |
| [**Bing Custom Search**](#bing-custom-search) | Web search scoped to specific domains. |
| [**Code interpreter**](#code-interpreter) | Runs sandboxed Python; optionally attach files. |
| [**File search**](#file-search) | Retrieval over uploaded files. |
| [**Azure AI Search**](#azure-ai-search) | Query an existing AI Search index. |
| [**Browser automation**](#browser-automation) | Drive a real browser (navigate, click, extract). |

> This page covers only the **built-in tool** parts — the Configured-tab selection and any
> resource/connection each tool needs. For the shared toolbox flow (create → publish → copy the
> endpoint), see the [README](../README.md#create-the-toolbox).

## Create the tool connection & toolbox

### Foundry Toolkit in VS Code

1. Follow the README's [Create the toolbox](../README.md#create-the-toolbox) steps to open the **Select a tool** dialog.
2. Stay on the **Configured** tab and select the tool, then follow the config dialog — it prompts for any resource or connection the tool needs (and lets you create one inline). Click **Add tool**.

### `azd` CLI

Each tool is one entry under `tools:`. When a tool has a **Create the toolbox** step, it offers two ways:

- **Way A — standalone toolbox** (`toolbox.yaml` + `azd ai toolbox create`): builds the toolbox on its
  own. Best for testing, or when the toolbox is shared across agents.
- **Way B — toolbox in an agent project** (`azure.yaml` + `azd deploy`): declares the toolbox next to
  your agent and ships them together. Best when the toolbox belongs to one agent project.

Combine multiple tools by listing several entries under `tools:`.

#### Web search (basic Bing)

Connectionless — no prerequisite or connection. To **scope** search to specific domains, use
[Bing Custom Search](#bing-custom-search) instead.

**1. Create the toolbox**

**Way A — standalone toolbox (`toolbox.yaml`)**

i. Write `toolbox.yaml`:

   ```yaml
   # toolbox.yaml
   description: web-search toolbox
   tools:
     - type: web_search
       name: web_search
       require_approval: "never"
   ```

ii. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

iii. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`.

**Way B — toolbox in an agent project (`azure.yaml`)**

i. Declare the toolbox and agent together in `azure.yaml`:

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
         - type: web_search
           name: web_search
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

ii. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```

Docs: [Web Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search) ·
[Web Search vs Grounding with Bing Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview)

#### Bing Custom Search

Like web search but **scoped to specific domains** via a Bing Custom Search instance.

**1. Prerequisite — create the resource and a published configuration:**

   i. Create a **Grounding with Bing Custom Search** resource (kind `Bing.GroundingCustomSearch`) in
      the Azure portal, and note its **resource ID** and **key**.

   ii. In the Azure Portal, **Create new configuration** in Bing Custom Search resource,
       add your allowed domains, and **Publish** it. Note the **Configuration Name** — this is the
       `instance_name` the toolbox tool references (a tool call fails with `Instance or Customer not
       found` until a published configuration exists and its name matches).

**2. Create the connection.** Use `--kind custom-keys`; the Bing key is sent as the
`Ocp-Apim-Subscription-Key` header, and the `ResourceId` + `type` metadata mark it as a Bing Custom
Search connection:

```bash
azd ai connection create bingcustomconn \
  --kind custom-keys \
  --target https://api.bing.microsoft.com/ \
  --auth-type api-key \
  --key "<bing_api_key>" \
  --metadata "ResourceId=<bing_resource_id>" \
  --metadata "type=bing_custom_search_preview" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

**3. Create the toolbox**

**Way A — standalone toolbox (`toolbox.yaml`)**

i. Write `toolbox.yaml` referencing the connection by name:

   ```yaml
   # toolbox.yaml
   description: bing-custom-search toolbox
   tools:
     - type: web_search
       name: web_search
       custom_search_configuration:
         instance_name: "<config-name>"          # the published Bing Custom Search Configuration Name
         project_connection_id: bingcustomconn
       require_approval: "never"
   ```

ii. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

iii. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`.

**Way B — toolbox in an agent project (`azure.yaml`)**

i. Declare the toolbox and agent together in `azure.yaml`:

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
         - type: web_search
           name: web_search
           custom_search_configuration:
             instance_name: "<config-name>"          # the published Bing Custom Search Configuration Name
             project_connection_id: bingcustomconn
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

ii. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```

Docs: [Grounding with Bing Custom Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview)

#### Code interpreter

Connectionless — no prerequisite or connection. In the portal's **Upload files** dialog you can
optionally attach files for it to process.

**1. Create the toolbox**

**Way A — standalone toolbox (`toolbox.yaml`)**

i. Write `toolbox.yaml`:

   ```yaml
   # toolbox.yaml
   description: code-interpreter toolbox
   tools:
     - type: code_interpreter
       name: code_interpreter
       require_approval: "never"
   ```

ii. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

iii. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`.

**Way B — toolbox in an agent project (`azure.yaml`)**

i. Declare the toolbox and agent together in `azure.yaml`:

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
         - type: code_interpreter
           name: code_interpreter
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

ii. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```

Docs: [Code Interpreter](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/code-interpreter)

#### File search

**1. Prerequisite.** Needs an existing **vector store** (e.g. `vs_xxxxxxxxxxxx`) in the **same
project**, with at least one indexed file
([create one](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/file-search#upload-files-and-add-them-to-a-vector-store)) —
in the portal, via **Data → Vector stores**. Connectionless — no connection to create.

**2. Create the toolbox**

**Way A — standalone toolbox (`toolbox.yaml`)**

i. Write `toolbox.yaml` with your vector store ID:

   ```yaml
   # toolbox.yaml
   description: file-search toolbox
   tools:
     - type: file_search
       name: file_search
       vector_store_ids:
         - "vs_xxxxxxxxxxxx"     # flat: sibling of type, NOT nested under file_search
       require_approval: "never"
   ```

ii. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

iii. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`.

**Way B — toolbox in an agent project (`azure.yaml`)**

i. Declare the toolbox and agent together in `azure.yaml`:

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
         - type: file_search
           name: file_search
           vector_store_ids:
             - "vs_xxxxxxxxxxxx"
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

ii. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```

- `vector_store_ids` is a **flat** sibling of `type` — do **not** nest it under a `file_search:` object.
- When calling the tool over MCP, the argument is `queries` (an **array** of strings), e.g.
  `{"queries": ["what is the refund policy?"]}`.

Docs: [File Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/file-search)

#### Azure AI Search

**1. Prerequisite.** Needs an existing **Azure AI Search service + index**
([create one](https://learn.microsoft.com/azure/search/search-create-service-portal)).

**2. Grant Search access to the Foundry project identity.** Keyless connections created with `azd`
use the project's system-assigned managed identity. Grant it the roles required by the Azure AI
Search tool:

```bash
SEARCH_RESOURCE_ID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Search/searchServices/<service>"
PROJECT_RESOURCE_ID="/subscriptions/<sub>/resourceGroups/<project-rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
PROJECT_PRINCIPAL_ID=$(az resource show \
  --ids "$PROJECT_RESOURCE_ID" \
  --api-version 2025-06-01 \
  --query identity.principalId \
  --output tsv)

az role assignment create \
  --assignee-object-id "$PROJECT_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Search Index Data Contributor" \
  --scope "$SEARCH_RESOURCE_ID"

az role assignment create \
  --assignee-object-id "$PROJECT_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Search Service Contributor" \
  --scope "$SEARCH_RESOURCE_ID"
```

**3. Create the connection** — a keyless `CognitiveSearch` connection that uses the project managed
identity:

```bash
azd ai connection create aisearchconn \
  --kind cognitive-search \
  --target "https://<service>.search.windows.net/" \
  --auth-type project-managed-identity \
  --audience "https://search.azure.com" \
  --metadata "displayName=<service>" \
  --metadata "ApiType=Azure" \
  --metadata "ResourceId=$SEARCH_RESOURCE_ID" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

> `azd ai connection create` does not accept `--auth-type aad`. The supported keyless CLI mode is
> `project-managed-identity`, which creates a `CognitiveSearch` connection with
> `ProjectManagedIdentity` credentials. This differs from the legacy REST request body that uses
> `authType: AAD`.

**4. Create the toolbox**

**Way A — standalone toolbox (`toolbox.yaml`)**

i. Write `toolbox.yaml` referencing the connection and index:

   ```yaml
   # toolbox.yaml
   description: ai-search toolbox
   tools:
     - type: azure_ai_search
       name: azure_ai_search
       azure_ai_search:
         indexes:
           - project_connection_id: aisearchconn
             index_name: "<your_index_name>"
             query_type: simple      # simple | semantic | vector | vector_simple_hybrid | vector_semantic_hybrid
             top_k: 5
       require_approval: "never"
   ```

ii. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

iii. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`.

**Way B — toolbox in an agent project (`azure.yaml`)**

i. Declare the toolbox and agent together in `azure.yaml`:

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
         - type: azure_ai_search
           name: azure_ai_search
           azure_ai_search:
             indexes:
               - project_connection_id: aisearchconn
                 index_name: "<your_index_name>"
                 query_type: simple
                 top_k: 5
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

ii. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```

- For multiple indexes, add more entries under `azure_ai_search.indexes:`.
- Index config is **mutually exclusive** per entry: use exactly one of `project_connection_id` +
  `index_name`, `index_connection_id` + `index_name`, or `index_asset_id` alone.

Docs: [Azure AI Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/azure-ai-search)

#### Browser automation

Drive a real browser via an **Azure Playwright workspace**
([create one](https://aka.ms/pww/docs/manage-workspaces)). Uses a `PlaywrightWorkspace` connection
with **project managed identity**. `browser_automation_preview` is a preview tool type.

**1. Prerequisite — gather the workspace's identifiers.** From the Playwright workspace resource, note
two values:

- **Resource ID** — the workspace's ARM resource ID
  (`/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.LoadTestService/playwrightWorkspaces/<name>`).
- **Browser (wss) endpoint** —
  `wss://<region>.api.playwright.microsoft.com/playwrightworkspaces/<workspaceId>/browsers`.

**2. Create the connection.** `--audience` is required so the tool can request a token for the target;
use the ARM audience `https://management.core.windows.net`:

```bash
azd ai connection create browserautomation \
  --kind playwright-workspace \
  --target "<browser-wss-endpoint>" \
  --auth-type project-managed-identity \
  --audience "https://management.core.windows.net" \
  --metadata "resourceId=<workspace-resource-id>" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

Then grant the project identity access to the workspace:

   i. **Get the project's managed-identity principal.** The connection authenticates as the Foundry
      **project's** system-assigned identity — note its **principal ID** from the project's
      `identity.principalId`.

   ii. **Grant that identity a role on the workspace.** Without it, the first `create_session` fails
       with **HTTP 403**. Grant **Playwright Workspace Contributor**:

      ```bash
      az role assignment create \
        --assignee "<project-mi-principal-id>" \
        --role "Playwright Workspace Contributor" \
        --scope "<workspace-resource-id>"
      ```

**3. Create the toolbox**

**Way A — standalone toolbox (`toolbox.yaml`)**

i. Write `toolbox.yaml` referencing the connection by name:

   ```yaml
   # toolbox.yaml
   description: browser-automation toolbox
   tools:
     - type: browser_automation_preview
       name: browser_automation
       browser_automation_preview:
         connection:
           project_connection_id: browserautomation
       require_approval: "never"
   ```

ii. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

iii. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`.

**Way B — toolbox in an agent project (`azure.yaml`)**

i. Declare the toolbox and agent together in `azure.yaml`:

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
         - type: browser_automation_preview
           name: browser_automation
           browser_automation_preview:
             connection:
               project_connection_id: browserautomation
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

ii. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```

Browser automation surfaces as MCP sub-tools under your `name` prefix, joined by three underscores
(e.g. `browser_automation___create_session`). A successful `create_session` returns a live CDP
endpoint (`wss://browser.playwright.microsoft.com/ws?...`) the agent drives.

**Troubleshooting**

| Symptom | Cause | Fix |
|---|---|---|
| `azd ai connection create` fails with `Error when parsing request; unable to deserialize request body` | The beta CLI may reject the `playwright-workspace` kind | Create the `PlaywrightWorkspace` connection from the **Foundry portal** or **VS Code Foundry Toolkit** instead — set auth to **project managed identity** and audience `https://management.core.windows.net`. The toolbox references it the same way. |
| `403` on `create_session` | The project managed identity lacks a role on the workspace | Grant it **Playwright Workspace Contributor** (see the role grant above). |
| Connection-resolution error about a missing audience | The connection's audience isn't set | Set `--audience "https://management.core.windows.net"` on the connection. |
