<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Hosted Agent — Adapter Mode (.NET)

## What this sample demonstrates

This is a deployable Foundry Hosted Agent application. It adds voice to an
HTTP-shaped streaming Echo agent without teaching its business
handler the Bridge state machine. This is a new, standalone sample; the existing
basic, LangChain and LangGraph examples are not modified.

The single Hosted Agent declares only `voice_conversation_engine:1.0.0`.
Voice Live connects to its `/voice_conversation_engine` route using Bridge messages
version `1.0`. Inside the process, the adapter calls the original invocation
handler as a function. **There is no second Agent, HTTP hop, loopback client, or
registered HTTP business endpoint.** The Voice Agent `conversation_engine`
reference (`conversationEngine` in the manifest) points to this same Hosted Agent.

## Hosted Agent entry point

`azure.yaml` registers `kind: hosted`, .NET 10 and `VoiceLiveAdapter.dll` as the
entry point. `Program.cs` starts the long-running AgentServer host; the adapter
invokes `EchoHttpAgent.HandleAsync` in process and streams the Echo reply back
over CE. This is the application that runs locally and after deployment.

`smoke/VoiceLiveAdapter.SmokeTest.csproj` is only an optional client for checking
a running Agent. It is not the Hosted Agent project and is never executed by deployment.

## How it works

`EchoHttpAgent.cs` contains an ordinary `InvocationHandler.HandleAsync` implementation.
`Program.cs` injects it into `InvocationAdapter`, then starts the typed Voice host.
The Echo handler is **not** registered with `AddInvocations` or started as an HTTP server.

Echo returns the input verbatim in word-sized chunks, preserving leading/trailing
whitespace and Unicode. Slash-prefixed input is ordinary text, not a command.
There is no model, tool, business-history store or external backend dependency.

The internal request is `{"input":"Hello world"}`. The handler's SSE profile is:

```text
data: {"type":"token","content":"Hello"}

data: {"type":"token","content":" world"}

data: {"type":"done","full_text":"Hello world"}

```

The sample-maintained `Adapter/` directory owns SDK callbacks, response/input
correlation, bounded capacity, asynchronous scheduling, interruption, cancellation,
timeout handling, heard-text bookkeeping, telemetry and cleanup. The adapter
connects the original handler's response stream to a bounded in-process `Pipe`,
reads concurrently, propagates cancellation through `RequestAborted` and the handler
cancellation token, and waits for handler finalization before success.

SSE is parsed incrementally with bounded frames and output; split UTF-8/CRLF and
multiline data fields are supported. `done.full_text` must match accumulated tokens.
The adapter still drains the handler after `done`: later errors or final-save
failures cannot become a successful `response.done`. Malformed/truncated SSE,
HTTP errors and missing/duplicate completion fail rather than silently succeeding.
A single output item is completed after handler finalization.

## Prerequisites

