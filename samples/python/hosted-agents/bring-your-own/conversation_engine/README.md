<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Bridge hosted-agent samples

## What these samples demonstrate

These samples show how to give a **hosted text agent** a managed voice experience without adding
audio-processing code to the agent. The agents implement Voice Live Bridge Protocol `1.0` on the
dedicated `voice_conversation_engine` transport by using the typed AgentServer Voice API.

[Microsoft Foundry Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)
owns the audio pipeline: speech recognition, turn detection, synthesis, playback, and interruption.
Python and .NET provide two integration styles: an in-process adapter around a simple streaming
HTTP-shaped Echo handler, and native CE samples that define a fixed thirty-word children's story
directly in their user-message handlers. Both styles schedule cancellable output so interruption,
cancellation, timeout, and session callbacks remain responsive. Neither requires a model call.

## Samples

| Language | Sample | Description |
| --- | --- | --- |
| Python | [Voice Live — Adapter Mode](adapter_mode/) | Recommended for reusing an invocation handler: a CE-only Agent calls a streaming HTTP-shaped Echo handler in process. |
| Python | [Voice Live Bridge — Basic Python](basic/) | A framework-free Python hosted agent using `azure-ai-agentserver-invocations`. |
| Python | [Voice Live Bridge — LangChain Python](langchain/) | Model-free async story stream; legacy directory/Agent names retained. |
| Python | [Voice Live Bridge — LangGraph Python](langgraph/) | Model-free async story stream; legacy directory/Agent names retained. |
| C# | [Voice Live — Adapter Mode](../../../../csharp/hosted-agents/bring-your-own/conversation_engine/adapter_mode/) | The equivalent in-process adapter and streaming Echo handler for .NET. |
| C# | [Voice Live Bridge — Basic .NET](../../../../csharp/hosted-agents/bring-your-own/conversation_engine/basic/) | The equivalent framework-free hosted agent using the AgentServer Invocations SDK for .NET. |

All implementations demonstrate the same Bridge Protocol behavior so you can start with the
language that matches your application.

## Choose an integration style

- **Adapter mode:** start here to reuse HTTP invocation logic without implementing Bridge
  callbacks in the business handler. The single Agent declares only `voice_conversation_engine`;
  its internal adapter calls the handler directly and consumes its SSE stream. There is no
  separately deployed adapter Agent, registered HTTP business endpoint, or loopback HTTP request.
  Customize `echo_agent.py` and its input/output mapping; the sample-maintained `adapter/` runtime
  owns response IDs, task scheduling, cancellation, timeouts, heard-text bookkeeping and cleanup.
- **Native CE mode:** use `basic`, `langchain`, or `langgraph` when you want to implement typed
  Voice callbacks directly and manage the application-owned protocol state. These existing
  samples retain their fixed story behavior; the legacy variant names do not add framework clients.

Adapter mode does not take over a replacement handler's business history or roll back side effects.
Its Echo is stateless; persistence and any reconciliation of unheard text remain business concerns.

## How it works

```text
Caller audio
    → Foundry voice agent
    → Voice Live (STT, VAD, TTS, and barge-in)
    → Bridge Protocol 1.0 over voice_conversation_engine
    → hosted text agent
    → Echo text (adapter mode) or a thirty-word story (native CE) streamed back to Voice Live
```

The caller connects to a Foundry **voice agent**, not directly to the hosted text agent. The voice
agent targets a deployed hosted agent in the same Foundry project. Voice Live opens the
`voice_conversation_engine` agent leg and exchanges typed Bridge messages with the conversation engine while the
caller sends and receives audio through the normal voice WebSocket.

After the WebSocket upgrade, the basic flow is:

1. Voice Live sends `session.start` with Bridge Protocol version `1.0`.
2. The hosted agent validates the event and explicitly sends `session.ready`.
3. Voice Live sends each completed transcript as a `user.message` text event.
4. The hosted agent opens a response with `response.created`, streams
   `response.output_text.delta` events, completes the output item, and sends `response.done`.
