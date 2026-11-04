<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->


# Foreground + background agents over Conversation Engine

## What this sample demonstrates

This is a transport-only migration of the
[original foreground/background Responses sample](../../voicelive/foreground-background-agents-responses-voicelive/).
One Hosted Agent process contains a foreground Router and an asynchronous background
Worker. Only its public entry point changes to `voice_conversation_engine:1.0.0`.
The directory suffix `-responses` records its source sample; it does not register a
Responses endpoint. Bridge message version remains `1.0`.

`router_agent.py`, `worker_agent.py`, and `task_store.py` are copied verbatim.
The model deployment declared in `azure.yaml`, model environment variables, model
access code, prompts, meta-tools, mock tools and worker loop remain the original's.
The new CE layer replaces the old HTTP/SSE host and its request context.

## How it works

The original handler still streams acknowledgment → waits for work → delivers results.
The Router makes a Chat Completions call with `tool_choice="required"` and selects
`respond_directly`, `start_task`, `check_task_status`, `cancel_task`, or
`get_task_result`. The Worker runs through `asyncio.create_task` and uses the model's
Responses API for up to five rounds of tool calling.

The domain tools are the original mocks, not real Work IQ or document-service
integrations. Each simulated tool call waits 6–12 seconds. Status updates keep the
original five-second interval and maximum of five updates.

The CE host schedules the handler as a response task and remains free to receive
control events. Its 40-character text chunks flow to Voice Live, which owns STT,
TTS and playback. The original handler's multiple text messages are separated by
blank lines within one CE output item. There is no loopback HTTP request, separate
Worker service, second Hosted protocol or proactive result-notification redesign.

### Interruption and state

- Barge-in, response cancellation or response timeout closes the current output,
  but does not cancel the Worker. A later user turn can deliver the saved result.
- An explicit `cancel_task` sets the original Worker's cooperative cancellation
  event. It does not forcibly interrupt an in-flight synchronous model/tool call.
- The CE context supplies the task store, worker handles and last 20 history items
  per connection, replacing the context/state previously provided by the HTTP host.
- `heard_text` replaces interrupted assistant output in subsequent model history.
- Session end, disconnect and server shutdown cancel the connection's tasks and
  discard its memory. There is no durable task queue or reconnect recovery.
- Original task delivery bookkeeping is retained; this sample does not promise
  exactly-once playback or delivery across interruptions/disconnection.

The CE layer retains input/response-ID correlation, duplicate-input tracking,
bounded response capacity, cancellation/timeouts, no-input handling and cleanup
from the basic CE sample. It does not await the handler in the receive callback.

Scheduled replies share a per-connection wire-generation gate: only one response
may be open, while additional accepted inputs wait in the bounded queue without
blocking control callbacks. A committed terminal send or winning inbound terminal
event releases this gate independently of slow producer cleanup. Cleanup remains
tracked and consumes task capacity until it finishes; self-cancel waits for its
winning terminal acknowledgment before replacement output.

## Prerequisites

1. Python 3.13 and uv 0.11.7 or later.
2. A Foundry project whose region supports the dedicated Hosted CE and Voice Live
   path. Local socket tests alone cannot establish that rollout.
3. A model deployment supporting both Chat Completions with function calling and
   the model Responses API. The manifest keeps the original `gpt-5.4-mini`
   deployment, version `2026-03-17`, GlobalStandard capacity 10.
4. The local development identity and deployed Hosted identity must have model
   inference access in that project. For example, grant the Hosted identity
   `Cognitive Services OpenAI User` on the Foundry resource serving the model;
   this covers Chat Completions and Responses. Deploying code does not establish
   those grants, and the developer's own access is not inherited by a new Agent.
   The identity assigning the role needs `Microsoft.Authorization/roleAssignments/write`.

| Variable | Required | Meaning |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Same project endpoint as the original; injected by Hosted Agent Service. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Same deployment-name setting as the original; select your project's deployment. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional | Same telemetry configuration as the original. |

Model access is unchanged: `DefaultAzureCredential` →
`AIProjectClient(endpoint=...)` → `get_openai_client()`. No additional model
endpoint, API key, Azure OpenAI client or Voice Live reasoning model is introduced.

The original Responses Server SDK pins an older Core range incompatible with the
CE SDK. Its HTTP event builder is therefore replaced by a small internal text-event
adapter. The model-facing `azure-ai-projects==2.0.1`, `azure-identity==1.25.3`,
`openai==2.54.0`, and `httpx==0.28.1` match the original sample's resolved versions.
Core `2.3.0b2` and Invocations `1.3.0b1` supply CE transport.