1. The .NET 10 SDK. The sample uses the published
   [Invocations `1.0.0-beta.8`](https://www.nuget.org/packages/Azure.AI.AgentServer.Invocations/1.0.0-beta.8)
   package with public Core `1.0.0-beta.30`. Both restore from nuget.org without
   source-built SDK packages, private feeds or package credentials.
2. For deployment: azd 1.32.0+ with `azure.ai.agents` 1.0.0-beta.13+,
   a Foundry project and permissions to deploy Hosted and Voice agents.
3. The target environment must support dedicated Vienna/APIM CE routing and
   CE-aware Voice Live. Public SDK publication is not proof of regional rollout.

Local tests require no Azure credentials, model configuration, Cosmos, indexes,
RBAC changes or network setup. Deployment still needs the ordinary hosting and
regional speech capacity. No Bridge metadata or external CE Connection is needed.

## Option 1: Deploy with Azure Developer CLI

Initialize from the public sample after it is merged and synchronized:

```bash
azd ext install microsoft.foundry
azd auth login
az login
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/bring-your-own/conversation_engine/adapter_mode/azure.yaml
azd provision
azd deploy
```

The manifest declares a Foundry project, one Hosted CE Agent and its Voice wrapper,
with no model deployment. For an existing project, configure
`AZURE_AI_PROJECT_ID`, `FOUNDRY_PROJECT_ENDPOINT`, subscription and region first;
use `azd deploy` without provisioning a replacement project.

To run the same Hosted Agent locally with azd instead of deploying it:

```bash
azd ai agent run
```

Neither `azd ai agent invoke` nor Agent Inspector generates CE messages.
Use the smoke client locally; after deployment, connect to the Voice wrapper and
verify real audio, interruption and cleanup in your target environment. A local
test pass is not deployed validation; see the recorded [validation status](../README.md#validation-status).

## Option 2: Run the Hosted Agent locally

From `src/voice-live-adapter-dotnet`:

```bash
dotnet restore VoiceLiveAdapter.csproj
dotnet build VoiceLiveAdapter.csproj --no-restore
dotnet run --project VoiceLiveAdapter.csproj --no-restore
```

The SDK listens on `PORT` or `8088` and exposes `GET /readiness`.
The sample uses `/voice_conversation_engine`; SDK-retained compatibility routes
are not additional protocol declarations or an HTTP registration of the Echo handler.
The repository's .NET NuGet configuration uses only nuget.org.

### Optional protocol check

Keep the Hosted Agent running. In another terminal, run the separate validation client:

```bash
dotnet run --project smoke/VoiceLiveAdapter.SmokeTest.csproj -- --text "Hello,  世界 👋"
```

Expected sequence: `session.ready`, `response.created`, one or more
`response.output_text.delta` frames, `response.output_text.done`, `response.done`.
Completed and streamed text must exactly equal the supplied input.

## Test

```bash
dotnet test tests/VoiceHostedAgent.Tests.csproj --configuration Release
dotnet format VoiceLiveAdapter.csproj --verify-no-changes --no-restore
```

Tests cover Echo, first-chunk streaming, malformed SSE, cancellation and producer
disposal, finalization failures, bounded output, ID correlation, deadlines and
late `heard_text`. Tests do not make cloud calls. The shared cloud runner cannot
invoke CE; the central `hosted-agent-samples-ci-skiplist` records this deployment
limitation, not a passing cloud test. Build-readiness checks and unit tests still run.
The public test spec at
`.azure-pipelines/hosted-agent-tests/csharp/bring-your-own/conversation_engine/adapter_mode/test-spec.yml`
and its Invocations-compatible raw-evidence plan are fixture validation only,
not support for invoking this CE-only Agent through HTTP.

## Customization and boundaries

Replace the Echo handler and, if its event schema differs, the mapping in
`Adapter/InvocationAdapter.cs`. Keep the protocol runtime unchanged.
This adapter supports the illustrated token/done SSE profile, not arbitrary
HTTP middleware, HTTP LROs, structured data or automatic business-state recovery.

The handler must cooperate with cancellation and release its nested generators,
model/tool requests and resources in its own finalization. Cancelling output
does not undo a business side effect. Echo has no business history; a stateful
replacement still owns its persistence and any reconciliation of unheard text.
The adapter's `heard_text` record is not an automatic rollback of that history.
No persistence service, replay or exactly-once business guarantee is added.

Session-end, disconnect and server shutdown cancel/drain connection-owned work.
The stateless Echo can accept a reconnect without restoring business history;
a stateful replacement must restore the state it needs or explicitly reject it.

## Troubleshooting

- Bridge message version is `1.0`; the independently versioned Hosted declaration
  is `voice_conversation_engine:1.0.0`.
- Start the server before the smoke client and match `--uri` to `PORT`.
- Keep deployed audio validation separate from local fixture and unit-test checks;
  the dated smoke results do not establish readiness in every target environment.

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Dedicated CE public contract](https://github.com/Azure/azure-rest-api-specs/pull/47228)
