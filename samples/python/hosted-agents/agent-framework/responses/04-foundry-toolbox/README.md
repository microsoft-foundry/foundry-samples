# Agent with Foundry Toolbox (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery, hosted on Microsoft Foundry using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Foundry Toolbox configuration
The [`azure.yaml`](azure.yaml) declares the `agent-tools` toolbox and its authenticated connections as separate services. `azd deploy --all` deploys them before the agent and passes the versioned MCP endpoint to `TOOLBOX_ENDPOINT`.

To use your own tools, choose the tool type and authentication mode from the table below, then follow the linked guide to configure that tool in your toolbox.

### Toolbox tool types

| Type | Variant | Description | Guide |
|------|---------|-------------|-------|
| **Built-in** | Web search, code interpreter, ... | Ready-to-use tools hosted by Foundry with no external MCP server to connect. | [Built-in tools guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/built-in-tools.md) |
| **MCP** | Unauthenticated | Anonymous — you provide nothing. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-unauthenticated.md) |
| **MCP** | Key-based | A shared static key you provide as a header (e.g. `Authorization: Bearer <token>`). | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-key-auth.md) |
| **MCP** | Microsoft Entra<br>(Agent Identity / Project Managed Identity) | • Accesses MCP as the **agent/project** itself.<br>• Need grant the agent/project's identity access on the MCP.<br>• No user sign-in or consent. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md) |
| **MCP** | OAuth Identity Passthrough | • Accesses MCP as the signed-in **user**.<br>• Need register the OAuth app.<br>• User consents on first use. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-custom.md) |
| **MCP - Foundry Catalog** | OAuth Identity Passthrough<br>(Managed) | • Accesses MCP as the signed-in **user**.<br>• No OAuth app to set up — Foundry uses its own.<br>• User consents on first use.<br>• Only some catalog MCP support it. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-managed.md) |
| **MCP - Foundry Catalog** | OAuth Identity Passthrough<br>(User Entra Token) | • Accesses MCP as the signed-in **user**.<br>• No OAuth app to set up — Foundry uses its own.<br>• No user consent needed.<br>• Only some catalog MCP support it. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-user-entra-token.md) |
| **OpenAPI** | External REST API | Any REST API with an OpenAPI 3.x spec. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/openapi.md) |
| **A2A** | Remote agent (Agent-to-Agent) | Call another remote agent. | [Setup guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/a2a.md) |


## How it works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via `FoundryToolbox` — a thin convenience wrapper over `MCPStreamableHTTPTool` that authenticates every request with the credential and forwards the platform per-request call-id — which discovers and invokes the toolbox's tools over MCP at runtime. `FoundryToolbox` resolves the endpoint from the `TOOLBOX_ENDPOINT` environment variable. If that variable isn't set, it builds the endpoint from `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_NAME`.

See [main.py](src/agent-framework-agent-with-foundry-toolbox-responses/main.py) for the full implementation.

## Running the agent

### Option 1: Azure Developer CLI (`azd`)

#### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.32.0 or later)
2. Install the unified Foundry CLI extension bundle (provides `azd ai agent`, `connection`, `inspector`, `project`, `routine`, `skill`, and `toolbox`):
   ```bash
   # If you previously installed individual extensions, uninstall them first:
   #   azd ext uninstall azure.ai.agents
   #   azd ext uninstall azure.ai.toolboxes
   azd ext install microsoft.foundry
   ```
3. Authenticate:
   ```bash
   azd auth login
   ```

The sample manifest declares three authenticated connections: `ghmcppat` (GitHub MCP, PAT), `langmcpconn` (Azure Language MCP, project managed identity), and `foundrymcpconn` (Foundry MCP, user Entra token). **Have the following two values ready** before running `azd ai agent init` as initialization prompts for them.

