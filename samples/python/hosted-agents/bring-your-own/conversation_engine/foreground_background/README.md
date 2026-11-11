<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->


# Foreground + Background Conversation Engine

## What this sample demonstrates

This is a CE variant of the model-backed foreground/background VoiceLive sample, hosted on the
dedicated `voice_conversation_engine:1.0.0` protocol. The
[original Responses sample](../../voicelive/foreground-background-agents-responses-voicelive/)
remains unchanged at its original path. This CE variant does not expose a Responses HTTP endpoint.
The Router still uses Chat Completions, and the Worker still uses the model's Responses API;
those upstream model APIs are independent of the Hosted Agent ingress protocol.

The foreground Router makes one asynchronous model request and selects one of
`respond_directly`, `start_task`, `check_task_status`, `cancel_task`, or `get_task_result`.
The background Worker retains the five-round tool loop and the four original domain tools:
`search_site_specs`, `search_work_iq`, `get_repair_procedure`, and `analyze_document`.
These tools return mock data and simulate 6–12 seconds of service latency. They do not connect
to real Work IQ, document-processing, or procedural-memory services.
Only one business Worker runs per connection. While it is busy, another `start_task` request
is explicitly declined, not queued or acknowledged as started; retry after the current work ends.
Worker model continuations preserve all returned output items, including encrypted reasoning,
in their original order before appending tool results.

Voice Live owns speech recognition, turn detection, synthesis, and playback. The hosted
conversation engine handles text and control events. Router latency depends on the model;
there is no guaranteed two-second response time.

## How it works

- `main.py` creates the clients and starts the typed AgentServer Voice host.
- `agent_logic.py` retains Router dispatch, acknowledgments, periodic status messages, and Worker
  result delivery. Optional status requests have a one-second deadline and run at most five times.
- `router_agent.py`, `worker_agent.py`, and `task_store.py` contain the original business tools.
  Router calls disable parallel tool calls and validate exactly one returned call.
- `conversation_runtime.py` connects that workflow to the native CE runtime. It records only
  successfully sent text, reconciles caller-heard text, and owns connection-scoped business state.
- `voice_runtime.py`, `response_coordinator.py`, `state.py`, and `response_telemetry.py` reuse the
  existing Basic CE lifecycle. The local runtime's user-message hook delegates to the Router/Worker
  subclass, rather than producing the Basic sample's story. There are no sibling-path imports.

The manifest declares only `voice_conversation_engine:1.0.0`. The WebSocket route is
`/voice_conversation_engine`; the message handshake remains Bridge Protocol `1.0`.
Neither `voiceLiveCompatible` nor `bridgeProtocolVersion` metadata is required.
The SDK retains its independent `/invocations_ws` compatibility route, but the manifest does not
declare it. The sample accepts text only; application-data input is declined explicitly.

### Interruption, history, and tasks

Response generation runs outside receive callbacks, so the SDK can process `user.barge_in`,
`response.cancelled`, `response.timeout`, and `session.end` while model work is pending.
Response/input correlation, output budgets, duplicate-input rejection, and terminal sequencing
come from the existing CE coordinator.

Tasks and the last 20 history entries belong to one physical connection, not a process-wide
store. History advances after successful text sends; `heard_text` updates replace an interrupted
assistant entry before a later Router request uses it. Queued turns build history when they
actually start, not when they are enqueued.
Caller-heard prefixes use the existing 512 KiB UTF-8 response budget, not the user-input
character limit. History and playback state use the same bounded prefix; over-budget values
are cut only at complete Unicode characters. This does not expand the model-history budget.
Router requests and new Workers share a recent-history snapshot capped at 16,000 content
characters. Oldest entries are dropped whole until the remaining chronological suffix fits;
individual entries are never clipped and the recorded history is unchanged. Current input and
system instructions are retained separately; task context has its own 8,000-character budget.
These are character limits, not model-token estimates or a guarantee for every deployment's
context window. Worker tool-round continuation is separate from this initial-history budget.
Playback corrections for entries already outside that history window do not reinsert old speech
as the newest reply. A correction can add a missing entry only during its first text send.
The first two no-input reminders use the same recorder, including their non-streaming
`response.output_text.done` text and caller-heard corrections. Streamed text is not counted twice.

Barge-in or a response timeout stops foreground speech/waiting without cancelling the business
Worker. Its result can be delivered by a later turn on the same connection. Session end,
disconnect, or the third no-input event requests cooperative Worker cancellation before terminal
transport I/O. It does not block the SDK receive callback waiting for a synchronous model/tool
call. Shutdown retains and joins Workers before closing clients; an already-running call must
settle first. Model requests use a 30-second timeout without automatic retries.
Cancellation is checked when queued model/tool calls actually start; calls already executing
are still drained cooperatively.
The Worker makes at most five model calls. If the fifth call still requires tools rather than
providing a final answer, it records a sanitized failure, not a successful placeholder result.
Failed/incomplete API responses, structured model refusals, and empty or whitespace-only final
answers also remain unsuccessful. A real final answer returned by an already-running call can
still be saved after cooperative cancellation; refusals and blank answers cannot.

Completed results are marked `DELIVERED` only after a successful CE `response.done` send.
The Router identifies paraphrased/translated results explicitly through required
`delivered_task_ids` (an empty array for unrelated chat). Invalid or missing IDs fail the turn
before speech rather than silently losing delivery bookkeeping. Nonempty delivery IDs also
require a nonblank spoken message before the turn can claim any results.
Delivery claims are checked against complete result bodies included in that Router request,
not the task store after model I/O. Results that finish during routing remain available through
the direct result/status or automatic Worker-result output paths. Index-only results require
`get_task_result`; their IDs alone cannot authorize a delivery claim, even when history remains.
Direct result/status paths also track the task ID. Text-substring matching is not used.
Retained `COMPLETED` and `DELIVERED` IDs are both valid for repetition or translation;
replaying a delivered result does not reset or repeat its delivery-state transition.
This is transport-level delivery, not proof that all audio was heard. Playback corrections still
update history. Failure messages sent to the caller and Router context are sanitized.

