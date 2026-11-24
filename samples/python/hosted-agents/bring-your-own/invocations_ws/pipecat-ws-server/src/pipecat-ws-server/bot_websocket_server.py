# Copyright (c) Microsoft. All rights reserved.

"""Two Azure LLM agents with per-agent Azure TTS voices over a FastAPI WebSocket.

Architecture (mirrors examples/local/agent-handoff/two_llm_agents_with_tts.py):

    Main agent (no LLM/TTS):
        ws.in -> STT -> context_agg.user -> BusBridge ->
        ws.out -> context_agg.assistant

    LLM agent (with TTS):
        BusInput -> LLM -> TTS -> BusOutput

Two LLM agents:
  * "greeter"      - Zava online store greeter, voice en-US-AvaMultilingualNeural
  * "check_order"  - order-status agent, voice en-US-AndrewMultilingualNeural
"""

import os
import time

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    TextFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.azure.llm import AzureLLMService
from azure_tts_text_streaming import AzureTTSTextStreamingService

try:
    from websockets.asyncio.client import connect as websocket_connect
except ImportError:
    websocket_connect = None  # type: ignore
from pipecat.services.llm_service import FunctionCallParams, LLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from pipecat_subagents.agents import (
    BaseAgent,
    LLMAgent,
    LLMAgentActivationArgs,
    agent_ready,
    tool,
)
from pipecat_subagents.bus import AgentBus, BusBridgeProcessor
from pipecat_subagents.runner import AgentRunner
from pipecat_subagents.types import AgentReadyData
from azure_fast_transcription_stt import AzureFastTranscriptionSTTService
from pipecat.observers.turn_tracking_observer import TurnTrackingObserver
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver


# ---------------------------------------------------------------------------
# Wall-clock response latency observer
# ---------------------------------------------------------------------------


