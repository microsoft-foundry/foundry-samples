# Foundry Toolbox — Auth Paths

A Foundry Toolbox that demonstrates the **authentication paths** a toolbox MCP tool can use to reach its upstream server. Like [`foundry-toolbox-server-side`](../foundry-toolbox-server-side/), the agent registers the toolbox with `AddFoundryToolboxes()`; the hosting layer discovers its tools and injects them as **server-side tools** — Foundry executes them on the agent's behalf.

The key idea: **the agent code carries no auth logic**. Foundry resolves each tool's credential server-side when it proxies the MCP call, so `Program.cs` is identical regardless of which path a tool uses. The difference lives entirely in [`azure.yaml`](azure.yaml).

## Auth path matrix

| # | Path | `authType` | Where the secret lives | Wired by default? |
|---|------|-----------|------------------------|-------------------|
| 1 | Key-based | `CustomKeys` | `gh_pat` secret parameter → Foundry connection secret store, injected as `Authorization: Bearer …` | ✅ Yes (GitHub MCP) |
| 2 | Microsoft Entra agent identity | `AgenticIdentity` | No secret — the agent's managed identity gets an Entra token for the target `audience` | ➕ Optional (see below) |

> A third variant — embedding an `Authorization` header **inline** in the manifest — is an anti-pattern: the token is committed in plain text. Always prefer a `CustomKeys` connection (path 1) so the secret stays in the Foundry connection store.

## How auth is exercised

There is nothing auth-specific to run. Each prompt drives a GitHub tool, which drives the key-based path end to end:

- A GitHub answer means the **CustomKeys** PAT (path 1) resolved correctly.

A `401`/`403` from a tool means that path's credential did not resolve. Send any prompt that triggers a GitHub tool (e.g. *"What tools do you have available?"*) to exercise the path.

## All-or-nothing enumeration

`AddFoundryToolboxes()` makes the hosting layer fetch **all** tool definitions at startup. If any configured source is misconfigured (bad PAT, missing RBAC, unreachable server), the fetch fails and the host does not start. When adding a new auth path, **validate one source at a time** — comment out the others in the manifest until each one enumerates cleanly.

## Adding auth path 2 — Microsoft Entra agent identity

Path 2 is documented rather than wired by default because it needs a post-deploy RBAC grant before the toolbox can enumerate it. To add it:

1. Add a parameter and an `AgenticIdentity` connection, and reference it from a third toolbox tool, in [`azure.yaml`](azure.yaml):

   ```yaml
   parameters:
     properties:
       - name: entra_audience
         secret: false
         description: Entra ID token audience for the target MCP server (e.g. https://cognitiveservices.azure.com).
       - name: entra_mcp_target
         secret: false
         description: URL of the Entra-protected MCP server that accepts agent-identity tokens.
   resources:
     - kind: connection
       name: entra-agent-conn
       category: RemoteTool
       authType: AgenticIdentity
       audience: "{{ entra_audience }}"
       target: "{{ entra_mcp_target }}"
     - kind: toolbox
       name: auth-paths-tools
       tools:
         # … existing github entry …
         - type: mcp
           server_label: entra
           project_connection_id: entra-agent-conn
   ```

2. **Grant RBAC on the target before the first invoke.** After deploy, the agent gets a managed identity (its principal id changes each time the agent is recreated). Assign that identity the role the target MCP server requires (for an Azure Cognitive Services target: **Cognitive Services User** at the resource scope). Until this lands, the path-2 source fails to enumerate and bricks the whole toolbox.

## Provisioning the toolbox in your environment

The agent reads its toolbox from your Foundry project at startup, so the `auth-paths-tools` toolbox (and the `github-mcp-conn` connection that backs the key-based path) must exist in the project before you run. You have two ways to create them.

### Provision with `azd` (recommended)

`azd provision` reads [`azure.yaml`](azure.yaml) and creates the connection and toolbox for you:

```bash
azd ai agent init          # prompts once for the gh_pat secret parameter
azd provision              # creates github-mcp-conn (CustomKeys) + auth-paths-tools toolbox
```

The `gh_pat` value is stored only in the Foundry connection secret store. It is never written to disk or passed to the container as an env var. Use a GitHub PAT (classic `ghp_...` or fine-grained `github_pat_...`) scoped to read the repositories your prompts ask about. Public-repo read is enough for the sample prompts.

### Create the toolbox yourself

Create the same two resources in the [Foundry portal](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox) or in code with the [Foundry Toolbox CRUD sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/hosted_agents/sample_toolboxes_crud.py):

1. A `CustomKeys` connection named `github-mcp-conn`, target `https://api.githubcopilot.com/mcp`, key `Authorization` = `Bearer <your-pat>`.
2. A toolbox named `auth-paths-tools` with one MCP tool: `github` (referencing `github-mcp-conn`).

Once the toolbox exists, set `TOOLBOX_NAME=auth-paths-tools` (already the manifest default) and run the agent.

## Continuous integration

The `hosted-agents-cloud-e2e` workflow treats this as a **toolbox sample** (its directory name contains `toolbox`) and runs with `SKIP_PROVISION=true`, so it does **not** run `azd provision` and never receives a PAT. Instead it consumes a toolbox that already exists in a shared Foundry project, the same way [`langgraph-toolbox`](../../../python/hosted-agents/bring-your-own/responses/langgraph-toolbox/) does. To enable it there, register an `auth-paths-tools` toolbox in that project (see [Create the toolbox yourself](#create-the-toolbox-yourself), above) and add one `label=url|query` line to the `TOOLBOX_ENDPOINT` repository variable:

```
auth-paths=https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/auth-paths-tools/mcp?api-version=v1|<query that exercises the github tool>
```

The workflow derives `TOOLBOX_NAME` from the URL slug (`.../toolboxes/auth-paths-tools/mcp`) and drives the toolbox with that query. Until the toolbox is registered, add `samples/csharp/hosted-agents/agent-framework/toolbox-auth-paths` to `.azure-pipelines/scripts/hosted-agent-samples-ci-skiplist` at the repository root to keep the sample out of the gated set.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir toolbox-auth-paths-agent && cd toolbox-auth-paths-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/toolbox-auth-paths/azure.yaml
```

`azd ai agent init` prompts once for the `gh_pat` secret parameter. Follow the prompts to configure your Foundry project and model deployment.

### Provision Azure resources (if needed)

The agent reads its toolbox from your Foundry project at startup, so the `auth-paths-tools` toolbox and `github-mcp-conn` connection must exist first — see [Provisioning the toolbox in your environment](#provisioning-the-toolbox-in-your-environment). With the manifest, `azd provision` creates them (along with a Foundry project and model deployment if you don't have one):

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, send a prompt:

```bash
azd ai agent invoke --local "What tools do you have available?"
azd ai agent invoke --local "Search the microsoft/agent-framework repo for open issues that mention hosted agents."
```

A GitHub answer means the key-based **CustomKeys** path (path 1) resolved its PAT correctly. A `401`/`403` means the connection credential did not resolve.

Or use curl directly against `http://localhost:8088/responses`:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What tools do you have available?", "stream": false}'
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "What tools do you have available?"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

The `auth-paths-tools` toolbox must already exist (see [Provisioning the toolbox in your environment](#provisioning-the-toolbox-in-your-environment)). Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   dotnet restore
   ```

2. Configure the agent: copy `.env.example` to `.env` and fill in the required variables (including `TOOLBOX_NAME=auth-paths-tools`). The sample loads `.env` automatically on startup.

3. Sign in to Azure with the Azure CLI so `DefaultAzureCredential` can authenticate the terminal process (the **F5** path reuses the Azure sign-in from the Foundry Toolkit, so it doesn't need a separate `az login`):

   ```bash
   az login
   ```

4. Start the agent (listens on `http://localhost:8088`):

   ```bash
   dotnet run
   ```

5. Open the Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.
