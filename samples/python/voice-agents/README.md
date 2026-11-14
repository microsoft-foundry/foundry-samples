---
page_type: sample
languages:
- python
products:
- ai-services
- azure
description: Use azure-ai-projects 2.11.0 for Voice Agent management, Realtime, GPT Live, tools, subagents, and telephony.
---

# 🎙️ Microsoft Foundry Voice Agents — Python Samples

These samples use [`azure-ai-projects[voice]==2.11.0`](https://pypi.org/project/azure-ai-projects/2.11.0/)
to create Voice Agents and exchange text, audio, images, and tool results.

Voice agents are exposed through `project_client.agents` with `kind="voice"` — the same management
surface (create, version, list, delete) used for prompt, workflow, hosted, and external agents.

| API | Status in 2.11.0 |
| --- | --- |
| `agents.create_from_prompt()`, `voice_agents.realtime`, `voice_agents.conversations`, Teams/Twilio telephony | Generally available; no preview opt-in. |
| GPT Live definitions, inline handoff, SIP | Preview; the relevant samples use `allow_preview=True`. |
| `beta.voice_agents.live`, `beta.voice_agents.live_conversations`, outbound campaigns under `beta.voice_agents.telephony` | Preview; beta operations supply their preview header. |

Realtime and Native GPT Live use different events and storage APIs. Do not mix their protocols.

## Prerequisites

- **Python 3.10+**
- A **Microsoft Foundry project** — see the [Overview page](https://ai.azure.com/) of your project
  for its endpoint.
- A supported **Realtime model** (default `gpt-realtime`). Self-deployed examples need an
  existing deployment. Native GPT Live needs a GPT Live deployment and, where listed, a chat backend.
- **Azure CLI**, logged in (`az login`) — the samples authenticate with `DefaultAzureCredential`.
- Optional: **[PyAudio](https://pypi.org/project/PyAudio/)** for speaker playback in the typed
  Realtime samples; the microphone sample requires it. Other examples need no audio hardware.

## Setup

1. **Create a virtual environment** (recommended)

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   Optionally, install PyAudio too (see [Prerequisites](#prerequisites)):

   ```bash
   pip install pyaudio
   ```

3. **Create your `.env` file**

   ```bash
   # PowerShell
   Copy-Item .env.sample .env
   # macOS/Linux: cp .env.sample .env
   ```

   Edit `.env` with your own values. At minimum, set `FOUNDRY_PROJECT_ENDPOINT`.

## Samples

### Agent lifecycle and management

| Sample | Description |
| --- | --- |
| [`voice_agent_basic.py`](voice_agent_basic.py) | Create, retrieve, list, update, disable/enable, and delete a voice agent (sync client). |
| [`voice_agent_basic_async.py`](voice_agent_basic_async.py) | Create, retrieve, list, and delete with the async client. |
| [`voice_agent_generate.py`](voice_agent_generate.py) | Generate a starter definition with GA `agents.create_from_prompt()`. |
| [`voice_agent_versions.py`](voice_agent_versions.py) | Publish, list, and retrieve immutable versions; opt into `DraftAgents=V1Preview` for a draft. |
| [`voice_agent_with_tools.py`](voice_agent_with_tools.py) | Configure audio/VAD/transcription and function/system tools; optionally attach your MCP server or existing toolbox, or use BYOM. |
| [`voice_agent_subagents.py`](voice_agent_subagents.py) | Consult a same-project prompt agent; set `FOUNDRY_VOICE_SUBAGENT_MODEL` to a chat deployment. |
| [`voice_agent_inline_handoff.py`](voice_agent_inline_handoff.py) | Route to an inline billing specialist and verify correlated handoff events (preview). |
| [`voice_agent_structured_inputs.py`](voice_agent_structured_inputs.py) | Supply connection-time customer/department values and verify the personalized greeting and answer. |

### Realtime conversations

| Sample | Description |
| --- | --- |
| [`voice_agent_realtime_text_conversation.py`](voice_agent_realtime_text_conversation.py) | Interactive, typed, multi-turn realtime conversation (sync). Replies stream back as audio + transcript and play through speakers if PyAudio is installed. |
| [`voice_agent_realtime_text_conversation_async.py`](voice_agent_realtime_text_conversation_async.py) | The same typed conversation using the async client. |
| [`voice_agent_realtime_audio_conversation_async.py`](voice_agent_realtime_audio_conversation_async.py) | Microphone conversation with barge-in, or device-free WAV input/output using `--audio-file` and `--output-audio`. |
| [`voice_agent_realtime_image_conversation.py`](voice_agent_realtime_image_conversation.py) | Send one text-and-image turn to an existing voice agent and validate the response lifecycle. |
| [`voice_agent_realtime_function_tool.py`](voice_agent_realtime_function_tool.py) | Handle a client-executed `function` tool call during a live realtime session. |
| [`voice_agent_realtime_interruption.py`](voice_agent_realtime_interruption.py) | Cancel a response and confirm truncation of unheard audio, without speakers. |
| [`voice_agent_realtime_session.py`](voice_agent_realtime_session.py) | Update session settings and create an out-of-band response without adding conversation history. |
| [`voice_agent_realtime_mcp.py`](voice_agent_realtime_mcp.py) | Wait for the MCP catalog, invoke a read-only tool, and explicitly approve or reject execution. Defaults to public Microsoft Learn search. |
| [`voice_agent_toolbox.py`](voice_agent_toolbox.py) | Create a temporary version-pinned toolbox, invoke its MCP tool, and delete the owned resources. |
| [`voice_agent_audio_settings.py`](voice_agent_audio_settings.py) | WAV-based recipes for semantic VAD, noise/echo processing, transcription hints, Custom Speech, and interim speech. |
| [`voice_agent_avatar.py`](voice_agent_avatar.py) | Save actual encoded avatar video or viseme/blendshape animation; require requested media events rather than just successful signaling. |

Device-free audio examples:

```bash
python voice_agent_realtime_audio_conversation_async.py --audio-file question.wav --output-audio reply.wav
python voice_agent_audio_settings.py --recipe semantic-vad --audio-file question.wav --output-audio vad-reply.wav
```

WAV input is uncompressed PCM16, mono, 24 kHz. Keep output paths new. Hardware mode requires
PyAudio; file mode does not open a microphone or speakers.

### Reading persisted conversations

| Sample | Description |
| --- | --- |
| [`voice_agent_read_conversation.py`](voice_agent_read_conversation.py) | Read a persisted conversation back: its envelope, responses, and ordered transcript items. |
| [`voice_agent_read_conversation_audio.py`](voice_agent_read_conversation_audio.py) | Read persisted conversation audio: the merged whole-call recording and a single item's audio segment. |
| [`voice_agent_conversations.py`](voice_agent_conversations.py) | Discover/list/get Realtime or Live conversations; deletion requires an exact ID, `--delete`, and a matching confirmation ID. |

Stored Realtime items are open-union mappings. Use mapping access so unknown service-generated
item kinds remain readable. Recordings require `store=True` and a finalized conversation.
Realtime and Live BYOS readers
download from the metadata-selected customer blob using your Azure identity, which needs
Storage Blob Data Reader or equivalent. They reject credential-bearing URLs and never fall
back to another storage route after a download failure.

### Native GPT Live (preview)

Set `FOUNDRY_VOICE_LIVE_MODEL` to an existing GPT Live deployment. Live waits for service-owned
`session.started`, never sends `session.start`, and confirms `session.closed` before cleanup.

| Sample | Description |
| --- | --- |
| [`voice_agent_live_text.py`](voice_agent_live_text.py) | Session updates, appended instructions, and two-turn Responses continuation; `--function-tool` runs a local demo tool. Requires `FOUNDRY_MODEL_NAME`. |
| [`voice_agent_live_audio.py`](voice_agent_live_audio.py) | Stream a spoken PCM16 mono 24-kHz WAV and save reply audio. `--store` also reads back and deletes this run's stored conversation. |
| [`voice_agent_live_delegation.py`](voice_agent_live_delegation.py) | Return correlated client commentary; `--managed` delegates to an owned, version-pinned prompt agent using `FOUNDRY_MODEL_NAME`. |
| [`voice_agent_live_readback.py`](voice_agent_live_readback.py) | Read an existing Live transcript, merged recording, and first speech item's audio without changing the existing agent/conversation. |
| [`voice_agent_live_controls.py`](voice_agent_live_controls.py) | Verify input mute/unmute and unspoken demo context. `--transcript-triggers` additionally requests service-dependent transcript Decisions. |

Audio/delegation examples require `FOUNDRY_VOICE_AUDIO_INPUT_PATH`. Their bounded capture window
does **not** prove speech completion; backend `response.completed` is a separate signal.
The [existing GPT Live application](gpt-live/README.md) is a separate azd-managed example with
its own dependencies, not part of this direct SDK collection.

### Telephony

These examples require your existing provider connections, routing, authorized numbers, and
recipient consent. They send **no requests by default**; use their explicit opt-in flags.

| Sample | Description |
| --- | --- |
| [`voice_agent_telephony_call_job.py`](voice_agent_telephony_call_job.py) | Create/poll/list/cancel an outbound job with `--provider ... --place-call`. Calls may start immediately and incur charges. |
| [`voice_agent_campaign.py`](voice_agent_campaign.py) | Schedule one preview campaign with `--provider ... --schedule-campaign`; use fresh ETags to cancel and delete it. |
| [`voice_agent_telephony_calls.py`](voice_agent_telephony_calls.py) | List/get connected inbound calls, explicitly transfer/end an exact call, or verify targets on a temporary agent. A call ID is not a job ID. |
| [`voice_agent_system_tools.py`](voice_agent_system_tools.py) | Language/digit recognition, DTMF/SMS send/collect, and input-collection events; optional built-in telephony soundscape. Provider actions require actual phone-side setup. |

Provider values are `twilio`, `teams_phone_extensibility`, and `sip`. Outbound destinations use
E.164 phone numbers; Teams sources use resource-account GUIDs. SIP addresses are transfer-only
in this SDK version. Cancelling an outbound job/campaign stops future attempts, not connected
calls. A campaign may still place a billable call if cleanup fails.

The IVR recipes use model-compatible defaults: digits uses a speech-to-speech model; language,
DTMF, and SMS use a cascaded model. Override the model only with a compatible selection.
Retained agents respond automatically to speech. `--observe` controls only its own
WebSocket session and waits for the service's post-tool reply.
System-tool argument events represent intent, not execution success. DTMF/SMS delivery requires
a provider transport and is not proved by WebSocket observation. Soundscapes are telephony-only.

[`voice_agent_util.py`](voice_agent_util.py) and
[`voice_agent_live_util.py`](voice_agent_live_util.py) contain shared configuration/lifecycle functions;
[`voice_agent_storage_util.py`](voice_agent_storage_util.py) contains authenticated download helpers.
These three modules are not standalone samples.

## Running a sample

```bash
python voice_agent_basic.py
```

Each script starts with its purpose, environment variables, and run command. Management and basic
Realtime examples need only `FOUNDRY_PROJECT_ENDPOINT`; model defaults to `gpt-realtime`.
Leave `FOUNDRY_VOICE_AGENT_NAME` blank for a unique sample-owned name. Creating samples refuse
existing names; readback/image and telephony examples explicitly support existing agents.

The interactive conversation samples (`voice_agent_realtime_text_conversation*.py`) prompt
for input on the command line; end the session with a blank line, `exit`, or `Ctrl-C`.
Without `--audio-file`, `voice_agent_realtime_audio_conversation_async.py` uses your microphone
and speakers and runs until you press `Ctrl-C`.

## Notes

- Samples that create a voice agent clean up (delete) the version(s) they created when they exit,
  including on error. Existing resources are not removed; `--keep-agent` explicitly retains a
  newly created IVR agent. Realtime stored recordings follow project retention unless
  explicitly deleted; Live `--store` examples delete their owned conversation after readback.
- Conversation and audio persistence require the agent definition to set `store=True`.
- Avatar video and animation are separate capabilities; one does not prove the other.
- Custom Speech, transcript Decisions, animation, BYOS, and provider-specific
  operations require corresponding service support or setup. Unsupported responses remain
  errors; samples do not silently disable requested features.
- No sample logs credentials or raw audio. Downloaded WAVs contain conversation content; protect them.
- Review the [Responsible AI transparency note for Agents](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) before deploying a voice agent that real users will talk to.

## Next steps

- [Microsoft Foundry documentation](https://learn.microsoft.com/azure/foundry/)
- [`azure-ai-projects` on PyPI](https://pypi.org/project/azure-ai-projects/)
- [Microsoft Foundry Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)

## Local validation

From this directory in Bash, after installing the pinned requirements, run the same
lightweight checks declared in `sample.yaml`:

```bash
python -m py_compile *.py
python voice_agent_realtime_image_conversation.py --self-test
```

In PowerShell, use `python -m compileall -q -l .` for the syntax check.
The existing image self-test needs no Azure credentials; it is not an E2E test.
Live validation runs each sample with its documented setup. Microphone and telephony
scenarios additionally require audio hardware or provider configuration and consent.
