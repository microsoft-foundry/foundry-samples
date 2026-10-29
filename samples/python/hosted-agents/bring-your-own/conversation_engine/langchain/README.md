<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Bridge — LangChain Python

## What this sample demonstrates

This sample implements Voice Live Bridge Protocol `1.0` with the typed AgentServer Voice API.
Each valid user message triggers the same fixed, thirty-word children's story, streamed word by word.
The echo server does not initialize a model or interpret commands.

Voice Live owns speech recognition, turn detection, synthesis, and playback interruption.
No LLM client, framework adapter, or model-specific configuration is included.
The `langchain` directory and Agent names are retained for compatibility; the runtime no longer uses that framework.

## How it works

`on_user_message` validates the input, defines the story, and passes an asynchronous word generator to
`send_echo`. There is no command parser or model call; the input text does not change the story.

`send_echo` accepts `AsyncIterable[str]`, schedules cancellable work, and returns immediately.
The coordinator uses `async for` and sends each chunk as soon as it arrives; it does not collect
the source first. To integrate your own streaming logic, replace the local `stream_story` async
generator in `on_user_message`. Source cleanup runs on completion, cancellation, and send failure.
The response task emits `response.created`, thirty `response.output_text.delta` frames,
`response.output_text.done`, and `response.done`. The callback returns promptly so the SDK can
continue receiving `user.barge_in`, `response.cancelled`, `response.timeout`, and session events while
output is still in flight.

The protocol layer retains response/input-ID correlation, bounded active and terminal response
capacity, proactive admission, task cancellation, telemetry, and session cleanup.
`heard_text` updates are retained for known responses, including recent completed responses,
without keeping an LLM prompt or model conversation history.

## Prerequisites

1. Python 3.13 and uv.
2. For deployment: Azure Developer CLI (`azd`) 1.32.0 or later with
   `azure.ai.agents` 1.0.0-beta.13 or later.
3. For deployment: a Foundry project and permission to deploy Hosted and Voice agents.
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

The runtime pins `azure-ai-agentserver-invocations==1.3.0b1` and its compatible
`azure-ai-agentserver-core==2.3.0b2` from PyPI.

Before deploying the new declaration, verify the target Vienna/APIM and Voice Live rollout.
After deployment, verify readiness, spoken output, and `user.barge_in` interruption through the
Voice wrapper. Local WebSocket tests do not establish deployed routing or audio-path readiness.

## Option 1: Azure Developer CLI

Initialize this sample from the public manifest:

```bash
mkdir voice-live-bridge-langchain-python
cd voice-live-bridge-langchain-python
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/conversation_engine/langchain/azure.yaml
```

Provision the declared Foundry project when needed, then run or deploy the hosted agent:

```bash
azd provision
azd ai agent run
azd deploy
```

Unlike request/response agents, this agent expects Bridge Protocol WebSocket events. Use the local
smoke client below instead of `azd ai agent invoke`.

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

The Foundry Toolkit Agent Inspector does not generate Voice Live Bridge WebSocket events. This
sample therefore uses the protocol-aware smoke client instead of the standard Inspector flow.

From the sample source directory:

```bash
uv sync --frozen --python 3.13
```

Start the server directly; no `.env` file is needed:

```bash
uv run --frozen python main.py
```

The server listens on `PORT` or port `8088` and exposes `GET /readiness` and the
`/voice_conversation_engine` WebSocket route.

## Local protocol smoke test

The smoke test sends `Hello, Voice Live!` and verifies the story, all thirty word deltas,
and their response/item correlation:

```bash
uv run --frozen python scripts/smoke_test.py
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
directly to the hosted text agent. This target streams the story and handles session lifecycle events.
Voice configuration and the managed audio experience belong to the Voice wrapper and Voice Live.

## User messages

Every valid user message, including `/end` and Unicode text, triggers this same thirty-word story:

> Once a little rabbit found a lonely star. She carried it up the tallest hill, where friendly
> fireflies helped it shine again. That night, everyone dreamed of kindness and adventure.

There is no command parser. Each response sends thirty word deltas sharing one output item,
then the full story in `response.output_text.done`, followed by `response.done`.
Empty and oversized input still receive `response.none`.

## Test

Tests exercise the SDK WebSocket route with the thirty-word stream, session lifecycle, input validation,
and response telemetry. Gated asynchronous sources prove that the first chunk is sent before later
chunks exist, and cancellation/failure closes the source. No tests make cloud calls:

```bash
uv run --frozen python -m pytest -q
ruff check .
```

The sample's build, validation, and test commands are also listed in `sample.yaml`.
Local tests use an in-process WebSocket transport; they do not verify cloud permissions, hosting
capacity, or the managed audio path. No cloud resources have been changed by local validation.
After deployment, verify readiness and a spoken echo through the Voice wrapper.

## Design notes

- `voice_runtime.py` contains the SDK callbacks. The story and its word generator are directly in
  `on_user_message`; `send_echo` keeps cancellation and state management out of that simple path.
- `response_coordinator.py` owns interruptible response tasks and terminal message sequencing;
  `state.py` owns connection state and response/input-ID correlation.
- `user.barge_in` and `response.cancelled` synchronize caller-heard text and cancel pending output.
  `response.timeout` cancels work selected by response ID or input IDs.
- Playback state is bounded to 64 known responses with up to 8,000 characters of heard text each.
  Session termination clears it together with pending work.
- Response operations contain protocol bookkeeping, not `prompt` or `use_model` flags.
- Runtime dependencies are locked in `uv.lock`; OpenAI, LangChain, and LangGraph clients
  are not included. The SDK still requires telemetry instrumentation packages, some named OpenAI;
  these are transitive infrastructure dependencies, not model clients.
- The `dev` dependency group includes `httpx2` only for Starlette's local test client.
- Custom spans record identifiers, duration, and sanitized outcomes without text or credentials.

## Troubleshooting

- If the server rejects `session.start` with `protocol_mismatch`, ensure the event declares Bridge
  Protocol `1.0`. This is separate from the `voice_conversation_engine` transport version in `azure.yaml`.
- If the smoke test cannot connect, start `uv run --frozen python main.py` first and verify that port `8088` is
  available, or set the smoke client's URL to match `PORT`.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK on PyPI](https://pypi.org/project/azure-ai-agentserver-invocations/)
