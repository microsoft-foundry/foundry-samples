<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Bridge — Basic Python (legacy echo test)

## What this sample demonstrates

This sample gives a hosted text agent a managed voice experience without adding audio code to the
agent. It implements Voice Live Bridge Protocol `1.0` with typed callbacks from
`azure-ai-agentserver-invocations==1.1.0` and echoes the latest input locally without a model call.
This test branch deliberately preserves the old SDK, protocol runtime, dependency lock, and
command parsing so the legacy path can be tested independently of the CE migration.

Voice Live owns audio input, speech recognition, turn detection, synthesis, playback interruption,
and proactive-response admission. This hosted agent receives text and control events on
`/invocations_ws`.

## How it works

```text
Caller audio
    → Foundry voice agent
    → Voice Live (STT, VAD, TTS, barge-in)
    → Bridge Protocol 1.0 over invocations_ws
    → this hosted text agent
    → local streaming echo backend
```

The application explicitly accepts `session.start`, sends `session.ready`, receives final
transcripts as `user.message`, and streams `response.output_text.delta` messages back to Voice
Live. The AgentServer Voice API is a typed relay; the application owns response IDs, tasks,
cancellation, bounded conversation history, and terminal-event correlation.

Protocol `1.0` in this sample supports text input, greeting context, streaming responses,
`response.none`, no-input turns, barge-in, response timeout, proactive responses, response
self-cancellation, errors, and call termination. It does not support DTMF, image input, app-driven
history mutation, or hosted-agent handoff.

## Prerequisites

1. Python 3.13 or later.
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later,
   installed and available on `PATH`.
3. Azure Developer CLI (`azd`) 1.27.1 or later with the Foundry extension.
4. For deployment only: a Foundry project, or permission for `azd provision` to create one.
   No model deployment, model credentials, or inference role is required by echo.

Install and authenticate the tools:

```bash
azd ext install microsoft.foundry
azd auth login
```

## Option 1: Azure Developer CLI

Initialize this sample from the public manifest:

```bash
mkdir voice-live-bridge-basic-python
cd voice-live-bridge-basic-python
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/wujin/test-legacy-voice-agent-target-basic/samples/python/hosted-agents/bring-your-own/voice-agent-target-agent/basic/azure.yaml
```

Provision the declared Foundry project when needed, then run or deploy the hosted agent.
The manifest does not declare or provision a model:

```bash
azd provision
azd ai agent run
azd deploy
```

Unlike request/response agents, this agent expects Bridge Protocol WebSocket events. Use the local
smoke client below instead of `azd ai agent invoke`.

### Deploy to an existing Foundry project

To reuse a project, create an `azd` environment in this sample directory and identify the
existing resources explicitly:

```bash
azd env new "<environment-name>"
azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
azd env set AZURE_LOCATION "<foundry-project-region>"
azd env set AZURE_AI_PROJECT_ID "<foundry-project-resource-id>"
azd deploy
```

Copy the project resource ID and region from **Manage** > **Project details** in the Foundry
portal. Use `azd deploy` rather than provisioning a fresh project in this existing-project flow.
Echo does not consume model quota. Hosted Agent and managed Voice wrapper deployment still
require the platform permissions, regional availability, and Voice Live resources they normally use.

## Option 2: Run locally

The Foundry Toolkit Agent Inspector does not generate Voice Live Bridge WebSocket events. This
sample therefore uses the protocol-aware smoke client instead of the standard Inspector flow.

From the sample source directory:

```bash
python -m pip install uv
uv sync --frozen
cp .env.example .env
```

No Azure login, Foundry endpoint, model name, or API key is needed to run echo locally.
The optional `.env` only configures logging and the listen port.

Load the environment and start the server:

```bash
set -a
source .env
set +a
uv run --no-sync python main.py
```

The server listens on `PORT` or port `8088` and exposes `GET /readiness` and the
`/invocations_ws` WebSocket route.

## Local protocol smoke test

The smoke test sends `Hello echo`, so it exercises the default echo path without cloud calls:

```bash
uv run --no-sync python scripts/smoke_test.py
```

Expected message sequence:

```text
session.ready
response.created
response.output_text.delta
response.output_text.done
response.done
```

The returned text is `Hello echo`. Override the input with `--text "your text"`.

## Give the hosted agent a voice

The sample `azure.yaml` already declares a managed Voice wrapper agent that targets this hosted
agent. `azd deploy` deploys both the hosted target and the Voice wrapper; no manual JSON wrapper
creation is required for the main azd flow.

The caller connects to the Voice wrapper's Voice WebSocket endpoint and never sends Bridge messages
directly to the hosted text agent. Echo response generation belongs to the target hosted agent.
Voice configuration and the managed audio experience belong to
the Voice wrapper and Voice Live.

## Sample commands

| User text | Behavior |
| --- | --- |
| Any text or `/stream text` | Stream back the parsed input in chunks of at most 40 characters. |
| `/done text` | Echo text as one completed output item. |
| `/voice text` | Echo completed text with a `+10%` synthesis-rate patch. |
| `/none` | Decline the input with `response.none`. |
| `/proactive text` | Echo only after Voice Live sends `response.accepted`. |
| `/cancel text` | Open a response and request self-cancellation. |
| `/error` or `/session-error` | Emit a sanitized sample error. |
| `/end` or `/end-now` | End after queued audio drains or immediately. |
| `/help` | Return this command set without calling the model. |

The old parser is unchanged: leading/trailing whitespace is stripped, and slash commands remain
commands rather than literal echo text. Echo uses only the latest parsed input, not earlier history.

## Test

Tests cover the default echo path plus existing deterministic injected backend streams and make
no cloud calls. The original model-adapter unit tests are retained for this historical test branch:

```bash
uv run --no-sync python -m pytest -q
uv run --no-sync ruff check .
```

From the repository root, run the standard per-sample validator:

```bash
bash .github/scripts/validate-sample.sh \
  --language python \
  --sample-dir samples/python/hosted-agents/bring-your-own/voice-agent-target-agent/basic
```

## Design notes

- The default entry point uses `EchoClient`, which owns no network resources or model credentials.
- `voice_runtime.py` is the thin protocol callback and command-dispatch layer;
  `response_coordinator.py` owns response execution and terminal sequencing, while `state.py` owns
  connection state and its session store.
- Echo implements the existing `model_contract.py` backend interface so scheduling, limits,
  interruption, history and cleanup stay on the original code path. `model_client.py` and its
  locked dependencies remain for historical comparison, but are not initialized by default.
- Conversation history is bounded and exists only for one physical agent connection.
- Barge-in reconciles assistant history to the text Voice Live reports as heard by the caller.
- Proactive output never starts before `response.accepted`.
- Custom spans contain identifiers, durations, and sanitized outcomes, but no prompt or response
  content.

## Troubleshooting

- If the server rejects `session.start` with `protocol_mismatch`, ensure the event declares Bridge
  Protocol `1.0`. This is separate from the `invocations_ws` transport version in `azure.yaml`.
- If startup requests model configuration, verify you are running the echo test branch's
  `main.py`, not the original model-backed version.
- If the smoke test cannot connect, start `uv run --no-sync python main.py` first and verify that port `8088` is
  available, or set the smoke client's URL to match `PORT`.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK on PyPI](https://pypi.org/project/azure-ai-agentserver-invocations/)
