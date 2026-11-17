"""Native GPT Live client delegation, or a pinned same-project prompt backend.

Run: python voice_agent_live_delegation.py [--managed] [--listen-seconds 30]
Requires azure-ai-projects[voice]==2.11.0, azure-identity, python-dotenv.
Env: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_LIVE_MODEL (existing GPT Live
deployment), FOUNDRY_VOICE_AUDIO_INPUT_PATH (spoken PCM16 mono 24000-Hz WAV,
at most 30 seconds). --managed also requires FOUNDRY_MODEL_NAME (existing prompt
model deployment in the SAME project). Optional FOUNDRY_VOICE_LIVE_OUTPUT_PATH:
a new reply WAV. DefaultAzureCredential authenticates. Only unique versions
created by this run are deleted; no existing agents are modified.

For client mode, record "How many blue mugs are in the demo inventory?"
The app supplies explicitly labeled local demo data with correlated commentary.
Use the typed session.delegation.created ID to correlate the local demo reply.
The capture timer does not signal frontend speech completion.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from azure.ai.projects import models
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.aio.operations import AsyncBetaLiveConnection
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_live_audio import (
    decode_audio,
    has_audio,
    output_wav,
    read_pcm,
    stream_audio,
)
from voice_agent_live_util import (
    audio_settings,
    check_event,
    create_owned_agent,
    live_session,
)


async def reply_to_client(
    connection: AsyncBetaLiveConnection,
    event: Mapping[str, Any],
    replies: dict[str, str],
    accepted: set[str],
) -> None:
    """Deduplicate delegation notifications and correlate commentary acknowledgements."""
    if isinstance(event, models.LiveServerEventLiveCommentaryAppended):
        accepted.update(
            key for key, value in replies.items() if value == event.client_event_id
        )
        return
    if isinstance(event, models.LiveServerEventLiveDelegationCreated):
        if (
            not isinstance(event.delegation, models.VoiceAgentLiveDelegationItem)
            or event.delegation.target != "client"
        ):
            raise RuntimeError(
                "The client handler received work owned by another backend."
            )
        delegation_id = event.delegation.id
    else:
        return
    if not isinstance(delegation_id, str) or not delegation_id.strip():
        raise RuntimeError(
            "Delegation omitted an explicit ID; refusing to guess correlation."
        )
    if delegation_id in replies:
        return
    if len(replies) >= 3:
        raise RuntimeError("Exceeded the three-delegation sample limit.")
    event_id = f"demo-commentary-{len(replies)}"
    await connection.session.commentary.append(
        content="The local demo inventory has three blue mugs. This is sample data, not a production lookup.",
        delegation_id=delegation_id,
        event_id=event_id,
    )
    replies[delegation_id] = event_id


def verify_managed_session(
    session: models.VoiceAgentLiveSessionResource, backend: models.AgentVersionDetails
) -> None:
    owner = session.delegation
    if (
        not isinstance(owner, models.VoiceAgentLiveManagedAgentDelegation)
        or owner.agent_name != backend.name
        or owner.agent_version != backend.version
    ):
        raise RuntimeError(
            "Live did not pin the exact same-project prompt-agent version created by this run."
        )


@dataclass
class ManagedDelegation:
    response_id: str | None = None
    completed: bool = False


def observe_managed(
    event: Mapping[str, Any], delegations: dict[str, ManagedDelegation]
) -> bool:
    """Backend completion and observed frontend speech are independent evidence."""
    nested = check_event(event)
    if isinstance(event, models.LiveServerEventLiveDelegationCreated):
        if (
            not isinstance(event.delegation, models.VoiceAgentLiveDelegationItem)
            or event.delegation.target != "foundry_managed_agent"
            or not isinstance(event.delegation.id, str)
            or not event.delegation.id.strip()
        ):
            raise RuntimeError(
                "Expected Foundry-managed delegation, not application-owned work."
            )
        if event.delegation.id not in delegations and len(delegations) >= 3:
            raise RuntimeError("Exceeded the three-delegation sample limit.")
        delegations.setdefault(event.delegation.id, ManagedDelegation())
    elif nested:
        delegation_id = event.get("delegation_id")
        if delegation_id not in delegations:
            raise RuntimeError(
                "Managed backend event does not match an observed delegation."
            )
        state = delegations[delegation_id]
        snapshot = nested.get("response")
        if snapshot is not None and not isinstance(snapshot, Mapping):
            raise RuntimeError("Malformed managed backend response snapshot.")
        if nested["type"] in ("response.created", "response.in_progress") and (
            state.response_id is None
            or state.completed
            or nested["type"] == "response.created"
        ):
            response_id = snapshot.get("id") if snapshot is not None else None
            if not isinstance(response_id, str) or not response_id:
                raise RuntimeError("Managed response.created omitted a response ID.")
            if state.response_id is not None and not state.completed:
                raise RuntimeError(
                    "Concurrent managed backend responses are unsupported."
                )
            state.response_id, state.completed = response_id, False
        if state.response_id is None:
            raise RuntimeError(
                "Managed backend output arrived before response.created."
            )
        identifiers = [nested["response_id"]] if "response_id" in nested else []
        if snapshot is not None and "id" in snapshot:
            identifiers.append(snapshot["id"])
        if any(identifier != state.response_id for identifier in identifiers):
            raise RuntimeError(
                "Managed backend response ID does not match its delegation."
            )
        if nested["type"] == "response.completed":
            if snapshot is None or snapshot.get("status") != "completed":
                raise RuntimeError(
                    "Managed backend completion did not have status=completed."
                )
            state.completed = True
    elif isinstance(event, models.LiveOutputAudioDelta) and any(
        state.completed for state in delegations.values()
    ):
        return has_audio(decode_audio(event))
    return False


async def main(managed: bool = False, listen_seconds: float = 30) -> None:
    if not 1 <= listen_seconds <= 60:
        raise ValueError("listen_seconds must be between 1 and 60.")
    load_dotenv()
    pcm = read_pcm(Path(os.environ["FOUNDRY_VOICE_AUDIO_INPUT_PATH"]))
    model = os.environ["FOUNDRY_VOICE_LIVE_MODEL"]
    backend_model = os.environ.get("FOUNDRY_MODEL_NAME") if managed else None
    path = Path(
        os.environ.get("FOUNDRY_VOICE_LIVE_OUTPUT_PATH")
        or f"voice-live-delegation-{uuid4().hex[:8]}.wav"
    )
    replies: dict[str, str] = {}
    accepted: set[str] = set()
    delegations: dict[str, ManagedDelegation] = {}
    speech_seen = False

    async def on_event(
        connection: AsyncBetaLiveConnection, event: Mapping[str, Any]
    ) -> None:
        nonlocal speech_seen
        if managed:
            speech_seen = observe_managed(event, delegations) or speech_seen
        else:
            await reply_to_client(connection, event, replies, accepted)

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
            backend = None
            if managed:
                if backend_model is None or not backend_model.strip():
                    raise ValueError(
                        "Managed delegation requires a nonblank FOUNDRY_MODEL_NAME."
                    )
                backend = await create_owned_agent(
                    project,
                    cleanup,
                    "prompt-backend",
                    models.PromptAgentDefinition(
                        model=backend_model,
                        instructions=(
                            "Handle spoken questions delegated by a voice assistant. Return exactly two sections: "
                            "[thinking] followed by a brief task status, NOT private reasoning; then [commentary] "
                            "followed by the actual answer in one speakable sentence. Do not claim external lookups."
                        ),
                    ),
                )
            delegation = (
                models.VoiceAgentLiveManagedAgentDelegation(
                    agent_name=backend.name, agent_version=backend.version
                )
                if backend is not None
                else models.VoiceAgentLiveClientDelegation()
            )
            agent = await create_owned_agent(
                project,
                cleanup,
                "delegation",
                models.VoiceAgentLiveDefinition(
                    model_type=models.VoiceModelType.SELF_DEPLOYED,
                    model=model,
                    instructions=(
                        "Delegate every substantive spoken question to your backend. Do not invent answers or "
                        "give a spoken acknowledgement. Speak the returned commentary in one short sentence."
                    ),
                    audio=audio_settings(),
                    delegation=delegation,
                    store=False,
                ),
            )
            async with live_session(project, cleanup, agent) as (connection, started):
                if backend is not None:
                    verify_managed_session(started.session, backend)
                user_text, agent_text, count = await stream_audio(
                    connection,
                    pcm,
                    output,
                    on_event=on_event,
                    listen_seconds=listen_seconds,
                )
                if managed:
                    if (
                        not delegations
                        or not all(state.completed for state in delegations.values())
                        or not speech_seen
                    ):
                        raise RuntimeError(
                            "Missing correlated managed completion or actual frontend reply audio."
                        )
                elif not replies or accepted != set(replies):
                    raise RuntimeError(
                        "Missing client delegation or its correlated commentary acknowledgement."
                    )
    if user_text:
        print(f"Input transcript: {user_text}")
    if agent_text:
        print(f"Output transcript: {agent_text}")
    print(
        f"Captured {count} reply PCM16 bytes in {path}; session.closed was confirmed separately."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--managed",
        action="store_true",
        help="Create and pin an owned same-project prompt backend.",
    )
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=30,
        help="Capture window after input ends (1-60 seconds).",
    )
    options = parser.parse_args()
    asyncio.run(main(options.managed, options.listen_seconds))
