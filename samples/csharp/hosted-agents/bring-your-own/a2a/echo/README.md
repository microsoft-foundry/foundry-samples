# Native A2A Echo and streaming (.NET)

## What this sample demonstrates

A deterministic native A2A v1 Echo agent using the **unpublished
`Azure.AI.AgentServer.A2A` source project**. It mirrors the
[Python Echo reference](../../../../../python/hosted-agents/bring-your-own/a2a/echo/):

- `SendMessage` returns a completed Task containing exactly `Echo: <input>`.
- Explicit `SendStreamingMessage` demonstrates incremental updates to one artifact.
- A .NET client verifies Task/artifact identity, append/final flags, exact output,
  completion, measured live delivery, and the same final artifact through `GetTask`.
- The existing Agent Server host supplies readiness, routes, request context, and
  tracing; the sample does not implement its own A2A server.

No model deployment or LLM call is used. **No SDK alpha package is required,
created, or published.** The server builds our local SDK checkout through
`ProjectReference`. The client uses the published Azure Identity library only
when authenticating to Foundry.

This is a development/reference sample, not a merge-ready published-package
quickstart. The SDK and this sample still require their normal reviews.

## How it works

`Program.cs` composes `AddA2A<EchoAgent>(card)` onto `AgentHost`. `EchoAgent`
implements the native `IAgentHandler` and uses native `TaskUpdater` and `Part`
types. An explicit native `InMemoryTaskStore` matches the Python reference:
tasks survive requests within the same process, **not restarts or replicas**.
This intentionally does not test the SDK's default Foundry-backed task store.

Ordinary Echo has no artificial delay. Message metadata
`{"streaming_demo": true}` enables the demonstration: split the exact response
into newline-preserving chunks, batch to at most 16 updates, and wait 500 ms
between updates to the same artifact. The final output remains unchanged.

The client uses explicit JSON-RPC requests rather than allowing discovery to
silently select a unary transport. The public Foundry card can currently report
`streaming: false` even while the explicit SSE request path works. This sample
does not rewrite that public capability.

## Prerequisites

- .NET 10 SDK.
- A checkout of `azure-sdk-for-net` containing our unpublished
  `sdk/agentserver/Azure.AI.AgentServer.A2A` project and its matching Core changes.
- For deployment: Azure Developer CLI with the Foundry extensions, an existing
  Foundry project supporting hosted agents, and permission to deploy agents.
- Sign in manually with `azd auth login` and `az login` when needed. Never put
  credentials in source files or command arguments.

The .NET server is not installed from NuGet. Set its source location in the
current shell, from this sample directory:

```powershell
$env:AGENTSERVER_DOTNET_SDK_ROOT = "C:\a2a\azure-sdk-for-net"
dotnet build .\src\echo-a2a-dotnet\EchoA2A.csproj
dotnet build .\clients\EchoClient\EchoClient.csproj
dotnet test .\tests\EchoSample.Tests\EchoSample.Tests.csproj
```

Alternatively pass `-p:AgentServerSdkRoot="<checkout>"` to build/test commands.
A missing source dependency fails with an actionable error; there is no
fallback to a different or previously published hosting library.

## Run locally

```powershell
$env:AGENTSERVER_DOTNET_SDK_ROOT = "C:\a2a\azure-sdk-for-net"
$env:PORT = "8088"
$env:A2A_AGENT_URL = "http://localhost:8088/a2a"
dotnet run --project .\src\echo-a2a-dotnet\EchoA2A.csproj --no-launch-profile
```

Wait for the listening message. In a second terminal:

```powershell
dotnet run --project .\clients\EchoClient -- `
  --endpoint "http://localhost:8088/a2a" `
  --card-endpoint "http://localhost:8088/a2a/.well-known/agent-card.json" `
  --message "hello" --output .test-results\local-unary.json

dotnet run --project .\clients\EchoClient -- `
  --endpoint "http://localhost:8088/a2a" --stream `
  --output .test-results\local-stream.json
