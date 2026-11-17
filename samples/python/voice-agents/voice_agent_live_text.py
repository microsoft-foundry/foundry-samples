"""Native GPT Live lifecycle, two-turn Responses history, and a local function tool.

Run: python voice_agent_live_text.py [--function-tool]
Requires azure-ai-projects[voice]==2.11.0, azure-identity, python-dotenv.
Env: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_LIVE_MODEL (existing GPT Live
deployment), FOUNDRY_MODEL_NAME (existing Responses deployment available to Live).
Uses DefaultAzureCredential and deletes only its unique, owned agent version.
Printed backend text is NOT frontend speech completion; this sample does not
play or record speech. For audio capture use voice_agent_live_audio.py.
Both variants send a second user item on the SAME Live connection and call
response.create again. Live owns the backend history; no hypothetical
previous_response_id or Realtime response command is sent.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from contextlib import AsyncExitStack
import json
import os
import re
import time
from typing import Any
from uuid import uuid4

from azure.ai.projects import models
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.aio.operations import AsyncBetaLiveConnection
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_live_util import (
    audio_clock,
    audio_settings,
    create_owned_agent,
    live_session,
    receive,
    wait_event,
)


def execute_tool(call: Mapping[str, Any]) -> str:
    """Deliberately local demo data, not a real inventory lookup."""
    if call.get("name") != "get_demo_stock":
        raise ValueError(f"Unexpected function: {call.get('name')}.")
    encoded = call.get("arguments")
    if not isinstance(encoded, str):
        raise ValueError("Function arguments must be a JSON string.")
    arguments = json.loads(encoded)
    if not isinstance(arguments, dict) or arguments != {"sku": "blue-mug"}:
        raise ValueError("get_demo_stock requires exactly sku='blue-mug'.")
    return json.dumps({"sku": "blue-mug", "quantity": 3, "source": "local demo data"})


async def receive_response(
    connection: AsyncBetaLiveConnection, deadline: float
) -> tuple[str, list[Mapping[str, Any]]]:
    """Consume granular content; lifecycle snapshots intentionally omit output."""
    response_id = None
    delegation_id = None
    text: dict[tuple[str, int], str] = {}
    calls: dict[str, Mapping[str, Any]] = {}
    while True:
        event = await receive(connection, deadline)
        if event.get("type") == "session.closed":
            raise RuntimeError("Live closed before the backend response completed.")
        if not isinstance(event, models.LiveServerEventLiveResponseEvent):
            continue
        nested = event.event
        if not isinstance(nested, Mapping):
            raise RuntimeError("Malformed backend event.")
        snapshot = nested.get("response")
        if snapshot is not None and not isinstance(snapshot, Mapping):
            raise RuntimeError("Malformed backend response snapshot.")
        if nested["type"] in ("response.created", "response.in_progress"):
            if response_id is not None and nested["type"] == "response.created":
                raise RuntimeError(
                    "Concurrent backend responses are outside this sample's single-response flow."
                )
            if response_id is None:
                # Tool continuations can begin with in_progress, without another created event.
                response_id = snapshot.get("id") if snapshot is not None else None
                if not isinstance(response_id, str) or not response_id:
                    raise RuntimeError(
                        "Backend response lifecycle omitted a usable response ID."
                    )
                delegation_id = event.delegation_id
                if delegation_id is not None and (
                    not isinstance(delegation_id, str) or not delegation_id.strip()
                ):
                    raise RuntimeError("Backend event has an invalid delegation ID.")
        if response_id is None:
            raise RuntimeError(
                f"Backend {nested['type']} arrived before a response lifecycle event."
            )
        # Granular Responses events often have neither response_id nor a response snapshot.
        # One response is active at a time; the Live envelope correlates its whole nested stream.
        identifiers = [nested["response_id"]] if "response_id" in nested else []
        if snapshot is not None and "id" in snapshot:
            identifiers.append(snapshot["id"])
        if (
            any(identifier != response_id for identifier in identifiers)
            or event.delegation_id != delegation_id
        ):
            raise RuntimeError(
                "Backend event does not match the current response/delegation."
            )
        if nested["type"] in (
            "response.output_text.delta",
            "response.output_text.done",
        ):
            item_id, content_index = nested.get("item_id"), nested.get("content_index")
            fragment = nested.get(
                "delta" if nested["type"].endswith(".delta") else "text"
            )
            if (
                not isinstance(item_id, str)
                or not item_id
                or not isinstance(content_index, int)
                or isinstance(content_index, bool)
                or content_index < 0
                or not isinstance(fragment, str)
            ):
                raise RuntimeError("Malformed backend text content.")
            key = (item_id, content_index)
            text[key] = (
                text.get(key, "") + fragment
                if nested["type"].endswith(".delta")
                else fragment
            )
        elif nested["type"] == "response.output_item.done":
            call = nested.get("item")
            if not isinstance(call, Mapping):
                raise RuntimeError("Malformed backend output item.")
            if call.get("type") == "function_call":
                call_id = call.get("call_id")
                if not isinstance(call_id, str) or not call_id or call_id in calls:
                    raise RuntimeError("Missing or repeated function call_id.")
                calls[call_id] = call
        elif nested["type"] == "response.completed":
            if snapshot is None or snapshot.get("status") != "completed":
                raise RuntimeError("Backend completion did not have status=completed.")
            return "".join(text.values()).strip(), list(calls.values())


async def run_turn(
    connection: AsyncBetaLiveConnection, use_tool: bool, *, prompt: str | None = None
) -> str:
    prompt = prompt or (
        "Use get_demo_stock for blue-mug once, then report the demo quantity."
        if use_tool
        else "Suggest one practical way to reduce meeting overload. Use one sentence."
    )
    await connection.response.item.create(
        item={
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }
    )
    await connection.response.create()
    deadline = time.monotonic() + 90
    handled: set[str] = set()
    for cycle in range(4):
        text, calls = await receive_response(connection, deadline)
        if not calls:
            if not text or (use_tool and not handled):
                raise RuntimeError(
                    "Backend returned no answer or omitted the required demo tool."
                )
            return text
        if not use_tool:
            raise RuntimeError("The text-only backend unexpectedly requested a tool.")
        if cycle == 3:
            raise RuntimeError("Exceeded the four-response tool-cycle limit.")
        # Submit outputs only after this response cycle completes; call_id is not item.id.
        for call in calls:
            if call["call_id"] in handled:
                raise RuntimeError(
                    "Backend repeated an already handled function call_id."
                )
            result = execute_tool(call)
            await connection.response.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": result,
                }
            )
            handled.add(call["call_id"])
        await connection.response.create()
    raise RuntimeError("Exceeded the four-response tool-cycle limit.")


async def run_two_turns(
    connection: AsyncBetaLiveConnection, use_tool: bool
) -> tuple[str, str]:
    """Prove continuation by asking about context absent from the second user item."""
    code = f"demo-{uuid4().hex[:8]}"
    first = await run_turn(
        connection,
        use_tool,
        prompt=(
            None
            if use_tool
            else (
                f"The meeting's local demo code is {code}. Suggest one practical way "
                "to reduce meeting overload in one sentence, including that code."
            )
        ),
    )
    second = await run_turn(
        connection,
        False,
        prompt=(
            "Using only the demo quantity returned on the previous turn, what is twice "
            "that quantity? Reply with only the integer. Do not call a tool."
            if use_tool
            else (
                "What was the local demo code in my previous message? Reply with ONLY "
                "the exact code, without extra punctuation. Do not call a tool."
            )
        ),
    )
    retained = (
        re.findall(r"\b\d+\b", second) == ["6"] or second.strip().casefold() == "six"
        if use_tool
        else code.casefold() in second.casefold()
    )
    if not retained:
        raise RuntimeError(
            "The second Responses turn did not retain the first turn's context."
        )
    return first, second


async def main(use_tool: bool = False) -> None:
    load_dotenv()
    tool = models.LiveFunctionToolInputParam(
        name="get_demo_stock",
        description="Return local demo stock for blue-mug, not production inventory.",
        parameters={
            "type": "object",
            "properties": {"sku": {"type": "string", "enum": ["blue-mug"]}},
            "required": ["sku"],
            "additionalProperties": False,
        },
        strict=True,
    )
    definition = models.VoiceAgentLiveDefinition(
        model_type=models.VoiceModelType.SELF_DEPLOYED,
        model=os.environ["FOUNDRY_VOICE_LIVE_MODEL"],
        instructions="You are a concise voice assistant. Delegate substantive questions to the backend.",
        audio=audio_settings(),
        delegation=models.VoiceAgentLiveResponsesDelegation(
            responses=models.LiveResponsesDelegationSettingsInputParam(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                instructions=(
                    "Answer briefly. If asked for demo stock, call get_demo_stock once and use its result. "
                    "For follow-ups, retain earlier messages and tool results; do not repeat a lookup "
                    "unless the user requests one."
                ),
                tools=[tool] if use_tool else [],
                parallel_tool_calls=False,
            )
        ),
        store=False,
    )
    async with (
        DefaultAzureCredential(process_timeout=60) as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            allow_preview=True,
        ) as project,
        AsyncExitStack() as cleanup,
    ):
        agent = await create_owned_agent(project, cleanup, "text", definition)
        async with live_session(project, cleanup, agent) as (connection, _):
            await connection.session.update(
                session=models.LiveSessionUpdateParams(
                    delegation=models.LiveResponsesDelegationUpdateParam(
                        responses=models.LiveResponsesDelegationSettingsUpdateInputParam(
                            max_output_tokens=256
                        )
                    )
                ),
                event_id="update-backend",
            )
            updated = await wait_event(
                connection, "session.updated", client_event_id="update-backend"
            )
            if not isinstance(updated, models.LiveServerEventLiveSessionUpdated):
                raise RuntimeError(
                    "Expected the SDK's typed session.updated acknowledgement."
                )
            async with audio_clock(connection):
                await connection.session.instructions.append(
                    content="Do not invent external facts.",
                    delegation_id=None,
                    event_id="append-instructions",
                )
                appended = await wait_event(
                    connection,
                    "session.instructions.appended",
                    client_event_id="append-instructions",
                )
                if not isinstance(
                    appended, models.LiveServerEventLiveInstructionsAppended
                ):
                    raise RuntimeError(
                        "Expected the SDK's typed instructions.appended acknowledgement."
                    )
            first, second = await run_two_turns(connection, use_tool)
            print(f"Responses backend turn 1 (not speech completion): {first}")
            print(f"Responses backend turn 2 (not speech completion): {second}")
            print("Confirmed two-turn Responses continuation on the same Live session.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--function-tool",
        action="store_true",
        help="Run the bounded local demo function-tool cycle.",
    )
    asyncio.run(main(parser.parse_args().function_tool))
