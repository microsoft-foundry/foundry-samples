# Native A2A Echo and streaming (.NET)

## What this sample demonstrates

A deterministic native A2A 1.0 agent using published
`Azure.AI.AgentServer.A2A` **`1.0.0-alpha.20261109.2`**:

- `SendMessage` returns a completed Task containing exactly `Echo: <input>`.
- `SendStreamingMessage` emits incremental updates to one artifact.
- The .NET client verifies exact output, Task/artifact identity, append/final
  flags, measured delivery and the same final artifact through `GetTask`.

No model, Toolbox, SDK checkout or global NuGet configuration is required.
The sample-local [NuGet.Config](NuGet.Config) selects the public Azure SDK
development feed. This alpha was built from SDK commit `c07c20bf0` and includes
the fixes through that commit. It is not a stable SDK release.
The runtime source folder also carries that feed configuration, so an azd
copy of only the application can restore independently.

## How it works

`EchoAgent` implements native `IAgentHandler` and uses native `TaskUpdater`.
`AgentHost` supplies readiness, context, tracing and the A2A routes. The explicit
native in-memory task store persists across requests in one process, not across
restarts or replicas. It does not demonstrate durable executor recovery.

Normal Echo has no artificial delay. Message metadata
`{"streaming_demo": true}` enables up to 16 newline-preserving artifact chunks,
spaced 500 ms apart. The final output is unchanged.

## Prerequisites

- .NET 10 SDK and access to the Azure SDK development feed.
- For deployment: azd with the Foundry extension, a hosted-agent-enabled Foundry
  project and deployment permissions. Sign in manually with `azd auth login`
  and `az login` when required.

```powershell
dotnet build .\src\echo-a2a-dotnet\EchoA2A.csproj
dotnet build .\clients\EchoClient\EchoClient.csproj
dotnet test .\tests\EchoSample.Tests\EchoSample.Tests.csproj
```

## Run locally

```powershell
$env:PORT = "8088"
$env:A2A_AGENT_URL = "http://localhost:8088/a2a"
dotnet run --project .\src\echo-a2a-dotnet --no-launch-profile
```

In a second terminal:

```powershell
dotnet run --project .\clients\EchoClient -- `
  --endpoint "http://localhost:8088/a2a" `
  --card-endpoint "http://localhost:8088/a2a/.well-known/agent-card.json" `
  --message "hello" --output .test-results\local-unary.json

dotnet run --project .\clients\EchoClient -- `
  --endpoint "http://localhost:8088/a2a" --stream `
  --output .test-results\local-stream.json
```

The client prints `PASS` only after validating output and GetTask. Streaming
rejects unary fallback and buffered delivery; use a multiline message with
`--message` and `--stream`. Tokens are never written to its evidence files.

## Deploy with azd

The manifest uses .NET 10 and bundled code deployment. azd publishes the
application locally using the pinned NuGet package, then uploads the runtime
output; the hosted container does not need an SDK checkout.

Initialize a deployment copy outside this sample, using an existing project:

```powershell
.\scripts\Deploy-Source.ps1 `
  -ProjectResourceId "<existing-Foundry-project-ARM-resource-ID>" `
  -DeploymentDirectory "C:\a2a-runs\dotnet-a2a" `
  -EnvironmentName "dotnet-a2a-dev"
```

The script name is retained for compatibility; it deploys source using
**published NuGet dependencies**, not a source-built SDK.

From the generated deployment directory:

```powershell
azd ai agent sessions create echo-a2a-dotnet --version "<deployed-version>" `
  --session-id "<unique-session-id>" --no-prompt --output json
```

From the original sample directory:

```powershell
$projectEndpoint = "https://<account>.services.ai.azure.com/api/projects/<project>"
$rpc = "$projectEndpoint/agents/echo-a2a-dotnet/endpoint/protocols/a2a?api-version=v1"
$card = "$projectEndpoint/agents/echo-a2a-dotnet/endpoint/protocols/a2a/agentCard/v1.0?api-version=v1"

dotnet run --project .\clients\EchoClient -- `
  --endpoint $rpc --card-endpoint $card --azure-auth `
  --session-id "<returned-session-id>" --message "hello" `
  --output .test-results\hosted-unary.json
```

Use `--stream` for the explicit SSE check. The same session is used for
SendMessage and GetTask. The manifest's endpoint `responses` declaration matches
the gateway compatibility setting in the Python reference; only A2A is
implemented by the application.

## Tests and troubleshooting

Offline tests and the dedicated .NET client check output fidelity, stream
ordering, completion and delivery thresholds. The
[cloud contract](../../../../../../.azure-pipelines/hosted-agent-tests/csharp/bring-your-own/a2a/echo/test-spec.yml)
plans as native A2A. Planning is not execution: shared cloud execution needs
the native A2A runner proposed in samples PR #1144, or this dedicated client.

- Restore failures: verify access to the sample's Azure SDK development feed.
- Missing Task after restart: the explicit task store is in memory.
- Agent Card 404: verify endpoint, version, project permissions and role propagation.
- Public card reports no streaming: the client uses explicit SSE and never
  treats unary fallback as a streaming success.

Offline tests do not establish fresh hosted deployment, trace export,
cross-user cloud isolation or interrupted-task recovery.

## Next steps

- Compare [Python Echo](../../../../../python/hosted-agents/bring-your-own/a2a/echo/).
- Try the [travel planner with web search](../travel-planner-web-search/).
- Clean up only the sessions and deployment resources you created.
