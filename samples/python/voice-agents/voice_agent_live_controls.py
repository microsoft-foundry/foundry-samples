"""Native GPT Live input mute, silent context, and transcript Decision triggers.

Run: python voice_agent_live_controls.py [--transcript-triggers] [--listen-seconds 15]
Requires azure-ai-projects[voice]==2.11.0, azure-identity, python-dotenv.
Env: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_LIVE_MODEL (existing deployment),
FOUNDRY_VOICE_AUDIO_INPUT_PATH (spoken PCM16 mono 24000-Hz WAV, at most 30 s).
Optional FOUNDRY_VOICE_LIVE_OUTPUT_PATH: a NEW reply WAV.

DefaultAzureCredential authenticates. The sample creates/deletes only a unique
owned agent version. It checks typed, command-correlated mute/unmute/thinking
acknowledgements, then feeds the caller's WAV after unmuting. thinking.append
supplies labeled, unspoken demo context, never private reasoning. Decisions run
independently on the two supported transcript-delta triggers; no transcript-done
or hypothetical turn-completion event is used. Trigger completions are correlated
to actual transcript event IDs. --transcript-triggers explicitly opts into this
service-dependent feature; unsupported session.triggers errors propagate, never
silently disable it. The default runs input controls without requesting Decisions.
The bounded audio capture is NOT speech completion.
No microphone, speakers, existing agent mutation, or silent fallback is involved.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from contextlib import AsyncExitStack
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from azure.ai.projects import models
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.aio.operations import AsyncBetaLiveConnection
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_live_audio import output_wav, read_pcm, stream_audio
from voice_agent_live_util import (
    audio_clock,
    audio_settings,
    create_owned_agent,
    live_session,
    wait_event,
)

TRANSCRIPT_TYPES = (
    "session.input_transcript.delta",
    "session.output_transcript.delta",
)


def transcript_triggers() -> list[models.LiveDecisionTriggerInputParam]:
    questions = models.LiveDecisionQuestionsInputParam(
        questions=[
            models.LiveDecisionPredicateQuestionParam(
                name="contains_question",
                instructions="Does the current transcript contain a question?",
            )
        ]
    )
    return [
        models.LiveDecisionTriggerInputParam(
            event_type="session.input_transcript.delta", decisions=questions
        ),
        models.LiveDecisionTriggerInputParam(
            event_type="session.output_transcript.delta", decisions=questions
        ),
    ]


async def set_triggers(connection: AsyncBetaLiveConnection, *, enabled: bool) -> None:
    event_id = (
        "enable-transcript-triggers" if enabled else "disable-transcript-triggers"
    )
    await connection.session.update(
        session=models.LiveSessionUpdateParams(
            triggers=transcript_triggers() if enabled else []
        ),
        event_id=event_id,
    )
    updated = await wait_event(connection, "session.updated", client_event_id=event_id)
    if not isinstance(updated, models.LiveServerEventLiveSessionUpdated):
        raise RuntimeError("Expected the SDK's typed session.updated acknowledgement.")
    configured = updated.session.triggers
    if (
        not isinstance(configured, list)
        or not all(
            isinstance(trigger, models.LiveDecisionTriggerInputParam)
            for trigger in configured
        )
        or len(configured) != (len(TRANSCRIPT_TYPES) if enabled else 0)
        or {trigger.event_type for trigger in configured}
        != (set(TRANSCRIPT_TYPES) if enabled else set())
    ):
        raise RuntimeError("Live did not apply the requested transcript triggers.")
    print(f"Confirmed transcript triggers {'enabled' if enabled else 'disabled'}.")


async def prepare_controls(
    connection: AsyncBetaLiveConnection, *, transcript_decisions: bool = False
) -> None:
    async with audio_clock(connection):
        await connection.session.input_audio.mute(event_id="mute-input")
        muted = await wait_event(
            connection, "session.input_audio.muted", client_event_id="mute-input"
        )
        if not isinstance(muted, models.LiveServerEventLiveInputAudioMuted):
            raise RuntimeError(
                "Expected the SDK's typed input-audio muted acknowledgement."
            )
        await connection.session.thinking.append(
            content=(
                "Local demo context, not a production lookup: the sample inventory "
                "contains three blue mugs. This is unspoken context, not a request "
                "to read it aloud."
            ),
            delegation_id=None,
            event_id="append-demo-context",
        )
        appended = await wait_event(
            connection,
            "session.thinking.appended",
            client_event_id="append-demo-context",
        )
        if not isinstance(appended, models.LiveServerEventLiveThinkingAppended):
            raise RuntimeError(
                "Expected the SDK's typed thinking.appended acknowledgement."
            )
        await connection.session.input_audio.unmute(event_id="unmute-input")
        unmuted = await wait_event(
            connection, "session.input_audio.unmuted", client_event_id="unmute-input"
        )
        if not isinstance(unmuted, models.LiveServerEventLiveInputAudioUnmuted):
            raise RuntimeError(
                "Expected the SDK's typed input-audio unmuted acknowledgement."
            )
    print("Confirmed typed mute, unspoken demo context, and unmute acknowledgements.")
    if transcript_decisions:
        await set_triggers(connection, enabled=True)


def observe_trigger(
    event: Mapping[str, Any],
    transcripts: dict[str, str],
    decisions: dict[str, set[str]],
) -> None:
    if isinstance(
        event,
        (
            models.LiveServerEventLiveInputTranscriptDelta,
            models.LiveServerEventLiveOutputTranscriptDelta,
        ),
    ):
        if not isinstance(event.event_id, str) or not event.event_id:
            raise RuntimeError("Transcript event omitted its correlation ID.")
        transcripts[event.event_id] = event.type
    elif isinstance(event, models.LiveServerEventLiveDecisionEvent):
        source_type, source_id = event.source_event_type, event.source_event_id
        if (
            source_type not in TRANSCRIPT_TYPES
            or transcripts.get(source_id) != source_type
            or not isinstance(event.trigger_id, str)
            or not event.trigger_id
        ):
            raise RuntimeError(
                "Decision trigger does not match an observed transcript event."
            )
        completed = event.event
        if (
            not isinstance(completed, models.LiveDecisionCompleted)
            or completed.type != "decision.completed"
            or not isinstance(completed.decision, models.DecisionResponse)
            or not isinstance(completed.decision.answers, list)
            or len(completed.decision.answers) != 1
        ):
            raise RuntimeError("Malformed transcript-trigger Decision completion.")
        answer = completed.decision.answers[0]
        if answer.get("type") == "refusal":
            raise RuntimeError("The transcript-trigger Decision was refused.")
        if (
            not isinstance(answer, models.AnswerResourcePredicate)
            or answer.name != "contains_question"
            or not isinstance(answer.probability, (int, float))
            or isinstance(answer.probability, bool)
            or not 0 <= answer.probability <= 1
        ):
            raise RuntimeError(
                "Decision answer does not match the configured question."
            )
        decisions.setdefault(source_type, set()).add(source_id)


async def main(
    listen_seconds: float = 15, *, transcript_decisions: bool = False
) -> None:
    if not 1 <= listen_seconds <= 60:
        raise ValueError("listen_seconds must be between 1 and 60.")
    load_dotenv()
    pcm = read_pcm(Path(os.environ["FOUNDRY_VOICE_AUDIO_INPUT_PATH"]))
    path = Path(
        os.environ.get("FOUNDRY_VOICE_LIVE_OUTPUT_PATH")
        or f"voice-live-controls-{uuid4().hex[:8]}.wav"
    )
    transcripts: dict[str, str] = {}
    decisions: dict[str, set[str]] = {}

    async def on_event(_: AsyncBetaLiveConnection, event: Mapping[str, Any]) -> None:
        if isinstance(event, models.LiveServerEventLiveDelegationCreated):
            raise RuntimeError(
                "The controls-only agent unexpectedly delegated its answer."
            )
        observe_trigger(event, transcripts, decisions)

    with output_wav(path) as output:
        async with (
            DefaultAzureCredential(process_timeout=60) as credential,
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=credential,
                allow_preview=True,
            ) as project,
            AsyncExitStack() as cleanup,
        ):
            agent = await create_owned_agent(
                project,
                cleanup,
                "controls",
                models.VoiceAgentLiveDefinition(
                    model_type=models.VoiceModelType.SELF_DEPLOYED,
                    model=os.environ["FOUNDRY_VOICE_LIVE_MODEL"],
                    instructions=(
                        "Answer the spoken question yourself in one short sentence. "
                        "Do not delegate. Silent sample context is not a request to speak."
                    ),
                    audio=audio_settings(),
                    store=False,
                ),
            )
            async with live_session(project, cleanup, agent) as (connection, _):
                await prepare_controls(
                    connection, transcript_decisions=transcript_decisions
                )
                user_text, agent_text, count = await stream_audio(
                    connection,
                    pcm,
                    output,
                    on_event=on_event,
                    listen_seconds=listen_seconds,
                )
                if (
                    not user_text.strip()
                    or not agent_text.strip()
                    or (
                        transcript_decisions and set(decisions) != set(TRANSCRIPT_TYPES)
                    )
                ):
                    raise RuntimeError(
                        "Missing spoken transcripts or correlated Decisions for both triggers."
                    )
                if transcript_decisions:
                    await set_triggers(connection, enabled=False)
    label = (
        "input/output transcript triggers"
        if transcript_decisions
        else "native input controls"
    )
    print(
        f"Confirmed {label}; captured {count} reply PCM16 bytes "
        f"in {path}. Capture-window end does not prove speech completion."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transcript-triggers",
        action="store_true",
        help="Request Decisions triggers; requires service support for session.triggers.",
    )
    parser.add_argument("--listen-seconds", type=float, default=15)
    options = parser.parse_args()
    asyncio.run(
        main(
            options.listen_seconds,
            transcript_decisions=options.transcript_triggers,
        )
    )
