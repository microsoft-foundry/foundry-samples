<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Hosted Agent — Adapter Mode (Python)

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

`azure.yaml` registers `kind: hosted`, Python 3.13 and `main.py` as the entry point.
`main.py` starts the long-running AgentServer host; the adapter invokes `echo_agent.py`
in process and streams the Echo reply back over CE. This is the application that
runs locally and after deployment.

`scripts/smoke_test.py` is only an optional client for checking a running Agent.
It is not the Hosted Agent entry point and is never executed by deployment.

## How it works

`echo_agent.py` contains a plain `handle_invocation(Request) -> StreamingResponse` function.
`main.py` injects that function into the adapter. The handler returns incremental SSE;
it never imports Voice callbacks or allocates Bridge response IDs.

Echo returns the input verbatim in word-sized chunks, preserving leading/trailing
whitespace and Unicode. Slash-prefixed input is ordinary text, not a command.
JSON objects are returned verbatim as non-audio application data.
There is no model, tool, business-history store or external backend dependency.

The internal request is `{"input":"Hello world"}`. The handler's SSE profile is:

```text
data: {"type":"token","content":"Hello"}

data: {"type":"token","content":" world"}

data: {"type":"done","full_text":"Hello world"}

```

The sample-maintained `adapter/` directory owns SDK callbacks, response/input
correlation, bounded capacity, asynchronous scheduling, interruption, cancellation,
timeout handling, heard-text bookkeeping, telemetry and cleanup. The adapter
reads the original `StreamingResponse.body_iterator` directly and closes it on
cancellation or send failure; response background cleanup finishes before success.
Body-iterator setup is inside this cleanup boundary: a setup failure still attempts
body closure and response background cleanup while preserving the original failure.

SSE is parsed incrementally, independently of handler write boundaries. Valid UTF-8,
one optional leading BOM, LF/CRLF/CR line endings and multiline `data:` are supported.
Content-Type uses the exact `text/event-stream` token, case-insensitively; parameters
are allowed. Comments and unknown SSE fields are ignored. Parsing yields control
even for already-ready comment-only or empty chunks. EOF does not supply a missing
event delimiter: truncated data events fail, while a trailing comment is allowed.

Each event is limited to 512 KiB of UTF-8, counting line endings as LF and excluding
the optional stream BOM. This separate framing budget accommodates JSON escaping
and event envelopes; it is not a limit on a handler's write size. Input and total
text output are limited to 8,000 Unicode scalar values. Application data is limited
to 65,536 aggregate bytes of compact UTF-8 JSON (without ASCII escaping or optional
spaces); the SSE envelope is not part of that data budget. Non-finite JSON numbers
are rejected. `done.full_text` must match accumulated tokens.
The adapter still drains the handler after `done`: later errors or final-save
failures cannot become a successful `response.done`. Malformed/truncated SSE,
HTTP errors and missing/duplicate completion fail rather than silently succeeding.
Text items are completed before the next data item; response completion waits for handler finalization.

## Cancellation and cleanup contract

An invocation with neither nonempty text nor an application JSON item fails rather
than sending a successful empty response. Whitespace-only text and JSON-only output
remain valid. The 8,000-character text budget does not impose a new 4,096-event SSE
limit; valid token coalescing/fragmentation remains independent of handler writes.

Each connection opens at most one wire generation at a time. Input decisions
remain in receive order; up to eight resource-owning responses can be active or
queued, with eight additional bounded decline/cancellation operations. Excess
backlog ends the session rather than silently dropping an unresolved input.

Barge-in, cancellation, timeout or session termination stops further output for
that response. A cleanup exception after that decision is a local diagnostic,
not another response terminal. A producer's own cancellation without a protocol
stop is a generation failure. Already-started transport writes cannot be retracted;
Voice Live owns arbitration of frames already in flight.

Stopping generation and releasing resource ownership are separate: cleanup stays
tracked and occupies capacity until it settles. Session-end/disconnect callbacks
signal cancellation without joining producers in receive dispatch; host shutdown
(or .NET handler-scope disposal) joins the retained work. Cancelling a Python
shutdown join does not cancel the retained cleanup, and a later `close()` rejoins it.

Sources must cooperate with cancellation, bound upstream I/O and close their
nested resources. Ordinary asynchronous `finally`, `aclose()`/`DisposeAsync()`
and response background cleanup are supported and awaited before success.
They are **not guaranteed cancellation-proof**: in particular, cancellation can
interrupt an async finalizer that the source has already entered naturally.
Resource owners must make critical finalization cancellation-safe themselves.
An accepted source remains the cleanup target if its `__aiter__()` fails; successful
setup transfers closure to the returned iterator. The runtime attempts closure
and does not issue repeated cancellation
while its explicit Python close is draining, but cannot restart an already-aborted
finalizer or guarantee finite shutdown for non-cooperative I/O. There is no
producer-pump task, forced thread termination or business-state rollback.

