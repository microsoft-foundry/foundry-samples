# What this sample demonstrates

A **C# personal assistant** using the **GitHub Copilot SDK**, a Foundry-hosted
model, and the **Activity protocol**. This is the .NET counterpart of the
[Python GitHub Copilot sample](../../../../../python/hosted-agents/bring-your-own/activity/github-copilot).
It uses the actual [GitHub Copilot .NET SDK](https://github.com/github/copilot-sdk/tree/main/dotnet),
not a hand-written model/tool loop or an Agent Framework replacement.

## How it works

[Program.cs](src/github-copilot-dotnet-activity/Program.cs) runs a native
Microsoft 365 `AgentApplication` through `ActivityServer.Run<CopilotAgent>()`.
The Activity SDK handles the Foundry endpoint, session/correlation headers,
tracing, and channel authentication.

| File | Responsibility |
|------|----------------|
| [CopilotAgent.cs](src/github-copilot-dotnet-activity/CopilotAgent.cs) | Message/welcome/invoke routing, streamed replies, card and file delivery. |
| [CopilotAssistant.cs](src/github-copilot-dotnet-activity/CopilotAssistant.cs) | Copilot SDK sessions, Foundry provider/auth, model loop, and custom tools. |
| [TaskStore.cs](src/github-copilot-dotnet-activity/TaskStore.cs) | File-backed, conversation-scoped tasks under `$HOME`. |
| [TaskCards.cs](src/github-copilot-dotnet-activity/TaskCards.cs) | Adaptive Card task board with Add/Done/Delete/Refresh actions. |
| [FileTransfers.cs](src/github-copilot-dotnet-activity/FileTransfers.cs) | Shared-file/image loading and Teams File Consent uploads. |

### Features and channel boundaries

- Streaming text and tool-progress updates on streaming-capable channels;
  one accumulated reply on other channels.
- `add_task`, `list_tasks`, and `complete_task` tools. Tasks persist across
  process restarts when `$HOME` storage is retained. Task IDs and conversation
  session IDs are stable; turns for the same model session are serialized.
- Interactive task cards in Teams; plain-text task lists on other channels.
- Shared files are downloaded verbatim for the model's file tools. Bot
  Connector images become inline image attachments for a vision-capable model.
- The model creates files using Copilot's built-in tools, then calls
  `deliver_file`. Teams **personal chats** receive a File Consent card; other
  channels receive a plain explanation that downloads require personal Teams.

Each turn resumes the same Copilot session with a fresh Azure token. The
Copilot client starts and stops with the application host. No GitHub PAT or
Copilot subscription is needed for this **bring-your-own Foundry model** path.

The Activity package is pinned to `1.0.0-alpha.20261102.1` on the **public
Azure SDK development feed** in [NuGet.Config](src/github-copilot-dotnet-activity/NuGet.Config).
It is not a GA release. `GitHub.Copilot.SDK` 1.0.28 downloads and verifies
its matching CLI runtime during build, including the Linux runtime on publish.
No local NuGet binaries or SDK checkout are required.

### Sample safety boundaries

This is a trusted-user development sample, **not a hardened multi-user service**.
Like the Python sample, it enables Copilot's built-in shell/file tools and
automatically approves tool permission requests. The conversation working
directory and file-delivery checks are **not an execution sandbox**. Do not
expose this configuration to untrusted users, sensitive files, or privileged
credentials. For production, isolate tool execution and enforce an explicit
permission policy.

File downloads/uploads accept HTTPS SharePoint/OneDrive hosts only and do not
follow redirects. Files are limited to **4 MiB**. Generated-file delivery is
limited to regular files beneath the current conversation directory; symlinks
are rejected. File Consent uses a random conversation-scoped token backed by a
local pending record, not file bytes echoed through the card. Offers expire
after an hour and require the same durable `$HOME` on the later invoke.
Pending and shared files need a retention/cleanup policy for production use.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0).
- On Windows, clone to a short path such as `C:\src\foundry-samples`.
  The bundled native Copilot runtime can fail to start from deeply nested paths.
- A Foundry project and a deployed model supporting tools; vision requires
  an image-capable model. The manifest provisions `gpt-5-mini` if needed.
