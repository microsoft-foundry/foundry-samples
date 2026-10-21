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
existing `invocations_ws` transport by using the typed AgentServer Voice API.

[Microsoft Foundry Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)
owns the real-time audio pipeline: speech recognition, turn detection, speech synthesis, playback,
and interruption. The hosted agent continues to work with text and control events, calls a Foundry
model through the Responses API, and streams response text back to Voice Live for synthesis.

## Samples

| Language | Sample | Description |
| --- | --- | --- |
| Python | [Voice Live Bridge — Basic Python](basic/) | A framework-free Python hosted agent using `azure-ai-agentserver-invocations`. |
| Python | [Voice Live Bridge — LangChain Python](langchain/) | A tool-using LangChain hosted agent backed by the Foundry Responses API. |
| Python | [Voice Live Bridge — LangGraph Python](langgraph/) | An explicit StateGraph hosted agent with model and tool nodes backed by the Foundry Responses API. |
| C# | [Voice Live Bridge — Basic .NET](../../../../csharp/hosted-agents/bring-your-own/voice-agent-target-agent/basic/) | The equivalent framework-free hosted agent using the AgentServer Invocations SDK for .NET. |

All implementations demonstrate the same Bridge Protocol behavior so you can start with the
language that matches your application.

## How it works

```text
Caller audio
    → Foundry voice agent
    → Voice Live (STT, VAD, TTS, and barge-in)
    → Bridge Protocol 1.0 over invocations_ws
    → hosted text agent
    → Foundry model Responses API
```

The caller connects to a Foundry **voice agent**, not directly to the hosted text agent. The voice
agent targets a deployed hosted agent in the same Foundry project. Voice Live opens the
`invocations_ws` agent leg and exchanges typed Bridge messages with the target agent while the
caller sends and receives audio through the normal voice WebSocket.

After the WebSocket upgrade, the basic flow is:

1. Voice Live sends `session.start` with Bridge Protocol version `1.0`.
2. The hosted agent validates the event and explicitly sends `session.ready`.
3. Voice Live sends each completed transcript as a `user.message` text event.
4. The hosted agent opens a response with `response.created`, streams
   `response.output_text.delta` events, completes the output item, and sends `response.done`.
5. Voice Live synthesizes the streamed text and sends audio to the caller.

Bridge Protocol `1.0` is an **application protocol layered on `invocations_ws`**; it is not an audio
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

## Required hosted-agent configuration

Each target hosted agent opts into the typed bridge with these declarations in `azure.yaml`:

```yaml
metadata:
  voiceLiveCompatible: "true"
  bridgeProtocolVersion: "1.0"
protocols:
  - protocol: invocations_ws
    version: 1.0.0
```

The `bridgeProtocolVersion` value selects the Bridge application contract. The `invocations_ws`
version selects the Hosted Agent ingress contract; the two version numbers are unrelated.

## Run a sample

Choose a sample from the table above and follow its README for prerequisites, local setup,
deployment, protocol smoke testing, and troubleshooting. For example, initialize the Python sample
from its public manifest with the Azure Developer CLI:

```bash
mkdir voice-live-bridge-basic-python
cd voice-live-bridge-basic-python
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voice-agent-target-agent/basic/azure.yaml
azd provision
azd ai agent run
```

Standard request/response tools such as `azd ai agent invoke` and the Foundry Toolkit Agent
Inspector do not generate Voice Live Bridge WebSocket events. Use the protocol-aware smoke client
included with the selected sample for local testing.

## Give the hosted agent a voice

The sample `azure.yaml` already declares a managed Voice wrapper agent that targets this hosted
agent. `azd deploy` deploys both the hosted target and the Voice wrapper; no manual JSON wrapper
creation is required for the main azd flow.

The caller connects to the Voice wrapper's Voice WebSocket endpoint and never sends Bridge messages
directly to the hosted text agent. Conversation logic, model calls, tools, and response generation
belong to the target hosted agent. Voice configuration and the managed audio experience belong to
the Voice wrapper and Voice Live.

## Next steps

- [Voice Live Bridge — Basic Python](basic/)
- [Voice Live Bridge — LangChain Python](langchain/)
- [Voice Live Bridge — LangGraph Python](langgraph/)
- [Microsoft Foundry hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK for Python](https://pypi.org/project/azure-ai-agentserver-invocations/)