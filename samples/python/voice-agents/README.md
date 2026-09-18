---
page_type: sample
languages:
- python
products:
- ai-services
- azure
description: Create, manage, and converse with Microsoft Foundry Voice Agents (preview) using azure-ai-projects.
---

# 🎙️ Microsoft Foundry Voice Agents — Python Samples

These samples show how to build and manage **Voice Agents (preview)** with the
[`azure-ai-projects`](https://pypi.org/project/azure-ai-projects/) Python SDK. Voice agents provide
real-time, speech-to-speech conversational AI, reachable over a WebSocket
(`project_client.beta.voice_agents.realtime`), with persisted conversation transcripts and audio
through `project_client.beta.voice_agents.conversations`.

Voice agents are exposed through `project_client.agents` with `kind="voice"` — the same management
surface (create, version, list, delete) used for prompt, workflow, hosted, and external agents.

> [!IMPORTANT]
> Voice Agents are a **preview** feature. Preview API calls in these samples require
> `AIProjectClient(..., allow_preview=True)`. APIs and behavior may change before general
> availability.

## Prerequisites

- **Python 3.9+**
- A **Microsoft Foundry project** — see the [Overview page](https://ai.azure.com/) of your project
  for its endpoint.
- A **realtime model deployment** (for example `gpt-realtime`) in your project.
- **Azure CLI**, logged in (`az login`) — the samples authenticate with `DefaultAzureCredential`.
- Optional: **[PyAudio](https://pypi.org/project/PyAudio/)** for local microphone capture and
  speaker playback in the realtime samples. Samples fall back to a headless mode (no local audio
  I/O) if it isn't installed.

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
   cp .env.sample .env
   ```

   Edit `.env` with your own values. At minimum, set `FOUNDRY_PROJECT_ENDPOINT`.

## Samples

### Agent lifecycle and management

| Sample | Description |
| --- | --- |
| [`voice_agent_basic.py`](voice_agent_basic.py) | Create, retrieve, list, update, disable/enable, and delete a voice agent (sync client). |
| [`voice_agent_basic_async.py`](voice_agent_basic_async.py) | The same management lifecycle using the async client. |
| [`voice_agent_generate.py`](voice_agent_generate.py) | Guided authoring: generate a starter voice agent definition with `beta.agents.create_from_prompt()`. |
| [`voice_agent_versions.py`](voice_agent_versions.py) | Work with immutable agent versions: new versions, draft versions, listing, and reading a specific version. |
| [`voice_agent_with_tools.py`](voice_agent_with_tools.py) | Richer agent definitions: input-audio config (turn detection, transcription), function/system/MCP/toolbox tools, and bring-your-own-model (BYOM). |

### Realtime conversations

| Sample | Description |
| --- | --- |
| [`voice_agent_realtime_text_conversation.py`](voice_agent_realtime_text_conversation.py) | Interactive, typed, multi-turn realtime conversation (sync). Replies stream back as audio + transcript and play through speakers if PyAudio is installed. |
| [`voice_agent_realtime_text_conversation_async.py`](voice_agent_realtime_text_conversation_async.py) | The same typed conversation using the async client. |
| [`voice_agent_realtime_audio_conversation_async.py`](voice_agent_realtime_audio_conversation_async.py) | Hands-free, bidirectional mic ⇄ speaker conversation with server-side turn detection and barge-in (async only). |
| [`voice_agent_realtime_function_tool.py`](voice_agent_realtime_function_tool.py) | Handle a client-executed `function` tool call during a live realtime session. |

### Reading persisted conversations

| Sample | Description |
| --- | --- |
| [`voice_agent_read_conversation.py`](voice_agent_read_conversation.py) | Read a persisted conversation back: its envelope, responses, and ordered transcript items. |
| [`voice_agent_read_conversation_audio.py`](voice_agent_read_conversation_audio.py) | Read persisted conversation audio: the merged whole-call recording and a single item's audio segment. |
| [`voice_agent_util.py`](voice_agent_util.py) | Shared helper (not a standalone sample) that holds one short realtime turn to produce a real conversation on demand, used by the two samples above. |

## Running a sample

```bash
python voice_agent_basic.py
```

Each script's module docstring documents its own required and optional environment variables. Most
default to sensible values (for example `FOUNDRY_VOICE_AGENT_MODEL` defaults to `"gpt-realtime"`) so
you can run them with only `FOUNDRY_PROJECT_ENDPOINT` set.

The interactive conversation samples (`voice_agent_realtime_text_conversation*.py`) prompt
for input on the command line; end the session with a blank line, `exit`, or `Ctrl-C`.
`voice_agent_realtime_audio_conversation_async.py` uses your microphone and speakers instead
and runs until you press `Ctrl-C`.

## Notes

- Samples that create a voice agent clean up (delete) the version(s) they created when they exit,
  including on error — they don't modify or delete an agent you name yourself via
  `FOUNDRY_VOICE_AGENT_NAME`.
- Conversation and audio persistence require the agent definition to set `store=True`.
- Review the [Responsible AI transparency note for Agents](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) before deploying a voice agent that real users will talk to.

## Next steps

- [Microsoft Foundry documentation](https://learn.microsoft.com/azure/foundry/)
- [`azure-ai-projects` on PyPI](https://pypi.org/project/azure-ai-projects/)
- [Microsoft Foundry Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)