Task retention is deliberately small: at most 16 tasks per connection, with queries and final
results limited to 8,000 characters each. An oversized query is rejected before task admission;
an oversized Worker result fails instead of being silently truncated or retained. At each Router
turn/task admission, terminal tasks (including undelivered results) older than five minutes
after completion are removed. Capacity eviction removes the oldest terminal outcome, never an
active Worker. Expired/evicted lookups explicitly report that the result is unavailable; `latest`
does not silently select an older task, and eviction never marks a result delivered.
The Router's task-context block is capped at 8,000 characters. Delivered results are included
in full, without an unmarked preview, even after their speech leaves history. If results do not fit, it
receives a compact task index and must use `get_task_result` for a full retained result rather
than treat a clipped answer as complete. These are local limits and existing on-access cleanup,
not a background cleanup service or a promise to retain every result for the entire call.

State is in memory and is not restored across a disconnected/reconnected socket, host restart,
or replacement container. Use an application-owned durable store if that is required.
The sample does not promise arbitrary cancellation-resistant producer or finalizer support;
its business stream uses cancellable asynchronous calls and ordinary synchronous bookkeeping.

## Prerequisites

- Python 3.13 or later and [uv](https://docs.astral.sh/uv/) 0.11.7 or later.
- Azure Developer CLI and Foundry extension versions meeting `azure.yaml`'s `requiredVersions`.
- A Foundry project and model deployment, or permission to provision the declared
  `gpt-5.4-mini` deployment.
- A signed-in local Azure CLI identity for model-backed tests, or the Hosted Agent's managed
  identity after deployment. The identity needs appropriate Foundry/model-inference access.
- For deployment, matching Hosted Agent ingress and Voice Live support for
  `voice_conversation_engine:1.0.0`. A successful local SDK test does not establish that rollout.

The model deployment, CPU/memory settings, and runtime directory name are retained from the
original sample. The CE manifest uses the distinct Hosted Agent name
`foreground-background-agents-ce` and Voice wrapper name `foreground-background-agents-ce-voice`,
so deploying it in the same project does not replace the original Responses Agent.
The wrapper's `conversationEngine` references the CE Agent. No cloud resource is created by
checking out this sample.

## Option 1: Azure Developer CLI

Initialize from a fresh directory, not from a directory already containing `azure.yaml`:

```bash
mkdir foreground-background-ce
cd foreground-background-ce
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/conversation_engine/foreground_background/azure.yaml
azd auth login
az login
azd provision
azd ai agent run
```

The public manifest URL is available after this CE variant is merged. Before then, use the local
manifest's absolute path from a fresh directory. To reuse an existing project/model, configure
that azd environment for those existing resources and do not run `azd provision` or `azd up`.

After local protocol validation, `azd deploy` deploys the Hosted Agent and its Voice wrapper.
Callers connect to the Voice wrapper's normal Voice WebSocket, not to the internal CE agent leg.

`azd ai agent invoke` and Agent Inspector do not produce CE messages. Use the dedicated
WebSocket smoke client below. No separate adapter Agent, loopback HTTP request, or OpenAI API key
is required; the model clients authenticate to the configured Foundry project.

## Option 2: Run locally

From the sample directory:

```bash
cd src/foreground-background-agents-voicelive
uv sync --frozen
cp .env.example .env
```

Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`.
The endpoint is the HTTPS project URL ending in `/api/projects/<project>`.
`APPLICATIONINSIGHTS_CONNECTION_STRING` is optional locally and normally injected when hosted.
The module can be imported without model configuration; configuration is read when starting it.

```bash
az login
set -a
source .env
set +a
uv run --no-sync python main.py
```

The server exposes `GET /readiness` and the CE WebSocket on port 8088 (or `PORT`).
The retained Dockerfile uses Python 3.13 and the same frozen dependency graph as direct deployment.

In a second terminal, from the runtime directory:

```bash
uv run --no-sync python scripts/smoke_test.py --text "Hello!"
uv run --no-sync python scripts/smoke_test.py --text "Find the Quincy North fiber specifications."
```

Unlike the other CE samples' story/Echo tests, this smoke calls the real Router/model and can
invoke mock Worker tools. It requires valid model access and may take multiple tool rounds.
Expected response order is `session.ready → response.created → response.output_text.delta*
→ response.output_text.done → response.done`, with correlated IDs. No audio is tested here.

## Tests

Tests use fake model clients and zero-latency tool doubles; they do not need credentials or
provision Azure resources. They exercise the real SDK CE dispatcher and the real Worker loop.

```bash
uv sync --frozen
uv run --no-sync python -m pytest -q
uv run --no-sync ruff check .
uv run --no-sync python -m compileall -q -x '[.]venv' .
uv lock --check
```

`sample.yaml` declares the same build-readiness commands. The public behavior contract is at
`.azure-pipelines/hosted-agent-tests/python/bring-your-own/conversation_engine/foreground_background/test-spec.yml`.
The shared HTTP cloud runner cannot invoke CE; this path is listed with the other CE samples in
the deployment skiplist. Build-readiness and unit tests are not skipped. Use a dedicated CE/Voice
client for cloud validation.

No live model or managed-audio deployment validation is implied by these unit tests.
Before rollout, verify platform CE support, provision or reuse the model, grant model access,
deploy the Hosted Agent and Voice wrapper, and test real audio plus interruption.