## Prerequisites

1. Python 3.13 and uv. Runtime dependencies are fully pinned in `uv.lock`, including public
   `azure-ai-agentserver-invocations==1.3.0b1` and Core `2.3.0b2`.
2. For deployment: azd 1.32.0+ with `azure.ai.agents` 1.0.0-beta.13+,
   a Foundry project and permissions to deploy Hosted and Voice agents.
3. The target environment must support dedicated Vienna/APIM CE routing and
   CE-aware Voice Live. Public SDK publication is not proof of regional rollout.

Local tests require no Azure credentials, model configuration, Cosmos, indexes,
RBAC changes or network setup. Deployment still needs the ordinary hosting and
regional speech capacity. No Bridge metadata or external CE Connection is needed.

## Option 1: Deploy with Azure Developer CLI

Initialize from the public sample after it is merged and synchronized:

Use a new empty directory containing no `azure.yaml`; do not run initialization
inside the checked-out sample directory. Run the subsequent `azd` commands from
that initialized project directory.

```bash
mkdir voice-live-adapter-python
cd voice-live-adapter-python
azd ext install microsoft.foundry
azd auth login
az login
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/conversation_engine/adapter_mode/azure.yaml
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

From `src/voice-live-adapter-python`:

```bash
uv sync --frozen --python 3.13
uv run --frozen python main.py
```

The SDK listens on `PORT` or `8088` and exposes `GET /readiness`.
The sample uses `/voice_conversation_engine`; SDK-retained compatibility routes
are not additional protocol declarations or an HTTP registration of the Echo handler.

### Optional protocol check

Keep the Hosted Agent running. In another terminal, install the development tools
and run the separate validation client:

```bash
uv sync --frozen --python 3.13
uv run --frozen python scripts/smoke_test.py --text "Hello,  世界 👋"
```

Expected sequence: `session.ready`, `response.created`, one or more
`response.output_text.delta` frames, `response.output_text.done`, `response.done`.
Completed and streamed text must exactly equal the supplied input.

## Test

```bash
uv sync --frozen --python 3.13
uv run --frozen python -m pytest -q
uv run --frozen python -m ruff check .
```

Tests cover Echo, first-chunk streaming, malformed SSE, cancellation and producer
disposal, finalization failures, bounded output, ID correlation, deadlines and
late `heard_text`. Tests do not make cloud calls. The shared cloud runner cannot
invoke CE; the central `hosted-agent-samples-ci-skiplist` records this deployment
limitation, not a passing cloud test. Build-readiness checks and unit tests still run.
The public test spec at
`.azure-pipelines/hosted-agent-tests/python/bring-your-own/conversation_engine/adapter_mode/test-spec.yml`
and its Invocations-compatible raw-evidence plan are fixture validation only,
not support for invoking this CE-only Agent through HTTP.

## Customization and boundaries

### JSON passthrough

The caller sends a JSON object through the Voice wrapper:

```json
{"type":"response.create","response":{"invoke_input":{"customer_id":"demo","locale":"zh-CN"}}}
```

The adapter receives `input_data` and calls the same Echo function in process with
`{"input":{"customer_id":"demo","locale":"zh-CN"}}`. The handler emits:

```text
data: {"type":"data","data":{"customer_id":"demo","locale":"zh-CN"}}

data: {"type":"done","full_text":""}

```

The adapter sends `response.output_data.done`, preserving the complete application
object, then `response.done` after cleanup. Voice Live exposes the object as
`response.invocation.delta.delta` without text or audio. The target Voice Live
deployment must support the application-data extension.

With the Agent running, check its CE leg locally:

```bash
uv run --frozen python scripts/smoke_test.py --data '{"customer_id":"demo","locale":"zh-CN"}'
```

Replace the Echo handler and, if its event schema differs, the mapping in
`adapter/invocation.py`. Keep the protocol runtime unchanged.
This adapter supports the illustrated token/data/done SSE profile, not arbitrary
HTTP middleware, HTTP LROs or automatic business-state recovery.

The handler must cooperate with cancellation and release its nested generators,
model/tool requests and resources in its own finalization. The adapter does not
shield arbitrary asynchronous producer finalizers from cancellation; resource-owning
replacements must make their cleanup cancellation-safe and bound their upstream I/O.
Cancelling output
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
