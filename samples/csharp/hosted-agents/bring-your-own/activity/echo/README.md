# What this sample demonstrates

A minimal **C# echo agent** using the **Activity protocol** and the
[Microsoft 365 Agents SDK](https://github.com/microsoft/Agents-for-net).
It echoes nonblank messages and welcomes new members. No model is required.
This is the .NET counterpart of the [Python echo sample](../../../../../python/hosted-agents/bring-your-own/activity/echo).

## How it works

[Program.cs](src/echo-dotnet-activity/Program.cs) hosts an ordinary
[EchoAgent](src/echo-dotnet-activity/EchoAgent.cs) with one line:

```csharp
ActivityServer.Run<EchoAgent>(args);
```

`Azure.AI.AgentServer.Activity` owns the Foundry hosting contract:
`POST /activity/messages`, readiness, session headers, tracing, and native
Microsoft 365 channel delivery. The agent owns message and welcome handlers.
The host uses the simple agent-instance identity model, not digital-worker auth.

The package is pinned to **`Azure.AI.AgentServer.Activity` `1.0.0-beta.1`**
from **NuGet.org**, configured in [NuGet.Config](src/echo-dotnet-activity/NuGet.Config).
Its Core dependency is installed automatically. This is a beta, not a GA release. Restore needs internet
access but no private feed credentials, local packages, or SDK source checkout.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0).
- For local chat: Node.js and [Microsoft 365 Agents Playground](https://learn.microsoft.com/microsoftteams/platform/toolkit/debug-your-agents-playground).
- For deployment: an Azure subscription in a
  [hosted-agent supported region](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents),
  Azure CLI, and Azure Developer CLI (`azd`) 1.27.1 or later.
- Deployment permissions: Owner, or Contributor plus User Access Administrator,
  at the target scope so the tooling can create resources and role assignments.
  Your organization must allow custom Teams apps to sideload the generated app.

## Option 1: Azure Developer CLI (`azd`)

Run from this sample directory (which already contains [azure.yaml](azure.yaml)):

```powershell
azd extension install azure.ai.agents
az login
azd auth login
azd env new my-dotnet-echo
```

Before deploying, choose a globally unique bot/agent name and set both the
agent service key and its `name` in `azure.yaml` to that value. Keep the
`project` path and `entryPoint` unchanged.

```powershell
azd provision
azd deploy
```

The Foundry provider provisions the project. The configured direct-code
deployment publishes the .NET application, creates an agent version, and
configures the Bot/Teams channel for the declared Activity endpoint.
Follow the generated `TEAMS_APP_SETUP.md` next to the source project.
It describes uploading the generated `appPackage.zip` in Teams, or installing
it for the signed-in user with the Microsoft 365 Agents Toolkit CLI:

```powershell
npm install -g @microsoft/m365agentstoolkit-cli
atk auth login
atk install --file-path .\src\echo-dotnet-activity\appPackage.zip --scope Personal
```

Send `hello` in the installed app and expect `Echo: hello`.

Do not rerun bare `azd ai agent init` in this already configured directory:
it can add another service. If initializing a separate directory, use
`azd ai agent init -m <path-or-URL-to-this-azure.yaml>` once instead.

## Option 2: Local development / VS Code

Open **`src/echo-dotnet-activity`** as the VS Code workspace root, install
C# Dev Kit, and press **F5**. Or run manually from this sample directory:

```powershell
dotnet run --project .\src\echo-dotnet-activity\echo.csproj
```

In another terminal, launch the Playground against the Activity endpoint:

```powershell
npx @microsoft/m365agentsplayground --app-endpoint http://localhost:8088/activity/messages --channel-id emulator
```

The emulator channel uses plain replies and local mock connector delivery.
Local Playground runs do **not** prove authenticated Teams delivery.
Use Teams after deployment to test that separately.

Readiness is available at `http://localhost:8088/readiness`. Posting with
`curl` and seeing HTTP 202 only proves acceptance: the reply is delivered
asynchronously to the activity's `serviceUrl`, not in the HTTP response.
The endpoint is `/activity/messages`, not `/api/messages`. The Foundry
Responses/Invocations Agent Inspector is not the chat client for this sample.

## Tests

From the repository root:

```powershell
dotnet test .\samples\csharp\hosted-agents\bring-your-own\activity\tests\ActivitySamples.Tests.csproj
```

The default test settings exclude live tests. The offline suite references
the actual sample agents and tests replies with the native SDK TestAdapter,
welcome behavior, and the HTTP readiness/acceptance contract.
See the [shared test instructions](../tests/README.md) for coverage boundaries.

## Troubleshooting

- **Restore cannot find the Activity package:** preserve the source-level
  `NuGet.Config` when copying the sample and check access to NuGet.org.
- **202 but no response in Teams:** check the agent logs and Bot setup.
  Foundry supplies the instance identity used for outbound authentication;
  do not copy production identity settings into anonymous local testing.
- **Bot name unavailable:** choose a unique service key and agent name before
  deployment.
- **Playground does not connect:** verify port 8088 is free and explicitly
  use `/activity/messages`.

## Next steps

- [GitHub Copilot assistant](../github-copilot) adds a model, tools, and files.
- [Activity SDK documentation](https://github.com/Azure/azure-sdk-for-net/tree/main/sdk/agentserver/Azure.AI.AgentServer.Activity).
