<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Bridge — Basic .NET

## What this sample demonstrates

This sample gives a hosted .NET text agent a managed voice experience without adding audio code to
the agent. It implements Voice Live Bridge Protocol `1.0` with the typed
`Azure.AI.AgentServer.Invocations.Voice` API and streams a fixed thirty-word children's story to Voice Live.
The echo path contains no model client, LLM call, or prompt. Playback and protocol state are retained.
There is no LLM client package reference, model environment configuration, or model deployment.

Voice Live owns audio input, speech recognition, turn detection, synthesis, playback interruption,
and proactive-response admission. This hosted agent receives text and control events on
`/voice_conversation_engine`.

## How it works

`OnUserMessageAsync` validates the input, defines the story, and passes an asynchronous word stream to
`SendEcho`. There is no command parser, model call, or prompt; the input text does not change the story.

`SendEcho` accepts `IAsyncEnumerable<string>`, schedules cancellable work, and returns immediately.
The coordinator uses `await foreach` with cancellation and sends each chunk as it arrives, without
pre-buffering. Replace the local `StreamStory` iterator in `OnUserMessageAsync` with your own
asynchronous source; keep its `[EnumeratorCancellation]` token. Iterator cleanup runs even when
generation is cancelled or a send fails.
The response task opens a response, sends thirty word deltas, and completes the item and response.
The user-message callback
returns promptly, leaving the SDK receive loop free to dispatch interruption, cancellation,
timeout, and session events while output is in flight.

`VoiceResponseCoordinator` retains cancellable response execution and terminal sequencing.
`VoiceConnectionState` retains response/input-ID correlation, bounded capacity, proactive
admission, and playback synchronization. `OnUserBargeInAsync` and `OnResponseCancelledAsync` record
`heard_text` even for recent completed responses, then cancel any pending output.
`OnResponseTimeoutAsync` cancels work selected by response ID or input IDs.

Input-resolution frames (`response.created` and `response.none`) use a per-connection FIFO queue
reserved before background output is scheduled. Only these frames are ordered; echo output remains
cancellable. Input correlation is retained until final cleanup, including while `response.done` is
being sent. Termination selects response outcomes before triggering cancellation outside the state lock.

This matches the Python samples: the echo handler is simple, and the protocol lifecycle remains
fully represented. `VOICE_SAMPLE_REJECT_START=true` also exercises startup rejection in both.

Bridge Protocol `1.0` is the application contract; the manifest's `voice_conversation_engine` `1.0.0` selects
the independently versioned Hosted Agent ingress.

## Prerequisites

1. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0).
2. For deployment: Azure Developer CLI (`azd`) 1.32.0 or later with the
   `azure.ai.agents` extension 1.0.0-beta.13 or later.
3. For deployment: a Foundry project and permission to deploy hosted and Voice agents.
4. For deployment: Vienna/APIM and Voice Live support for `voice_conversation_engine:1.0.0`.

Local echo and protocol tests need no Azure credentials or model settings. The manifest declares
only the Foundry project, Hosted Agent, and Voice wrapper; it does not provision an LLM deployment.

Install and authenticate the tools:

```bash
azd ext install microsoft.foundry
azd auth login
az login
```

## Dedicated conversation-engine protocol

The manifest declares only `voice_conversation_engine:1.0.0`, and the typed Voice SDK registers
`/voice_conversation_engine`. Bridge messages still use `session.start.protocol_version: "1.0"`.
`voiceLiveCompatible` and `bridgeProtocolVersion` metadata are deprecated for new agents and
are omitted. Existing metadata-selected `invocations_ws` agents remain a Voice Live compatibility
path; the SDK also retains that local route, but this sample does not declare it.
The Voice Agent's `conversation_engine` reference (`conversationEngine` in `azure.yaml`) is unchanged.