- Local identity: sign in with Azure CLI and grant **Azure AI User** on the
  project, or the equivalent role needed to invoke the model. The deployed
  agent identity needs model access as well.
- Environment variables:
  - `FOUNDRY_PROJECT_ENDPOINT`: `https://<account>.services.ai.azure.com/api/projects/<project>`.
  - `AZURE_AI_MODEL_DEPLOYMENT_NAME`: your deployment name, for example `gpt-5-mini`.
- Node.js for the optional local Playground client.
- For deployment: azd 1.27.1+, Azure CLI, a supported hosted-agent region,
  and Contributor plus User Access Administrator (or Owner) at the deployment
  scope. Your Teams policy must allow sideloading the app.
- The container includes Python and document libraries for model-generated
  Office/PDF files. Local Office/PDF generation additionally needs those tools;
  text-file generation does not.

## Option 1: Azure Developer CLI (`azd`)

From this sample directory:

```powershell
azd extension install azure.ai.agents
az login
azd auth login
azd env new my-dotnet-copilot
```

Choose a globally unique agent/Bot name in [azure.yaml](azure.yaml), changing
both the agent service key and its `name` while leaving `project` and
`entryPoint` unchanged.

```powershell
azd provision
azd deploy
```

Provisioning sets up the Foundry project, registry, and declared model.
Deployment builds remotely, creates an agent version, and configures its
Activity endpoint and Bot/Teams channel. Follow the generated Teams app setup
instructions to package and sideload the app.

Do not rerun bare `azd ai agent init` in an initialized sample directory.
For a separate project, initialize once with
`azd ai agent init -m <path-or-URL-to-this-azure.yaml>` instead.

Try in Teams:

1. `Add a task: buy coffee`, then `Show my tasks`; use Done/Delete/Add.
2. Share a text file or document and ask for its key points.
3. Share an image and ask what it contains.
4. `Create a short markdown report about solar energy`; click **Allow** on
   the File Consent card in a personal chat.

## Option 2: Local development / VS Code

Sign in and set environment variables in the terminal that launches the app:

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5-mini"
dotnet run --project .\src\github-copilot-dotnet-activity\github-copilot.csproj
```

For F5 debugging, open **`src/github-copilot-dotnet-activity`** as the VS Code
workspace root with C# Dev Kit. Launch VS Code from an environment containing
the two variables; the checked-in launch configuration forwards them.
The application reads environment variables; it does not load a `.env` file.

In another terminal:

```powershell
npx @microsoft/m365agentsplayground --app-endpoint http://localhost:8088/activity/messages --channel-id emulator
```

The Playground emulator exercises plain replies with mock channel delivery
but real Foundry model calls. Test Teams streaming, card rendering, authenticated
image fetching, and File Consent separately in Teams. The Responses/Invocations
Agent Inspector is not an Activity chat client.

## Tests

See the [shared test instructions](../tests/README.md) for offline regression
tests and opt-in authenticated model tests. Model tests incur normal inference
charges and do not prove deployed Bot/Teams authentication.

## Troubleshooting

- **Missing project/model settings:** set both environment variables before
  startup. Foundry supplies the project endpoint in hosted environments.
- **403 from the model:** check project/model access for the local Azure
  identity or the hosted agent instance identity.
- **Copilot runtime download blocked:** allow access to the matching
  `github/copilot-cli` release assets or use the SDK's documented release mirror.
- **Windows Linux cross-publish fails in `tar.exe`:** clone to a short path,
  or pass `--artifacts-path C:\build\activity` to `dotnet publish`; long nested
  Windows paths can exceed the extractor's limit.
- **Startup fails with "filename or extension is too long":** use a short
  checkout path as above and rebuild; Windows must also be able to launch the
  bundled runtime from the output directory.
- **A shared file cannot be downloaded:** check the declared size and that its
  signed URL is an allowed SharePoint/OneDrive HTTPS URL without a redirect.
- **File offer expired or missing:** generate the file again. Pending state
  must survive until the user consents.

## Next steps

- [Echo sample](../echo) for the minimal Activity host.
- [GitHub Copilot SDK](https://github.com/github/copilot-sdk) for custom
  permission policies and tool configuration.