class WallClockLatencyObserver(BaseObserver):
    """Measures wall-clock time between UserStoppedSpeakingFrame and
    BotStartedSpeakingFrame using time.time() on both ends.

    Unlike the built-in UserBotLatencyObserver which uses VAD audio-clock
    timestamps, this gives the latency as seen by a wall clock on the server.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._user_stopped_time: float | None = None
        self._register_event_handler("on_wall_clock_latency")

    async def on_push_frame(self, data: FramePushed):
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        if isinstance(data.frame, UserStoppedSpeakingFrame):
            self._user_stopped_time = time.time()
        elif isinstance(data.frame, BotStartedSpeakingFrame):
            if self._user_stopped_time is not None:
                latency = time.time() - self._user_stopped_time
                self._user_stopped_time = None
                await self._call_event_handler("on_wall_clock_latency", latency)


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


def _build_stt() -> AzureFastTranscriptionSTTService:
    azure_fast_transcription_endpoint = f"https://{os.getenv('AZURE_SPEECH_REGION')}.api.cognitive.microsoft.com/"
    return AzureFastTranscriptionSTTService(
        api_key=os.getenv("AZURE_SPEECH_API_KEY"),
        endpoint=azure_fast_transcription_endpoint,
    )


def _build_tts(voice: str) -> AzureTTSTextStreamingService:
    return AzureTTSTextStreamingService(
        api_key=os.getenv("AZURE_SPEECH_API_KEY"),
        region=os.getenv("AZURE_SPEECH_REGION"),
        voice=voice,
    )


def _build_llm(system_instruction: str) -> AzureLLMService:
    return AzureLLMService(
        api_key=os.getenv("AZURE_FOUNDRY_API_KEY"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        settings=AzureLLMService.Settings(
            model=os.getenv("AZURE_LLM_MODEL"),
            system_instruction=system_instruction,
        ),
    )


# ---------------------------------------------------------------------------
# Drop foreign text frames at the LLM agent pipeline entry
# ---------------------------------------------------------------------------


class _DropForeignTextFrames(FrameProcessor):
    """Drop downstream `TextFrame`s arriving at the head of an LLM agent's pipeline.

    Each LLM agent in this app is created with ``bridged=()``, which causes
    the framework to wrap the agent's pipeline with bus-edge processors that
    fan ALL downstream frames out across the bus to every active agent.
    The TTS service produces text frames (`TTSTextFrame`, `AggregatedTextFrame`)
    that need to reach the main agent's `context_aggregator.assistant()` so
    the conversation context stays in sync. Those frames cross the bus to
    main correctly -- but they ALSO cross to every other active LLM agent.

    Without this filter, the receiving LLM agent's TTS would re-synthesize
    the foreign text, re-publish a fresh `TTSTextFrame`, and the main
    aggregator would append the same content twice (or three+ times during
    a handoff overlap). On the next user turn the LLM sees its own doubled
    history and faithfully continues the doubled style, which is what was
    being heard as ``"Welcome Welcome to to the the ..."``.

    Placing this filter at the very head of the user-built pipeline (i.e.
    immediately after the framework's `EdgeSource`) drops those bus-delivered
    text frames before they can reach the LLM/TTS path. The agent's own LLM
    is downstream of this filter, so the `LLMTextFrame`s it produces never
    pass through here -- they go straight to TTS, which consumes them.
    Non-text bus traffic (e.g. `LLMContextFrame`, `LLMRunFrame`, lifecycle
    frames) passes through unchanged.
    """

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if (
            direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, TextFrame)
        ):
            return  # silently drop foreign text frame
        await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# LLM agents (each has its own Azure TTS voice)
# ---------------------------------------------------------------------------


class ZavaTTSAgent(LLMAgent):
    """Base Zava agent with a per-agent Azure TTS voice and shared transfer tool."""

    def __init__(self, name: str, *, bus: AgentBus, voice: str):
        super().__init__(name, bus=bus, bridged=())
        self._voice = voice

    async def build_pipeline(self) -> Pipeline:
        # Pipeline (after framework wrapping):
        #     [EdgeSource, _DropForeignTextFrames, LLM, TTS, EdgeSink]
        # The drop filter prevents text frames published by OTHER LLM agents'
        # EdgeSinks from being re-synthesized by this agent's TTS, which is
        # the cause of the bot-text duplication that grows on each handoff.
        pipeline = await super().build_pipeline()
        return Pipeline(
            [
                _DropForeignTextFrames(name=f"{self.name}::DropForeignText"),
                pipeline,
                _build_tts(self._voice),
            ]
        )

    @tool(cancel_on_interruption=False)
    async def transfer_to_agent(
        self, params: FunctionCallParams, agent: str, reason: str
    ):
        """Transfer the user to another agent.

        Args:
            agent (str): The agent to transfer to (e.g. 'greeter', 'check_order').
            reason (str): Why the user is being transferred.
        """
        logger.info(f"Agent '{self.name}': transferring to '{agent}' ({reason})")
        await self.handoff_to(
            agent,
            messages=[
                {
                    "role": "developer",
                    "content": f"Tell the user about the transfer ({reason}).",
                }
            ],
            activation_args=LLMAgentActivationArgs(
                messages=[{"role": "developer", "content": reason}],
            ),
            result_callback=params.result_callback,
        )

    @tool
    async def end_conversation(self, params: FunctionCallParams, reason: str):
        """End the conversation when the user says goodbye.

        Args:
            reason (str): Why the conversation is ending.
        """
        logger.info(f"Agent '{self.name}': ending conversation ({reason})")
        await self.end(
            reason=reason,
            messages=[{"role": "developer", "content": reason}],
            result_callback=params.result_callback,
        )


class GreeterAgent(ZavaTTSAgent):
    """Greets the user for Zava online store and routes to the right specialist."""

    def __init__(self, name: str, *, bus: AgentBus):
        super().__init__(name, bus=bus, voice="en-US-Ava:DragonHDLatestNeural")

    def build_llm(self) -> LLMService:
        return _build_llm(
            system_instruction=(
                "You are the greeter for the Zava online store. "
                "Give a short, warm greeting and ask whether the user wants to "
                "(1) check an order status, or (2) report a product issue. "
                "When the user wants to check an order, call the transfer_to_agent "
                "tool with agent 'check_order'. "
                "If the user wants to report a product issue, briefly apologize and "
                "say a specialist will follow up by email (we do not have a product "
                "issue agent available right now). "
                "If the user says goodbye, call the end_conversation tool. "
                "Keep responses brief - this is a voice conversation."
            )
        )


class CheckOrderAgent(ZavaTTSAgent):
    """Helps the user check order status."""

    def __init__(self, name: str, *, bus: AgentBus):
        super().__init__(name, bus=bus, voice="en-US-Andrew:DragonHDLatestNeural")

    def build_llm(self) -> LLMService:
        return _build_llm(
            system_instruction=(
                "You are the order-status agent for the Zava online store. "
                "First, ask the user for their full name. "
                "Then ask for the phone number associated with the order. "
                "Once you have both, always tell the user: "
                "'Your package will be delivered within 2 days.' "
                "If the user wants to do something else, call the transfer_to_agent "
                "tool with agent 'greeter'. "
                "If the user says goodbye, call the end_conversation tool. "
                "Keep responses brief - this is a voice conversation."
            )
        )


# ---------------------------------------------------------------------------
# Main transport-owning agent
# ---------------------------------------------------------------------------


class ZavaMainAgent(BaseAgent):
    """Owns the FastAPI WebSocket transport and bridges frames to/from the bus."""

    def __init__(
        self, name: str, *, bus: AgentBus, transport: FastAPIWebsocketTransport
    ):
        super().__init__(name, bus=bus)
        self._transport = transport

    @agent_ready(name="greeter")
    async def on_greeter_ready(self, data: AgentReadyData) -> None:
        await self.activate_agent(
            "greeter",
            args=LLMAgentActivationArgs(
                messages=[
                    {
                        "role": "developer",
                        "content": (
                            "Welcome the user to the Zava online store, give a short "
                            "greeting, and ask whether they want to check an order or "
                            "report a product issue."
                        ),
                    },
                ],
            ),
        )

    def build_pipeline_task(self, pipeline: Pipeline) -> PipelineTask:
        turn_observer = TurnTrackingObserver(turn_end_timeout_secs=2.5)
        latency_observer = UserBotLatencyObserver()
        wall_clock_observer = WallClockLatencyObserver()

        task = PipelineTask(
            pipeline,
            enable_rtvi=True,
            idle_timeout_secs=None,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            observers=[turn_observer, latency_observer, wall_clock_observer],
        )

        @turn_observer.event_handler("on_turn_started")
        async def on_turn_started(observer, turn_count):
            logger.info(f"Turn {turn_count} started")
            await task.queue_frame(
                RTVIServerMessageFrame({"type": "turn-started", "turn_count": turn_count})
            )

        @turn_observer.event_handler("on_turn_ended")
        async def on_turn_ended(observer, turn_count, duration, was_interrupted):
            status = "interrupted" if was_interrupted else "completed"
            logger.info(f"Turn {turn_count} {status} after {duration:.2f}s")
            await task.queue_frame(
                RTVIServerMessageFrame({
                    "type": "turn-ended",
                    "turn_count": turn_count,
                    "duration": round(duration, 3),
                    "was_interrupted": was_interrupted,
                })
            )

        @latency_observer.event_handler("on_latency_measured")
        async def on_latency_measured(observer, latency_seconds):
            pass  # Suppressed — use wall-clock TTFA instead

        @wall_clock_observer.event_handler("on_wall_clock_latency")
        async def on_wall_clock_latency(observer, latency_seconds):
            logger.info(f"TTFA (time to first audio): {latency_seconds:.3f}s")
            await task.queue_frame(
                RTVIServerMessageFrame({
                    "type": "ttfa",
                    "latency_seconds": round(latency_seconds, 3),
                })
            )

        return task

    async def build_pipeline(self) -> Pipeline:
        stt = _build_stt()

        context = LLMContext()
        context_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=SileroVADAnalyzer(),
                # Disable UserStoppedSpeakingFrame from the turn stop strategy;
                # the STT pushes it downstream at VAD end instead so the RTVI
                # event fires immediately without waiting for transcription.
                user_turn_strategies=UserTurnStrategies(
                    stop=[
                        TurnAnalyzerUserTurnStopStrategy(
                            turn_analyzer=LocalSmartTurnAnalyzerV3(),
                            enable_user_speaking_frames=False,
                        )
                    ],
                ),
            ),
        )

        bridge = BusBridgeProcessor(
            bus=self.bus,
            agent_name=self.name,
            name=f"{self.name}::BusBridge",
        )

        @self._transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Pipecat client connected")
            greeter = GreeterAgent("greeter", bus=self.bus)
            check_order = CheckOrderAgent("check_order", bus=self.bus)
            for agent in (greeter, check_order):
                await self.add_agent(agent)

        @self._transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Pipecat client disconnected")
            await self.cancel()

        return Pipeline(
            [
                self._transport.input(),
                stt,
                context_aggregator.user(),
                bridge,
                self._transport.output(),
                context_aggregator.assistant(),
            ]
        )


# ---------------------------------------------------------------------------
# Entry point used by server.py
# ---------------------------------------------------------------------------


async def run_bot(websocket_client):
    """Run the multi-agent bot over a FastAPI WebSocket connection."""
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )

    runner = AgentRunner(handle_sigint=False)
    main = ZavaMainAgent("zava", bus=runner.bus, transport=transport)
    await runner.add_agent(main)
    await runner.run()