The runtime pins the published
[`Azure.AI.AgentServer.Invocations` `1.0.0-beta.8`](https://www.nuget.org/packages/Azure.AI.AgentServer.Invocations/1.0.0-beta.8)
with public Core `1.0.0-beta.30`. Both packages are available from nuget.org.
Clean restore, build, publish and a deployed audio smoke passed using these official packages;
no source-built SDK package or private feed is needed. Do not substitute beta.7, which lacks
the dedicated CE API. See the [validation status](../README.md#validation-status) for scope.

Before deploying the new declaration, verify the target Vienna/APIM and Voice Live rollout.
After deployment, verify readiness, spoken output, and `user.barge_in` interruption through the
Voice wrapper. Local WebSocket tests do not establish deployed routing or audio-path readiness.

## Option 1: Azure Developer CLI

Initialize this sample from the public manifest in a new directory:

```bash
mkdir voice-live-bridge-basic-dotnet
cd voice-live-bridge-basic-dotnet
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/bring-your-own/conversation_engine/basic/azure.yaml
```

Provision the declared Foundry project when needed, run locally, and deploy:

```bash
azd provision
azd ai agent run
azd deploy
```

Neither `azd ai agent invoke` nor Agent Inspector generates Voice Live Bridge events. Use the
protocol-aware smoke client described below to exercise this agent.

### Deploy to an existing Foundry project

To reuse an existing project, configure its resources explicitly and deploy:

```bash
azd env new "<environment-name>"
azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
azd env set AZURE_LOCATION "<foundry-project-region>"
azd env set AZURE_AI_PROJECT_ID "<foundry-project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "<foundry-project-endpoint>"
azd deploy
```

Copy the project resource ID, endpoint, and region from **Manage** > **Project details** in the
Foundry portal. No model deployment name, model API key, or model quota is required by this sample.
Use `azd deploy` for this existing-project flow; `azd provision` applies the new-project declaration.

## Option 2: Run locally

This sample uses direct code deployment; no Docker build is required. From the sample root,
restore and build the application:

```bash
dotnet restore src/voice-live-bridge-basic-dotnet/VoiceLiveBridgeBasic.csproj
dotnet build src/voice-live-bridge-basic-dotnet/VoiceLiveBridgeBasic.csproj --no-restore
```

The runtime's `NuGet.config` clears inherited sources and uses only nuget.org for every package.
`Azure.AI.AgentServer.Invocations` is pinned to `1.0.0-beta.8`; its minimum Core dependency is the
published `Azure.AI.AgentServer.Core` `1.0.0-beta.30`. Both packages restore from nuget.org;
no Azure Artifacts feed, package credentials, or pre-populated local package cache is required.

Start the echo server directly, without loading model settings:

```bash
cd src/voice-live-bridge-basic-dotnet
dotnet run --project VoiceLiveBridgeBasic.csproj --no-restore
```

The server listens on `PORT` or port `8088` and exposes `GET /readiness` and the
`/voice_conversation_engine` WebSocket route. `.env.example` documents only the optional port setting.

The Foundry Toolkit Agent Inspector does not generate Bridge Protocol WebSocket events. Start the
server manually or with `azd ai agent run`, then use the smoke client.

## Local protocol smoke test

In a second terminal, from the runtime directory, run:

```bash
dotnet run --project smoke/VoiceLiveBridgeBasic.SmokeTest.csproj
```

The default smoke input is `Hello, Voice Live!`; the client validates both the wire sequence and
the fixed story, all thirty word deltas, and their response/item correlation.
Override the target or input when needed:

```bash
dotnet run --project smoke/VoiceLiveBridgeBasic.SmokeTest.csproj -- \
  --uri ws://127.0.0.1:8088/voice_conversation_engine \
  --text "Hello, Voice Live!"
```

Expected message sequence:

```text
session.ready
response.created
response.output_text.delta (30 frames, one per word)
response.output_text.done
response.done
```

## Give the hosted agent a voice

The sample `azure.yaml` already declares a managed Voice wrapper agent that targets this hosted
agent. `azd deploy` deploys both the hosted target and the Voice wrapper; no manual JSON wrapper
creation is required for the main azd flow.

The caller connects to the Voice wrapper's Voice WebSocket endpoint and never sends Bridge messages
directly to the hosted text agent. The target streams the story and handles Bridge control events.
Voice configuration and the managed audio experience belong to the Voice wrapper and Voice Live.

## User messages

Every valid user message, including `/end` and Unicode text, triggers this same thirty-word story:

> Once a little rabbit found a lonely star. She carried it up the tallest hill, where friendly
> fireflies helped it shine again. That night, everyone dreamed of kindness and adventure.

There is no command parser. Each response sends thirty word deltas sharing one output item,
then the full story in `response.output_text.done`, followed by `response.done`.
Empty and oversized input still receive `response.none`.

## Tests

Tests verify the thirty-word stream, session lifecycle, response/input-ID correlation, and telemetry.
Blocked output transports exercise barge-in, cancellation, and timeout while a response is pending.
Late playback events verify caller-heard synchronization. Tests make no cloud calls.

Scheduling and blocked-send fixtures also verify ordered input resolution, input-ID timeouts during
`response.done`, and inline cancellation cleanup. These are local test doubles, not deployment settings.
Run the suite from the runtime directory:

```bash
dotnet test tests/VoiceHostedAgent.Tests.csproj
```

From the sample root, the build, formatting, and test commands are listed in `sample.yaml`.
The repository's `hosted-agent-samples-ci-skiplist` excludes this sample from shared
cloud deployment because the runner does not support `voice_conversation_engine`.
Build-readiness checks and unit tests still run; use the dedicated smoke client
for this protocol. The public behavior fixture is under
`.azure-pipelines/hosted-agent-tests/csharp/bring-your-own/conversation_engine/basic/`.

An isolated restore can verify that all dependencies are available from the same single source
used by deployment:

```bash
dotnet restore src/voice-live-bridge-basic-dotnet/tests/VoiceHostedAgent.Tests.csproj \
  --configfile src/voice-live-bridge-basic-dotnet/NuGet.config \
  --packages /tmp/voice-bridge-nuget-packages --no-http-cache --force
```

Local build, tests, and WebSocket smoke checks do not validate Foundry deployment permissions,
hosting capacity, Voice Live access, or the managed audio
path. After deploying, verify readiness and a spoken echo through the declared Voice wrapper.

## Design notes

- The story and its word sequence are directly in `OnUserMessageAsync`; no model history is added.
- Echo is scheduled as cancellable work so the receive loop remains available for control events.
- Barge-in and cancellation synchronize caller-heard text and stop pending output.
- Playback state is bounded to 64 known responses and cleared on session termination.
- Custom spans contain identifiers, durations, and status, but no prompt or response content.
- A deployed two-turn audio smoke passed with public SDK packages; see the
  [validation status](../README.md#validation-status). Perform deployment-specific validation
  in your own environment, including cloud interruption and reconnect scenarios.

## Troubleshooting

- If `dotnet restore` cannot find `Azure.AI.AgentServer.Invocations`, verify that the runtime
  `NuGet.config` is present and nuget.org is reachable.
- If the server rejects `session.start` with `protocol_mismatch`, ensure the event declares Bridge
  Protocol `1.0`. This is separate from `voice_conversation_engine` transport version `1.0.0` in `azure.yaml`.
- If the smoke client cannot connect, start the server first and verify port `8088`, or pass a
  matching `--uri`.
- Agent Inspector and `azd ai agent invoke` cannot validate this protocol because they do not emit
  Voice Live Bridge event frames.

## Next steps

- [Voice Live Bridge samples](../)
- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK for .NET](https://www.nuget.org/packages/Azure.AI.AgentServer.Invocations)