5. Voice Live synthesizes the streamed text and sends audio to the caller.

Bridge Protocol `1.0` is an **application protocol layered on `voice_conversation_engine`**; it is not an audio
protocol and is versioned independently from the Hosted Agent WebSocket ingress.

## Protocol capabilities

Adapter mode echoes each valid input verbatim in streaming chunks, preserving whitespace and
Unicode. Native CE samples stream the same thirty-word story for every valid input.
Slash-prefixed text such as `/help` or `/end` is ordinary text, not a command, in both styles.

The samples demonstrate the Protocol `1.0` customer surface:

- application readiness with `session.ready` and `session.rejected`;
- text input and streaming or completed text output;
- static greeting context and no-input turns;
- playback interruption managed by Voice Live, with Agent-side cancellation and heard-text synchronization;
- bounded inputs and response-duration telemetry; and
- drained call termination after repeated no-input events.

Protocol `1.0` does not include DTMF, image input, app-driven history mutation, or hosted-agent
handoff. Voice Live, rather than the hosted agent, remains responsible for all audio handling.

## Required hosted-agent configuration

Each hosted conversation engine opts into the typed bridge with these declarations in `azure.yaml`:

```yaml
protocols:
  - protocol: voice_conversation_engine
    version: 1.0.0
```

The `voice_conversation_engine:1.0.0` declaration selects the dedicated Hosted Agent ingress;
`session.start.protocol_version` remains `1.0` for Bridge messages. The Voice Agent configuration
property remains `conversation_engine` (`conversationEngine` in `azure.yaml`).

Neither `voiceLiveCompatible` nor `bridgeProtocolVersion` is required. They are deprecated for new
conversation engines; Voice Live retains the metadata-selected `invocations_ws` compatibility path
for existing agents. The typed SDK still exposes that local route, but these manifests declare only
`voice_conversation_engine`, and the default smoke clients use `/voice_conversation_engine`.

Deployment requires the matching Vienna/APIM endpoint and CE-aware Voice Live rollout. Deploy the
compatible SDK/runtime and declare the dedicated protocol only after that service path is available;
then verify readiness, spoken output, and interruption through the Voice wrapper. Local protocol
tests do not establish target-environment rollout or audio-path readiness.

## Run a sample

Choose a sample from the table above and follow its README for prerequisites, local setup,
deployment, protocol smoke testing, and troubleshooting. For example, initialize adapter mode
from its public manifest with the Azure Developer CLI:

```bash
mkdir voice-live-adapter-python
cd voice-live-adapter-python
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/conversation_engine/adapter_mode/azure.yaml
azd provision
azd ai agent run
```

New public manifest links become available only after merge and synchronization to the public
repository. Follow the selected sample's SDK/package prerequisites before running or deploying it.

Standard request/response tools such as `azd ai agent invoke` and the Foundry Toolkit Agent
Inspector do not generate Voice Live Bridge WebSocket events. Use the protocol-aware smoke client
included with the selected sample for local testing.

## Give the hosted agent a voice

The sample `azure.yaml` already declares a managed Voice wrapper agent that targets this hosted
agent. `azd deploy` deploys both the hosted target and the Voice wrapper; no manual JSON wrapper
creation is required for the main azd flow.

The caller connects to the Voice wrapper's Voice WebSocket endpoint and never sends Bridge messages
directly to the hosted text agent. The target streams its reply; voice configuration and the managed
audio experience belong to the Voice wrapper and Voice Live.

## Next steps

- [Voice Live — Adapter Mode](adapter_mode/)
- [Voice Live Bridge — Basic Python](basic/)
- [Voice Live Bridge — LangChain Python](langchain/)
- [Voice Live Bridge — LangGraph Python](langgraph/)
- [Microsoft Foundry hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK for Python](https://pypi.org/project/azure-ai-agentserver-invocations/)
