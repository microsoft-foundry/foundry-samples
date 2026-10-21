<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Bridge — LangChain Python

## What this sample demonstrates

This sample gives a hosted text agent a managed voice experience without adding audio code to the
agent. It implements Voice Live Bridge Protocol `1.0` with typed callbacks from
`azure-ai-agentserver-invocations==1.1.0`. A LangChain agent calls a Microsoft Foundry model
through the Responses API, can invoke a local UTC-time tool, and streams only assistant text back
to Voice Live.

Voice Live owns audio input, speech recognition, turn detection, synthesis, playback interruption,
and proactive-response admission. This hosted agent receives text and control events on
`/invocations_ws`.

## How it works

```text
Caller audio
    → Foundry voice agent
    → Voice Live (STT, VAD, TTS, barge-in)
    → Bridge Protocol 1.0 over invocations_ws
    → this LangChain hosted text agent and tools
    → Foundry model Responses API
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
3. Azure Developer CLI (`azd`) 1.34.2 or later with the Foundry extension.
4. Azure CLI authentication for local model access.
5. A Foundry project and model deployment, or permission for `azd provision` to create them.

Install and authenticate the tools:

```bash
azd ext install microsoft.foundry
azd auth login
az login
```

## Option 1: Azure Developer CLI

Initialize this sample from the public manifest:

```bash
mkdir voice-live-bridge-langchain-python
cd voice-live-bridge-langchain-python
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voice-agent-target-agent/langchain/azure.yaml
```

Provision the declared Foundry project and model when needed, then run or deploy the hosted agent:

```bash
azd provision
azd ai agent run
azd deploy
```

Unlike request/response agents, this agent expects Bridge Protocol WebSocket events. Use the local
smoke client below instead of `azd ai agent invoke`.

### Deploy to an existing Foundry project

The `ai-project.deployments` block in `azure.yaml` is the default for provisioning a new project.
To reuse a project that already has a model deployment, create an `azd` environment in this sample
directory and identify the existing resources explicitly:

```bash
azd env new "<environment-name>"
azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
azd env set AZURE_LOCATION "<foundry-project-region>"
azd env set AZURE_AI_PROJECT_ID "<foundry-project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "<foundry-project-endpoint>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<existing-model-deployment-name>"
azd deploy
```

Copy the project resource ID, endpoint, and region from **Manage** > **Project details** in the
Foundry portal. The model deployment name must exactly match a deployment in that project.
`AZURE_AI_MODEL_DEPLOYMENT_NAME` configures the hosted agent runtime; it does not rename, replace,
or suppress the model declared under `ai-project.deployments`.

Do not run `azd provision` or `azd up` in this existing-project flow. Those commands apply the
fresh-project declaration and may attempt to create another `gpt-5.4-mini` deployment, consuming
additional quota. After `azd deploy`, ensure the new hosted-agent instance identity has
**Cognitive Services OpenAI User** (or an equivalent inherited model-inference role) on the parent
AI Services account before exercising model-backed Bridge turns.

## Option 2: Run locally

The Foundry Toolkit Agent Inspector does not generate Voice Live Bridge WebSocket events. This
sample therefore uses the protocol-aware smoke client instead of the standard Inspector flow.

From the sample source directory:

```bash
python -m pip install uv
uv sync --frozen
cp .env.example .env
```

Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`. For local Entra
authentication, set `AZURE_TOKEN_CREDENTIALS=AzureCliCredential`. An API key is supported for local
development, but hosted deployments should use the hosted agent's managed identity.

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

The smoke test sends `/help`, so it validates the Bridge wire flow without calling a model:

```bash
uv run --no-sync python scripts/smoke_test.py
```

Expected message sequence:

```text
session.ready
response.created
response.output_text.done
response.done
```

## Give the hosted agent a voice

The sample `azure.yaml` already declares a managed Voice wrapper agent that targets this hosted
agent. `azd deploy` deploys both the hosted target and the Voice wrapper; no manual JSON wrapper
creation is required for the main azd flow.

The caller connects to the Voice wrapper's Voice WebSocket endpoint and never sends Bridge messages
directly to the hosted text agent. Conversation logic, model calls, tools, and response generation
belong to the target hosted agent. Voice configuration and the managed audio experience belong to
the Voice wrapper and Voice Live.

## Sample commands

| User text | Behavior |
| --- | --- |
| Any text or `/stream text` | Stream a model response. |
| `/done text` | Send one completed output item. |
| `/voice text` | Send completed text with a `+10%` synthesis-rate patch. |
| `/none` | Decline the input with `response.none`. |
| `/proactive text` | Generate only after Voice Live sends `response.accepted`. |
| `/cancel text` | Open a response and request self-cancellation. |
| `/error` or `/session-error` | Emit a sanitized sample error. |
| `/end` or `/end-now` | End after queued audio drains or immediately. |
| `/help` | Return this command set without calling the model. |

## Test

Tests use deterministic fake model streams and make no cloud calls:

```bash
uv run --no-sync python -m pytest -q
uv run --no-sync ruff check .
```

From the repository root, run the standard per-sample validator:

```bash
bash .github/scripts/validate-sample.sh \
  --language python \
  --sample-dir samples/python/hosted-agents/bring-your-own/voice-agent-target-agent/langchain
```

## Design notes

- `voice_runtime.py` is the thin protocol callback and command-dispatch layer;
  `response_coordinator.py` owns response execution and terminal sequencing, while `state.py` owns
  connection state and its session store.
- `langchain_agent.py` uses `create_agent`, a streaming `ChatOpenAI` Responses model, and the
  `get_current_utc_time` tool. The runtime owns and closes the adapter exactly once.
- Responses are created with `store=false`; LangChain tool messages stay inside the model loop and
  are not emitted as caller-visible Bridge output.
- Conversation history is bounded and exists only for one physical agent connection.
- Barge-in reconciles assistant history to the text Voice Live reports as heard by the caller.
- Proactive output never starts before `response.accepted`.
- Custom spans contain identifiers, durations, and sanitized outcomes, but no prompt or response
  content.

## Troubleshooting

- If the server rejects `session.start` with `protocol_mismatch`, ensure the event declares Bridge
  Protocol `1.0`. This is separate from the `invocations_ws` transport version in `azure.yaml`.
- If model calls fail locally, verify `FOUNDRY_PROJECT_ENDPOINT`,
  `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and the active Azure CLI identity.
- If the smoke test cannot connect, start `uv run --no-sync python main.py` first and verify that port `8088` is
  available, or set the smoke client's URL to match `PORT`.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [AgentServer Invocations SDK on PyPI](https://pypi.org/project/azure-ai-agentserver-invocations/)