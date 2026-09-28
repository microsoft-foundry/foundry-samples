# What this sample demonstrates

This sample hosts the Microsoft Agent Framework **research harness** on Microsoft Foundry using the **Responses protocol** in C#. The agent plans a research task, executes it with web search and a local web-browsing tool, tracks its own todos until the plan is complete, and saves findings to file memory.

## How it works

Give the agent a research topic. It plans the work, then executes — searching the web, browsing pages, and checking off todos — re-invoking itself until every todo is done, and writes the final report to file memory so it survives compaction.

### Conversation, session, and file behavior

The Responses protocol owns conversation history, while the hosted session identifies the filesystem context. The `azd` CLI saves and reuses both automatically. Use `--new-conversation --new-session` to start over. The harness keeps its own working state for the current run but does not reload prior turns — the hosting layer replays those — so history stays consistent across turns.

When hosted, the agent's file memory lives under `$HOME` (`agent-files`). In Foundry, `$HOME`
belongs to the hosted session and persists across turns and idle periods, so stored reports are
durable for the life of the session. `FileMemoryProvider` stores provider-managed records with opaque
filenames, so use the agent to retrieve a named report rather than expecting that report name to
appear directly in `azd ai agent files list`. Deleting the session removes the filesystem. Local
runs use the app directory.

### Session isolation

Harness agents carry per-session state (todo, mode, memory), so the hosting layer requires a session isolation key from the platform-injected `x-agent-user-id` header. `LocalDevSessionIsolationKeyProvider` supplies a fallback user id so the agent runs locally (`dotnet run` / `azd ai agent run` / F5 Inspector) without that header. In hosted Foundry environments the platform header takes precedence.

## Prerequisites

What the **sample itself** needs, independent of how you run it. The tooling for each run path is listed under its option below.

1. An existing Foundry project with a deployed model that provides at least **60K tokens per
   minute (TPM)**, or create them during setup in Option 1. The plan-to-execute transition includes
   the plan history and harness tool schemas, so one execute request can exceed 40K input tokens.
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **Roles (RBAC):** `Azure AI User` on the Foundry project (for the identity running the sample).
4. **Network:** the `WebBrowsingTool` makes outbound HTTP requests to public sites during `execute` mode.

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
mkdir my-agent && cd my-agent
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/harness-research/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

This creates a Foundry project and deploys the model declared in `azure.yaml` with 60K TPM, and
writes `FOUNDRY_PROJECT_ENDPOINT` / `AZURE_AI_MODEL_DEPLOYMENT_NAME` into your `azd` environment.

### Run the agent locally

```bash
azd ai agent run
```

The agent host starts on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "Research the history of the transistor and summarize the key milestones with sources."
```

The agent plans the research (plan mode), then on approval executes each todo — issuing web-browsing tool calls — and returns a Markdown report.

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "Research the history of the transistor and summarize the key milestones with sources."
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then run `az login` in the VS Code integrated terminal.
4. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Plan / execute workflow

This sample runs in two harness modes:

- **Plan mode** (default) — the agent breaks the request into todo items and asks for approval before doing the work.
- **Execute mode** — after you approve, the agent switches modes and works autonomously. The `TodoCompletionLoopEvaluator` re-invokes the agent (up to `MaxIterations = 10` passes per turn) until every todo is complete, issuing `WebBrowsingTool` calls to gather and cite sources.

To drive it end to end, send an initial research request, then reply approving execution (e.g. "Yes, execute now").

## Customization

- **Model** — change `AZURE_AI_MODEL_DEPLOYMENT_NAME` (env / `azure.yaml`) to target a different Foundry deployment.
- **Web access** — the `WebBrowsingTool` is constructed with `AllowPublicNetworks = true`; restrict or replace it in `Program.cs` to control outbound access.

## Troubleshooting

- **`500` / session isolation error locally** — ensure `LocalDevSessionIsolationKeyProvider` is registered (it is, in `Program.cs`); it supplies the fallback user id when the platform `x-agent-user-id` header is absent.
- **Rate limit (`429`)** — confirm the deployment provides at least 60K TPM. The first execute-mode
  request can exceed 40K input tokens before later loop iterations begin, so a 10K TPM deployment
  cannot run the documented flow; retry backoff and lower output-token limits do not reduce that
  input-token floor.
- **The friendly `azd` output does not show source URLs** — ask the agent to list the source URLs in
  a follow-up turn. Citation annotations and separate workflow messages are not always rendered by
  the friendly CLI output.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- See `../02-harness-data-processing` for a harness agent that reads and writes data files with tool approval.
