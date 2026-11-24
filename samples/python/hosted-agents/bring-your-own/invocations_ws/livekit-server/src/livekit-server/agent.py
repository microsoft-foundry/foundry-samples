# Copyright (c) Microsoft. All rights reserved.

"""LiveKit multi-agent voice workflow using Azure STT/LLM/TTS.

Models a small Zava online store front-of-house:

  * ``GreeterAgent``     - welcomes the user, routes to a specialist.
  * ``CheckOrderAgent``  - collects name + phone, reports order status.

Each specialist is a separate ``livekit.agents.Agent`` subclass with
its own Azure TTS voice override. The LLM transfers control by
returning a different agent from a ``@function_tool`` call, as
described in
https://docs.livekit.io/agents/logic/agents-handoffs/ .

Voice pipeline (shared by all agents on the session):
    Azure Speech STT  ->  Azure OpenAI LLM  ->  Azure Speech TTS

Usage:
    python agent.py dev       # live-reload, joins newly-created rooms
    python agent.py start     # production worker
    python agent.py console   # terminal-only, no LiveKit server needed
    python agent.py download-files   # pre-fetch Silero VAD weights
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    ChatContext,
    RoomInputOptions,
    RunContext,
    function_tool,
)
from livekit.agents.llm import ChatMessage
from livekit.agents.metrics import (
    EOUMetrics,
    LLMMetrics,
    STTMetrics,
    TTSMetrics,
)
from livekit.plugins import azure, openai, silero

from azure_tts_text_streaming import TTS as AzureTextStreamingTTS

load_dotenv(override=True)

logger = logging.getLogger("foundry-azure-voice")


# Use local VAD-based interruption handling instead of LiveKit Cloud's
# Adaptive Interruption (which requires LIVEKIT_INFERENCE_API_KEY and only
# works against agent-gateway.livekit.cloud).
_TURN_HANDLING = {
    "interruption": {"mode": "vad"},
}


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


def _build_stt() -> azure.STT:
    return azure.STT(
        speech_key=os.environ["AZURE_SPEECH_API_KEY"],
        speech_region=os.environ["AZURE_SPEECH_REGION"],
    )


def _build_llm() -> openai.LLM:
    return openai.LLM.with_azure(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_FOUNDRY_API_KEY"],
        api_version=os.environ.get(
            "AZURE_OPENAI_API_VERSION", "2024-10-01-preview"
        ),
        azure_deployment=os.environ["AZURE_LLM_MODEL"],
    )


def _build_tts(voice: str) -> AzureTextStreamingTTS:
    """Azure TTS that streams LLM tokens straight into the synthesiser.

    Uses the websocket v2 (``TextStream``) endpoint, so audio starts
    flowing as soon as the first tokens arrive instead of waiting for a
    full sentence the way the stock ``livekit.plugins.azure.TTS`` (SSML
    POST per utterance) does. See ``azure_tts_text_streaming.py``.
    """
    return AzureTextStreamingTTS(
        speech_key=os.environ["AZURE_SPEECH_API_KEY"],
        speech_region=os.environ["AZURE_SPEECH_REGION"],
        voice=voice,
    )


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


GREETER_VOICE = os.environ.get(
    "AZURE_TTS_VOICE_GREETER", "en-US-Ava:DragonHDLatestNeural"
)
CHECK_ORDER_VOICE = os.environ.get(
    "AZURE_TTS_VOICE_CHECK_ORDER", "en-US-Andrew:DragonHDLatestNeural"
)


class GreeterAgent(Agent):
    """Welcomes the user to Zava and routes to the right specialist."""

    def __init__(self, chat_ctx: ChatContext | None = None) -> None:
        super().__init__(
            instructions=(
                "You are the greeter for the Zava online store. "
                "Give a short, warm greeting and ask whether the user wants "
                "to (1) check an order status, or (2) report a product issue. "
                "When the user wants to check an order, call the "
                "transfer_to_check_order tool. "
                "If the user wants to report a product issue, briefly "
                "apologize and say a specialist will follow up by email "
                "(we do not have a product issue agent available right now). "
                "Keep responses brief - this is a voice conversation."
            ),
            tts=_build_tts(GREETER_VOICE),
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=(
                "Welcome the user to the Zava online store, give a short "
                "greeting, and ask whether they want to check an order or "
                "report a product issue."
            )
        )

    @function_tool()
    async def transfer_to_check_order(self, context: RunContext):
        """Transfer the user to the order-status agent to look up an order."""
        return (
            CheckOrderAgent(
                chat_ctx=self.chat_ctx.copy(exclude_instructions=True)
            ),
            "Transferring you to our order status specialist.",
        )


class CheckOrderAgent(Agent):
    """Collects name + phone and reports a (mock) order status."""

    def __init__(self, chat_ctx: ChatContext | None = None) -> None:
        super().__init__(
            instructions=(
                "You are the order-status agent for the Zava online store. "
                "First, ask the user for their full name. "
                "Then ask for the phone number associated with the order. "
                "Once you have both, always tell the user: "
                "'Your package will be delivered within 2 days.' "
                "If the user wants to do something else, call the "
                "transfer_to_greeter tool. "
                "Keep responses brief - this is a voice conversation."
            ),
            tts=_build_tts(CHECK_ORDER_VOICE),
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=(
                "Introduce yourself as the order-status specialist and ask "
                "the user for their full name."
            )
        )

    @function_tool()
    async def transfer_to_greeter(self, context: RunContext):
        """Hand control back to the greeter for anything else."""
        return (
            GreeterAgent(
                chat_ctx=self.chat_ctx.copy(exclude_instructions=True)
            ),
            "Transferring you back to the greeter.",
        )


# ---------------------------------------------------------------------------
# Worker entrypoint
# ---------------------------------------------------------------------------


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()

    session = AgentSession(
        stt=_build_stt(),
        llm=_build_llm(),
        # Per-agent TTS overrides (set in each Agent subclass) take
        # precedence, but a session-level default keeps things working if a
        # future agent forgets to set one.
        tts=_build_tts(GREETER_VOICE),
        vad=silero.VAD.load(),
        turn_handling=_TURN_HANDLING,
    )

    _wire_session_events(session, ctx.room)

    await session.start(
        room=ctx.room,
        agent=GreeterAgent(),
        room_input_options=RoomInputOptions(),
    )


# ---------------------------------------------------------------------------
# Event logging + TTFA (time-to-first-audio) wall-clock measurement
# ---------------------------------------------------------------------------
#
# AgentSession emits structured events (see
# https://docs.livekit.io/reference/agents/events/). We forward a subset to
# the browser over a LiveKit data-channel topic so the chat UI can display
# them, and we use ``user_state_changed`` + ``agent_state_changed`` to
# compute a wall-clock TTFA -- the seconds between the user being detected
# as stopped speaking and the agent starting to speak.

_EVENT_TOPIC = "agent-events"


def _wire_session_events(session: AgentSession, room: rtc.Room) -> None:
    loop = asyncio.get_event_loop()
    user_stopped_at: dict[str, float | None] = {"t": None}

    def publish(payload: dict) -> None:
        """Log locally + ship the event to the browser as JSON."""
        logger.info("event: %s", payload)
        data = json.dumps(payload).encode("utf-8")

        async def _send() -> None:
            try:
                await room.local_participant.publish_data(
                    data, reliable=True, topic=_EVENT_TOPIC
                )
            except Exception as e:  # pragma: no cover - best effort
                logger.warning("publish_data failed: %s", e)

        loop.create_task(_send())

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        publish({
            "type": "user_state_changed",
            "old": str(ev.old_state),
            "new": str(ev.new_state),
        })
        # The user transitioning to ``listening`` is the LiveKit equivalent
        # of a VAD UserStoppedSpeakingFrame -- start the TTFA stopwatch.
        if str(ev.new_state) == "listening":
            user_stopped_at["t"] = time.time()

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        new_state = str(ev.new_state)
        evt = {
            "type": "agent_state_changed",
            "old": str(ev.old_state),
            "new": new_state,
        }
        # First moment the agent is producing audio for the new turn.
        if new_state == "speaking" and user_stopped_at["t"] is not None:
            ttfa = time.time() - user_stopped_at["t"]
            user_stopped_at["t"] = None
            evt["ttfa_seconds"] = round(ttfa, 3)
            publish(evt)
            publish({"type": "ttfa", "latency_seconds": round(ttfa, 3)})
            return
        publish(evt)

    @session.on("user_input_transcribed")
    def _on_user_transcribed(ev) -> None:
        publish({
            "type": "user_input_transcribed",
            "transcript": ev.transcript,
            "is_final": ev.is_final,
        })

    @session.on("conversation_item_added")
    def _on_item_added(ev) -> None:
        if not isinstance(ev.item, ChatMessage):
            return
        text = (ev.item.text_content or "").strip()
        publish({
            "type": "conversation_item_added",
            "role": ev.item.role,
            "text": text[:500],
            "interrupted": bool(getattr(ev.item, "interrupted", False)),
        })

    @session.on("function_tools_executed")
    def _on_tools(ev) -> None:
        publish({
            "type": "function_tools_executed",
            "tools": [fc.name for fc in ev.function_calls],
            "has_agent_handoff": bool(ev.has_agent_handoff),
        })

    @session.on("speech_created")
    def _on_speech_created(ev) -> None:
        publish({
            "type": "speech_created",
            "source": str(ev.source),
            "user_initiated": bool(ev.user_initiated),
        })

    @session.on("close")
    def _on_close(ev) -> None:
        publish({
            "type": "close",
            "reason": str(ev.reason),
            "error": None if ev.error is None else str(ev.error),
        })

    # Per-plugin metrics (STT/LLM/TTS/EOU). The session-level
    # ``metrics_collected`` event is marked deprecated in the docs in favour
    # of subscribing on each plugin instance, but it still fires and is the
    # most compact way to collect all stages from a single hook.
    # See https://docs.livekit.io/deploy/observability/data/#metrics-reference
    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        m = ev.metrics
        sid = getattr(m, "speech_id", None)
        if isinstance(m, STTMetrics):
            publish({
                "type": "stt_metrics",
                "speech_id": sid,
                "duration": round(m.duration, 3),
                "audio_duration": round(m.audio_duration, 3),
                "streamed": bool(m.streamed),
            })
        elif isinstance(m, LLMMetrics):
            publish({
                "type": "llm_metrics",
                "speech_id": sid,
                "ttft": round(m.ttft, 3),
                "duration": round(m.duration, 3),
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "tokens_per_second": round(m.tokens_per_second, 1),
            })
        elif isinstance(m, TTSMetrics):
            publish({
                "type": "tts_metrics",
                "speech_id": sid,
                "ttfb": round(m.ttfb, 3),
                "duration": round(m.duration, 3),
                "audio_duration": round(m.audio_duration, 3),
                "streamed": bool(m.streamed),
            })
        elif isinstance(m, EOUMetrics):
            publish({
                "type": "eou_metrics",
                "speech_id": sid,
                "end_of_utterance_delay": round(m.end_of_utterance_delay, 3),
                "transcription_delay": round(m.transcription_delay, 3),
            })


if __name__ == "__main__":
    # ``agent_name`` switches this worker into EXPLICIT DISPATCH mode:
    # it only receives jobs whose RoomConfiguration includes a
    # RoomAgentDispatch for this name. That keeps it from competing
    # with other workers (e.g. a pre-deployed Cloud agent) that run
    # under the same project.
    # ``port=0`` -> the worker's built-in HTTP health server picks a
    # random free port, avoiding collisions with anything else on :8081.
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=os.environ.get(
                "LIVEKIT_AGENT_WORKER_NAME", "foundry-azure-voice"
            ),
            port=0,
        )
    )
