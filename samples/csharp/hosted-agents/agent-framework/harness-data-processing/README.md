# What this sample demonstrates

This sample hosts the Microsoft Agent Framework **data-processing harness** on Microsoft Foundry using the **Responses protocol** in C#. The agent reads and analyzes a bundled CSV through file tools while surfacing structured approval requests before any write or delete.

## How it works

Ask the agent to analyze the bundled `working/sales.csv`; read-only questions run immediately. Requests to create, change, or delete files pause for your approval, and approved files are written back to the working folder.

### Conversation, session, and file behavior

The Responses protocol owns conversation history, while the hosted session identifies the filesystem context. The `azd` CLI saves and reuses both automatically. Use `--new-conversation --new-session` to start over. The harness keeps its own working state for the current run but does not reload prior turns — the hosting layer replays those — so history stays consistent across turns.

The bundled `working/` directory is read-only seed data. When hosted, the sample copies it into `$HOME/working` only when a file is missing, so existing files are never overwritten. In Foundry, `$HOME` belongs to the hosted session and persists across turns and idle periods, so files the agent writes are durable for the life of the session and are visible through the Session Files API; deleting the session removes that filesystem. Local runs read and write the sample's `working/` folder directly.

### Session isolation

Harness agents carry per-session state, so the hosting layer requires a session isolation key from the platform-injected `x-agent-user-id` header. `LocalDevSessionIsolationKeyProvider` supplies a fallback user id so the agent runs locally (`dotnet run` / `azd ai agent run` / F5 Inspector) without that header. In hosted Foundry environments the platform header takes precedence.

## Prerequisites

What the **sample itself** needs, independent of how you run it. The tooling for each run path is listed under its option below.

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **Roles (RBAC):** `Azure AI User` on the Foundry project (for the identity running the sample).

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
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/harness-data-processing/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

This creates a Foundry project and deploys the model declared in `azure.yaml`, and writes `FOUNDRY_PROJECT_ENDPOINT` / `AZURE_AI_MODEL_DEPLOYMENT_NAME` into your `azd` environment.

### Run the agent locally

```bash
azd ai agent run
```

The agent host starts on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "List the available data files, read them, and give me a one-paragraph summary."
```

Reads are auto-approved. To see the approval flow, follow up with a write request (e.g. "Now write a summary.md with that summary") — the agent surfaces an approval request that you approve before the file is written.

> [!IMPORTANT]
> `azd ai agent invoke -f` currently treats a file as text inside the Responses `input` field; it
> does not send a complete structured Responses body. Use `az rest` for the
> `mcp_approval_response`.

Keep the same conversation ID for the request and its approval:

```bash
# Request a write. The response contains an mcp_approval_request; note its id.
azd ai agent invoke --local --conversation-id data-write-demo-1 \
  "Read sales.csv, summarize it in one paragraph, and write the result to summary.md."
```

Save the following as `approve-data-write.json`, replacing `<id>` with the returned approval request ID:

```json
{
  "conversation": { "id": "data-write-demo-1" },
  "input": [
    {
      "type": "mcp_approval_response",
      "approval_request_id": "<id>",
      "approve": true
    }
  ]
}
```

```bash
az rest --method POST \
  --url http://localhost:8088/responses \
  --headers "Content-Type=application/json" \
  --body @approve-data-write.json
```

The approval response resumes the paused turn, writes `summary.md` once, and returns the completed
tool result.

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "List the available data files, read them, and give me a one-paragraph summary."
```

For a protected write on the deployed agent:

1. Start a new conversation with `azd ai agent invoke --new-conversation "<write request>"`.
2. Copy the service-issued `Session:` and `Conversation:` values. Put the conversation value and the
   emitted `mcp_approval_request.id` into `approve-data-write.json`.
3. Send the structured response to the deployed Responses endpoint shown by
   `azd ai agent show --output json`:

```bash
az rest --method POST \
  --url "<responses-endpoint>" \
  --resource https://ai.azure.com \
  --headers "Content-Type=application/json" "x-agent-session-id=<agent-session-id>" \
  --body @approve-data-write.json
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

## Tool approval

File access is gated by tool approval:

- **Reads** (`file_access_ls`, `file_access_read`) are auto-approved by `FileAccessProvider.ReadOnlyToolsAutoApprovalRule` and run without prompting.
- **Writes / deletes** (`file_access_write`, ...) surface an approval request. Resume them with a
  structured `mcp_approval_response` in the same conversation.

## Customization

- **Data** — replace or add files under `src/harness-data-processing/working/` to analyze your own datasets.
- **Model** — change `AZURE_AI_MODEL_DEPLOYMENT_NAME` (env / `azure.yaml`) to target a different Foundry deployment.
- **Approval policy** — adjust the auto-approval rules in `Program.cs` (e.g. auto-approve writes too, or require approval for everything).

## Troubleshooting

- **`500` / session isolation error locally** — ensure `LocalDevSessionIsolationKeyProvider` is registered (it is, in `Program.cs`); it supplies the fallback user id when the platform `x-agent-user-id` header is absent.
- **Write never happens** — writes require approval; make sure you send an approval response to the `mcp_approval_request` the agent returns.
- **Approval fails with `No tool output found for function call` after `azd ... -f`** — the file was
  sent as user text rather than as a structured Responses body. Use the REST commands above.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- See `../01-harness-research` for a harness agent that plans and executes web research with a loop evaluator.