Follow the shared [Python startup configuration](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/README.md#python-startup-configuration).

## Option 1: Azure Developer CLI

Install azd 1.32.0+ and the Foundry extension, then authenticate:

```bash
azd ext install microsoft.foundry
azd auth login
az login
```

From this sample directory, initialize from the local manifest:

```bash
azd ai agent init -m azure.yaml
# Provision only when creating the manifest's project/model resources:
azd provision
azd ai agent run
```

To target an existing project/model, use the same `-p <project-id> -d <deployment-name>`
options as the original sample; avoid provisioning a duplicate model deployment.

In another terminal:

```bash
cd src/foreground-background-agents-ce
uv sync --frozen --python 3.13
uv run --frozen python scripts/smoke_test.py \
  --message "Search site specs for Quincy North. Include the fiber types and cross-connect rack location." \
  --expect OS2
```

Deploy the Hosted Agent and managed Voice wrapper with:

```bash
azd deploy
```

After deploying, read back the Hosted Agent's managed-identity principal and verify
its model-inference grant before the first live call. If manual code-ZIP deployment
or your deployment tooling did not configure the grant, have the resource's IAM
administrator assign it. Keep the scope to the intended Foundry resource and the
specific Hosted identity; do not broaden access to the subscription.

The wrapper `foreground-background-agents-ce-voice` targets the CE Hosted Agent.
Use a Foundry Voice client for the wrapper's `voice` protocol endpoint. Standard
`azd ai agent invoke` and Agent Inspector do not generate CE WebSocket events and
are not suitable for this sample.

Neither `voiceLiveCompatible` nor `bridgeProtocolVersion` metadata is required.

## Manual local run

From `src/foreground-background-agents-ce`:

```bash
uv sync --frozen --python 3.13
cp .env.example .env
# Edit .env to select your actual project and model deployment.
set -a
source .env
set +a
uv run --frozen python main.py
```

Run the protocol client above in another terminal. Its `--uri` argument is only
the test client's connection address, not a Router or Worker parameter.

## Validation

From the sample root, use `sample.yaml` for build readiness. Equivalent runtime checks:

```bash
cd src/foreground-background-agents-ce
uv sync --frozen --python 3.13
uv run --frozen python -m compileall -q .
uv run --frozen python -m ruff check .
uv run --frozen python -m pytest -q
```

Local tests use inert project/model values and replace only model/worker calls.
They exercise real SDK CE WebSocket encoding and dispatch, streaming, interruption
without worker cancellation, explicit cancellation, timeout, session isolation,
heard-text history, duplicate inputs and cleanup. They do not prove cloud model
permissions or audio-path readiness.

The behavior contract is at
`.azure-pipelines/hosted-agent-tests/python/bring-your-own/conversation_engine/foreground-background-agents-responses/test-spec.yml`.
The shared HTTP CI runner cannot invoke CE. The central deployment skiplist excludes
this sample from that runner, not from its build-readiness/unit checks.
Schema validation and `--protocol invocations` planning validate only its raw-evidence
assertion shape; a separate CE/Voice client must collect actual evidence.

On November 2, 2026, build readiness and all 18 local tests passed. The same code
ZIP then passed two deployed business turns in a CE-enabled `westus2` project:

- Text input exercised the original Router, real model Responses/tool loop and
  unchanged mock tools; the spoken result included the expected OS2 fiber and Rack 7.
- WAV input exercised STT, a foreground model reply and nonempty output audio.

Both responses completed, and Hosted session readback verified the exact new
Agent version. The test-owned Hosted session was deleted and read back as 404;
Agent versions and their scoped model-inference grant were retained.
The project's existing `gpt-5.4-mini-1` deployment was selected
through the original model-deployment environment variable. The new Hosted
identity's resource-scoped inference role was explicitly granted and read back
before testing. Model code, source defaults, prompts and tools were unchanged.

This used the SDK code-ZIP deployment route, not azd/Toolkit onboarding. It is a
minimal two-turn live smoke, not cloud interruption/reconnect/failure-injection,
load testing, or validation of real Work IQ/document backends. Local fake-model
tests remain separate from this live model and Voice Live result.

## Troubleshooting

- Missing model environment variables: use the same two settings as the original.
- Model 403/404 or unsupported endpoint: verify the selected deployment supports
  both APIs and the calling identity has access. Do not substitute a Voice Live
  model or disable authentication.
- CE 404 or startup error: check regional CE rollout and matching SDK/manifest
  protocol; do not fall back to deprecated Bridge metadata.
- No backend tool integration: the tools are intentionally the original mock implementations.
- Long-running job lost on disconnect: the sample's state is in memory; durable
  background execution is outside this transport-only migration.

## Next steps

- [Original Responses sample](../../voicelive/foreground-background-agents-responses-voicelive/)
- [Basic CE sample](../basic/)
- [In-process invocation adapter](../adapter_mode/)