```

Successful runs print `PASS` only after exact artifact and `GetTask` checks.
Streaming prints each event with its arrival time, rejects unary fallback,
requires 2-16 updates, and rejects delivery spread below 250 ms per expected
chunk gap. Use a multiline message when supplying `--message` with `--stream`.
Evidence includes the exact request JSON, received events, timings, Task ID,
trace ID, and final output hash. Authorization headers/tokens are never saved.

## Deploy source-built output with azd

The manifest uses `.NET 10`, `dependencyResolution: bundled`, and a separate
agent name, `echo-a2a-dotnet`. `azd` publishes the .NET application **locally**
using the SDK project references, then uploads the compiled application and
dependencies. Foundry does not need access to the SDK checkout or a package feed.

Use an existing project. No model or new project needs provisioning. Create the
deployment copy **outside** this sample, since azd rejects a template copied into
itself:

```powershell
.\scripts\Deploy-Source.ps1 `
  -SdkRoot "C:\a2a\azure-sdk-for-net" `
  -ProjectResourceId "<existing-Foundry-project-ARM-resource-ID>" `
  -DeploymentDirectory "C:\a2a-runs\dotnet-a2a" `
  -EnvironmentName "dotnet-a2a-dev"
```

The script initializes the sample against that project and deploys
`echo-a2a-dotnet`. It does not publish an SDK package or change the Python agent.
For a subsequent deployment, enter the generated
`<DeploymentDirectory>\echo-a2a-dotnet` directory:

```powershell
$env:AGENTSERVER_DOTNET_SDK_ROOT = "C:\a2a\azure-sdk-for-net"
azd deploy echo-a2a-dotnet --no-prompt
azd ai agent show echo-a2a-dotnet --output json
```

The deployment copy is independent of the original sample: copy intentional
source changes into it before redeploying, or initialize a fresh deployment
directory. Set the SDK source variable for every new shell.

### Test the deployed agent

From the generated deployment directory, create a session bound to the deployed
version. Keep the returned session ID:

```powershell
azd ai agent sessions create echo-a2a-dotnet --version "<deployed-version>" `
  --session-id "<unique-session-id>" --no-prompt --output json
```

From this source sample directory, invoke with the .NET client:

```powershell
$projectEndpoint = "https://<account>.services.ai.azure.com/api/projects/<project>"
$rpc = "$projectEndpoint/agents/echo-a2a-dotnet/endpoint/protocols/a2a?api-version=v1"
$card = "$projectEndpoint/agents/echo-a2a-dotnet/endpoint/protocols/a2a/agentCard/v1.0?api-version=v1"
$session = "<returned-session-id>"

dotnet run --project .\clients\EchoClient -- `
  --endpoint $rpc --card-endpoint $card --azure-auth --session-id $session `
  --message "hosted hello" --output .test-results\hosted-unary.json

dotnet run --project .\clients\EchoClient -- `
  --endpoint $rpc --azure-auth --session-id $session --stream `
  --output .test-results\hosted-stream.json
```

The client obtains an Azure Developer CLI credential in memory. It uses the same
session for the streaming request and `GetTask` verification. It fails instead
of claiming success on a JSON-RPC error, incomplete stream, incorrect output,
or buffered delivery.

The manifest lists `responses` in the public endpoint settings only because the
current Foundry Agent Card gateway requires it, matching the Python reference.
The application installs **only A2A**, not a Responses handler.

### Session retention and cleanup

Retain sessions when inspecting artifacts and logs. They consume resources and
expire according to platform policies. When finished, delete only the session
you created, from the deployment directory:

```powershell
azd ai agent sessions delete "<your-test-session-id>" --agent-name echo-a2a-dotnet --no-prompt
```

Do not delete pre-existing Python sessions or change the Python endpoint.

## Tests and limitations

The offline tests cover exact newline/Unicode preservation, bounded chunk count,
multiline SSE parsing, truncated-event rejection, unary-fallback rejection,
append ordering, exact output, buffering detection, and completion.

The [public cloud test contract](../../../../../../.azure-pipelines/hosted-agent-tests/csharp/bring-your-own/a2a/echo/test-spec.yml)
declares the ordinary Echo behavior.
Schema validation can run, but the shared cloud harness does not yet support
A2A planning/invocation. Use the dedicated .NET client; do not claim that a
Responses/Invocations plan validates A2A, and do not add a CI bypass.

Known hosting-library review gaps remain outside this sample: session response
headers and child-span session propagation, framework-generated error
classification, request-buffering behavior, and the default durable store's
credential/pagination design. Passing this Echo demonstration does not resolve
those findings or prove durable recovery, reconnect/replay, or production readiness.

For source-built binaries, prefer bundled deployment. A remote source build
cannot resolve the unpublished SDK from a package registry.

## Next steps

- Compare the [Python implementation](../../../../../python/hosted-agents/bring-your-own/a2a/echo/).
- Review the SDK findings separately before changing storage or claiming broader
  hosting-contract compliance.
- Use the recorded trace ID when inspecting hosted invocation and A2A spans.
  Trace IDs in client evidence are correlation inputs, not proof of export.
