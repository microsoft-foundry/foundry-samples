<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Conversation Engine hosted-agent samples

## What these samples demonstrate

These samples implement a **hosted conversation engine** for Voice Live without adding
audio-processing code. They implement Voice Live Bridge Protocol `1.0` on the
dedicated `voice_conversation_engine` endpoint by using the typed AgentServer Voice API.

[Microsoft Foundry Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)
owns the real-time audio pipeline: speech recognition, turn detection, speech synthesis, playback,
and interruption. The hosted agent continues to work with text and control events, calls a Foundry
model through the Responses API, and streams response text back to Voice Live for synthesis.

## Samples

| Language | Sample | Description |
| --- | --- | --- |
| Python | [Voice Conversation Engine — Basic Python](basic/) | A framework-free Python conversation engine using `azure-ai-agentserver-invocations`. |
| Python | [Voice Conversation Engine — LangChain Python](langchain/) | A tool-using LangChain conversation engine backed by the Foundry Responses API. |
| Python | [Voice Conversation Engine — LangGraph Python](langgraph/) | An explicit StateGraph conversation engine with model and tool nodes backed by the Foundry Responses API. |

All three samples demonstrate the same Bridge Protocol behavior while preserving their original
model and tool implementations.

The existing `voice-agent-target-agent` directory and `voice-live-bridge-*` project/resource
identifiers are retained for path and deployment compatibility. The supported Hosted protocol
is selected by `voice_conversation_engine:1.0.0`, not by those historical names.

## How it works

```text
Caller audio
    → Foundry voice agent
    → Voice Live (STT, VAD, TTS, and barge-in)
    → Bridge Protocol 1.0 over voice_conversation_engine
    → hosted conversation engine
    → Foundry model Responses API
```

The caller connects to a Foundry **voice agent**, not directly to the hosted conversation engine.
The voice agent references the deployed conversation engine in the same Foundry project. Voice Live
opens the `voice_conversation_engine` agent leg and exchanges typed Bridge messages with the engine
while the caller sends and receives audio through the normal voice WebSocket.

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

The samples demonstrate the Protocol `1.0` customer surface:

- application readiness with `session.ready` and `session.rejected`;
- text input and streaming or completed text output;
- static greeting context and no-input turns;
- caller barge-in and heard-text reconciliation;
- proactive-response admission;
- agent-initiated response cancellation;
- response timeouts and sanitized agent errors; and
- drained or immediate call termination.

Protocol `1.0` does not include DTMF, image input, app-driven history mutation, or hosted-agent
handoff. Voice Live, rather than the hosted agent, remains responsible for all audio handling.

## Required conversation-engine configuration

Each hosted conversation engine declares this protocol in `azure.yaml`:

```yaml
protocols:
  - protocol: voice_conversation_engine
    version: 1.0.0
```

The Hosted protocol version `1.0.0` selects Bridge message version `1.0`; the two version numbers
are independent. Neither `voiceLiveCompatible` nor `bridgeProtocolVersion` metadata is required.
The Voice wrapper's `conversationEngine` reference is unchanged and requires the new protocol
declaration. Caller interruption uses `user.barge_in` / `on_user_barge_in`.

The typed SDK also retains its independent `/invocations_ws` route for compatibility; the samples
declare only the dedicated CE protocol. Deployment requires matching Hosted Agent ingress and
Voice Live support for `voice_conversation_engine:1.0.0`, not just the published SDK. Confirm that
platform rollout before deploying. Local fake-model tests and protocol smoke tests do not validate
cloud routing, model access, or managed voice/audio readiness.

## Run a sample

Choose a sample from the table above and follow its README for prerequisites, local setup,
deployment, protocol smoke testing, and troubleshooting. For example, initialize the Python sample
from its public manifest with the Azure Developer CLI:

```bash
mkdir voice-live-bridge-basic-python
cd voice-live-bridge-basic-python
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voice-agent-target-agent/basic/azure.yaml
azd provision
azd ai agent run
```

Standard request/response tools such as `azd ai agent invoke` and the Foundry Toolkit Agent
Inspector do not generate Voice Live Bridge WebSocket events. Use the protocol-aware smoke client
included with the selected sample for local testing.

## Connect the conversation engine to Voice Live

The sample `azure.yaml` already declares a managed Voice wrapper agent whose `conversationEngine`
references this hosted conversation engine. `azd deploy` deploys both agents; no manual JSON
wrapper creation is required for the main azd flow.

The caller connects to the Voice wrapper's Voice WebSocket endpoint and never sends Bridge messages
directly to the hosted conversation engine. Conversation logic, model calls, tools, and response
generation belong to the conversation engine. Voice configuration and the managed audio experience
belong to the Voice wrapper and Voice Live.

## Next steps

- [Voice Conversation Engine — Basic Python](basic/)
- [Voice Conversation Engine — LangChain Python](langchain/)
- [Voice Conversation Engine — LangGraph Python](langgraph/)
- [Microsoft Foundry hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK for Python](https://pypi.org/project/azure-ai-agentserver-invocations/)