| Prompt | How to obtain the value |
|--------|-------------------------|
| `GITHUB_MCP_PAT` | [Create a GitHub personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens). Prefer a fine-grained token limited to the repositories and permissions needed by the GitHub tools you intend to call (for example, read-only **Contents** access for reading repository files). Follow any organization approval or SSO requirements. See the [GitHub remote MCP server guide](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md) for authentication details. Enter only the token, **without** the `Bearer ` prefix; the manifest adds it. |
| `AZURE_LANGUAGE_MCP_ENDPOINT` | Use an Azure **Language service** resource, not **Language Understanding** (LUIS). Follow the portal steps below to create the resource and obtain its full MCP URL. Enter the full MCP URL, not just the resource endpoint or an API key. |

To create the Language resource and get its MCP URL:

1. In the [Azure portal](https://portal.azure.com/), select **Create a resource**, search for **Language service**, and select the Microsoft offering. Alternatively, [open the Language resource creation page directly](https://portal.azure.com/#create/Microsoft.CognitiveServicesTextAnalytics), as linked in the [official resource creation instructions](https://learn.microsoft.com/en-us/azure/ai-services/language-service/language-detection/quickstart#create-an-azure-resource).
2. If the **Select additional features** page appears, select **Continue to create your resource**. Choose your subscription, resource group, region, resource name, and pricing tier; accept the required terms, then select **Review + create** > **Create**.
3. After deployment, select **Go to resource** > **Keys and Endpoint** and copy the custom-subdomain endpoint, such as `https://<language-service>.cognitiveservices.azure.com/`.
4. Append `language/mcp?api-version=2025-11-15-preview` to that endpoint. The value to enter for `AZURE_LANGUAGE_MCP_ENDPOINT` is:

   ```text
   https://<language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview
   ```

This sample does **not** provision the external Azure Language resource or create a GitHub PAT. Keep the PAT out of source control and do not share it in logs or screenshots.

This sample calls Azure Language using the Foundry **project's system-assigned managed identity**, not your signed-in user account. After provisioning, you must grant that identity the **Cognitive Services Language Owner** role on the **Language service resource** to invoke the Language MCP endpoint. You need permission to create Azure role assignments at that resource's scope (for example, **Role Based Access Control Administrator**, **User Access Administrator**, or **Owner**), or help from an administrator. Follow [Authorize the project managed identity](#authorize-the-project-managed-identity) below before invoking the agent.

The separate Foundry MCP connection needs no additional secret; it uses the calling user's Entra token and requires that user to have access to the target Foundry resources.

#### Initialize the agent project

No cloning required. Create a new empty folder and initialize from the manifest. Initialization reports the output directory containing `azure.yaml` and the downloaded sample files; use that directory for the subsequent commands:

```bash
mkdir my-toolbox-agent && cd my-toolbox-agent

azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment, and enter the PAT and Language MCP URL prepared above when prompted. If you don't have an existing Foundry project, `azd ai agent init` will guide you through configuring a new one; `azd provision` creates its Azure resources.

**Run every subsequent command from the initialized project directory containing `azure.yaml`.** If initialization reports a different output directory, change to that directory first. Selecting an active Foundry project for `azd ai` commands is not a substitute for being in the local azd project directory.

#### Optional: correct the values entered during initialization

If you supplied the correct values during initialization, **skip this step**. You do not need to enter them again. To replace a placeholder, correct a URL, or rotate a token, run these commands from the initialized project directory:

```bash
azd env set GITHUB_MCP_PAT "<your-GitHub-MCP-PAT>"
azd env set AZURE_LANGUAGE_MCP_ENDPOINT "https://<language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview"
```

If these commands report `ERROR: no project exists`, see [Local azd project not found](#local-azd-project-not-found). Do not run `azd env set` before initialization or from the agent's source subdirectory.

For other tool types, consult the [tool type guides](#toolbox-tool-types) and edit the connection and toolbox services in `azure.yaml`. Changing `ghmcppat` from PAT to OAuth requires updating its auth configuration.

#### Provision the Foundry resources

Provision before deploying so that the project's managed identity exists and can be authorized:

```bash
azd provision
```

#### Authorize the project managed identity

The `langmcpconn` connection uses `ProjectManagedIdentity` authentication. Grant the **Foundry project's identity** access to the **Language service resource**, as follows.

**1. Identify the project's managed identity**

After `azd provision` completes:

1. In the [Azure portal](https://portal.azure.com/), open your **Foundry project** resource, not the parent Foundry account.
2. In the project's menu, select **Resource Management** > **Identity**.
3. On the **System assigned** tab, copy the **Object (principal) ID**.

This GUID identifies the project's managed identity. It is not the project's Azure resource ID or an application (client) ID. Do not substitute your user ID, the parent Foundry account's identity, or an agent-specific identity.

**2. Assign the role on the Language resource**

1. Open the **Language service resource** whose endpoint you supplied as `AZURE_LANGUAGE_MCP_ENDPOINT`.
2. Select **Access control (IAM)** > **Add** > **Add role assignment**.
3. Search for and select **Cognitive Services Language Owner**, then select **Next**.
4. Under **Members**, choose **User, group, or service principal**, select **Select members**, and search using the **Object (principal) ID** copied above. Select the matching identity.
5. Select **Review + assign** to complete the assignment.

The assignment's **scope must be the Language service resource**, not the Foundry project. This grants Language API access without granting subscription-wide access. If **Add role assignment** is disabled or the assignment fails because you lack permission, ask an administrator to perform this step.

For more background on the required Language data actions, see the [managed-identity authorization guide](../../../SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md#step-2--authorize-the-identity).

#### Deploy and invoke the agent

Deploy all services together so that the connections and toolbox are deployed before the agent:

```bash
azd deploy --all
azd ai agent invoke "What tools do you have?"
```

If invocation fails with `language-mcp`, `HTTP_401`, and a message that a principal lacks `Microsoft.CognitiveServices/accounts/Language/mcp/action`, compare the principal ID in the error with the project's **Object (principal) ID** and verify the role was assigned on the correct Language resource. A failure from `language-mcp` can prevent discovery of **all** toolbox tools, even when the other sources succeed.

The agent's `TOOLBOX_ENDPOINT` maps to `TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT` produced by this toolbox deployment. After editing tools, connections, or agent code, run `azd deploy --all` again; the agent uses the new toolbox version without publishing it as the default or switching older agents.

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

#### Optional: run the agent locally

Complete provisioning, authorization, and deployment above first: `azd ai agent run` starts the host locally but does not create the remote connections or toolbox.

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

#### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "What tools do you have?"
```

### Option 2: VS Code (Foundry Toolkit)

#### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Python 3.13 or later** and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment.

#### Set up the Python virtual environment

- Create and synchronize the locked environment:

  ```bash
   uv sync --frozen
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

#### Prepare remote dependencies

Complete the external-dependency preparation, initialization, provisioning, managed-identity authorization, and deployment in [Option 1](#option-1-azure-developer-cli-azd) first. For F5 or standalone Python, set `TOOLBOX_ENDPOINT` in `.env` to the versioned endpoint available via `azd env get-value TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT` from the initialized project directory. The VS Code deploy wizard deploys the agent only; use `azd deploy --all` when changing the toolbox or its connections.

#### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

#### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

#### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.


## Use GitHub Copilot for Azure

If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, the following skill references describe the same endpoint contract (env var, headers, MCP protocol, citation patterns, and troubleshooting) that the agent must implement:

- [Foundry Toolbox — Concept, API Shape & Schema](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/toolbox/toolbox.md) — toolbox creation and lifecycle, supported tool and authentication types, composition rules, versioning, MCP endpoint formats, testing, and troubleshooting.
- [Use a Toolbox from Your Agent Code](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md) — framework-specific integration paths, `TOOLBOX_ENDPOINT`, local and deployed validation, BYO MCP authentication, OAuth consent, approvals, citations, and troubleshooting.


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

> For connector-backed MCP servers (for example Microsoft 365 / WorkIQ servers such as Outlook Mail), the audience is instead published in the Foundry Tools Catalog. Look it up with the helper scripts in [`scripts/`](src/agent-framework-agent-with-foundry-toolbox-responses/scripts/): run `./scripts/list-foundry-connectors.ps1 -ConnectorName <name>` (or `./scripts/list-foundry-connectors.sh -n <name>`) and read `AzureActiveDirectoryResourceId` (equivalently `resourceUri`) under `properties.x-ms-connection-parameters`. Run the script with no connector name to list every connector with its name, title, and auth type.

## Troubleshooting

### Local azd project not found

`azd env set` and the core `azd provision` / `azd deploy` commands require a local project containing `azure.yaml`. If you see `ERROR: no project exists; to create a new project, run azd init` after `azd ai agent init`:

1. Check the initialization output for the generated project directory.
2. Change to that directory and verify that it contains `azure.yaml`, rather than running from its parent or a source subdirectory. Alternatively, use `azd --cwd "<initialized-project-directory>" env set ...`.
3. If you have multiple azd environments, select the one created during initialization with `azd env select`.
4. Retry the command. If the values entered during initialization were already correct, skip `azd env set` and continue with `azd provision`.

Do not run a second, unrelated `azd init` just to clear the error. If no `azure.yaml` was generated, initialization did not produce the local project required by this workflow; check the CLI/extension prerequisites and the initialization output before retrying in a new empty directory.

### A single failing MCP source can fail the whole agent

A toolbox aggregates every tool source behind one MCP endpoint. If **any** referenced MCP server fails while the toolbox enumerates tools (`tools/list`), the toolbox fails the entire enumeration, so the agent can't load its tools and every request returns an error (HTTP 500) until that source recovers.

For example, a flaky third-party MCP source can intermittently return `HTTP 502 (Bad Gateway)` during enumeration, which surfaces as:

```
tools/list failed for 1 tool source(s), succeeded for 5 tool source(s)
{"errors":[{"name":"<server_label>","type":"mcp","error":{"code":"HTTP_502", ...}}]}
```

This is an upstream/service hiccup, not a problem with the agent code. Mitigations:

- Retry the request — these failures are usually transient.
- If a source is persistently unavailable, temporarily remove its tool entry (and connection service, if any) from `azure.yaml`, then run `azd deploy --all` to update the toolbox and agent together.
- Inspect deployed agent logs with `azd ai agent monitor` to identify which source failed.

### Entra pass-through forwards the caller's identity

The Foundry MCP tool authenticates with **Entra pass-through** (`foundrymcpconn`): Foundry forwards the
calling user's Entra token to `https://mcp.ai.azure.com`. The token is forwarded both from the Foundry
portal **Agent Playground** (signed-in user) and by `azd ai agent invoke` (the developer's Entra token),
so the tools operate as that user and only act on resources the user can already access. The Foundry MCP
server requires no extra license — just access to the Foundry project.

Because the tool acts as a specific user, running the agent **locally** (`uv run --no-sync python main.py`) or calling the
endpoint with a raw token uses whatever identity that token represents (`az login` user locally, the
agent's managed identity when hosted). If that identity has no access to the target resources, the tool
returns an authorization error even though it is discovered and called correctly.

> Some other Entra pass-through MCP servers add their **own** entitlement checks on top of the token. For
> example, the Microsoft 365 / WorkIQ servers (Outlook Mail, Teams) require the caller to hold a
> **Microsoft 365 Copilot (Business Chat)** license; without it they fail with
> `WorkIQ license check failed. Required service plan(s): [M365_COPILOT_BUSINESS_CHAT]`. That is a
> property of those servers, not of Entra pass-through itself.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Tool catalog](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/tool-catalog) — browse available tools to extend your agent (Bing Search, Azure AI Search, file search, code interpreter, and more)
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
- [Basic agent](../01-basic/) — minimal agent with no tools
- [Add local tools](../02-tools/) — sample with locally-defined Python tool functions
- [Build multi-agent workflows](../05-workflows/) — sample with chained agent pipelines
