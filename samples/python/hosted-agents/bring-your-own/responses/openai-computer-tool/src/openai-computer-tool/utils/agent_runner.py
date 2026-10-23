# Copyright (c) Microsoft. All rights reserved.

"""Shared multi-turn execution loop for the OpenAI Computer Tool Hosted Agent.

Invokes the Microsoft Foundry model deployment with `tools=[{"type": "computer"}]`,
dispatches each action in `computer_call.actions` to the PyAutoGUI helper
(`utils/pyautogui_helper.py`), and returns a desktop screenshot in
`computer_call_output` until the task completes.
"""

import asyncio
import base64
import logging
import time
from typing import Any, AsyncIterator, Callable

from openai import OpenAI

from utils.settings import (
    get_model_deployment_name,
    get_project_client,
    load_agent_instructions,
)

logger = logging.getLogger(__name__)

COMPUTER_TOOL: dict[str, str] = {"type": "computer"}


def build_screenshot_output(
    openai_client: OpenAI,
    screenshot_b64: str,
    uploaded_file_ids: list[str],
) -> dict[str, str]:
    """Build `computer_screenshot` output using a data URI or uploaded file ID for larger screenshots."""
    if len(screenshot_b64) <= 64_000:
        return {
            "type": "computer_screenshot",
            "image_url": f"data:image/png;base64,{screenshot_b64}",
        }

    uploaded = openai_client.files.create(
        file=("screenshot.png", base64.b64decode(screenshot_b64), "image/png"),
        purpose="assistants",
    )
    uploaded_file_ids.append(uploaded.id)
    return {
        "type": "computer_screenshot",
        "file_id": uploaded.id,
    }


def _cleanup_uploaded_files(openai_client: OpenAI, uploaded_file_ids: list[str]) -> None:
    """Delete temporary screenshot files uploaded during the computer-use loop."""
    for file_id in uploaded_file_ids:
        try:
            openai_client.files.delete(file_id)
        except Exception:
            pass


def run_cua_loop(
    prompt: str | list[dict[str, Any]],
    handle_action: Callable[[dict[str, Any]], None],
    take_screenshot: Callable[[], str],
    max_turns: int = 30,
) -> str:
    """Run the synchronous `computer_call` -> `computer_call_output` loop."""
    model = get_model_deployment_name()
    instructions = load_agent_instructions()
    uploaded_file_ids: list[str] = []

    logger.info("Invoking Computer Tool model=%s", model)

    with get_project_client() as project_client:
        openai_client = project_client.get_openai_client()
        try:
            response = openai_client.responses.create(
                model=model,
                instructions=instructions,
                input=prompt,
                tools=[COMPUTER_TOOL],
                store=False,
            )

            for turn in range(1, max_turns + 1):
                computer_calls = [item for item in response.output if item.type == "computer_call"]
                if not computer_calls:
                    logger.info("Agent completed in %d turn(s).", turn)
                    return response.output_text

                call = computer_calls[0]
                if getattr(call, "pending_safety_checks", None):
                    checks = ", ".join(f"{c.code}: {c.message}" for c in call.pending_safety_checks)
                    raise RuntimeError(f"Refusing to execute computer_call with pending safety checks: {checks}")

                logger.info("[Turn %d] Executing %d action(s) (call_id=%s)", turn, len(call.actions), call.call_id)

                for action in call.actions:
                    action_dict = action.model_dump(exclude_none=True)
                    logger.info("  -> %s", action_dict)
                    handle_action(action_dict)
                    if action_dict.get("type") != "screenshot":
                        time.sleep(0.35)

                call_output: dict[str, Any] = {
                    "type": "computer_call_output",
                    "call_id": call.call_id,
                    "output": build_screenshot_output(openai_client, take_screenshot(), uploaded_file_ids),
                }

                response = openai_client.responses.create(
                    model=model,
                    instructions=instructions,
                    previous_response_id=response.id,
                    input=[call_output],
                    tools=[COMPUTER_TOOL],
                    store=False,
                )

            remaining_calls = [item for item in response.output if item.type == "computer_call"]
            if remaining_calls:
                raise RuntimeError(
                    f"Reached max_turns={max_turns} with pending computer_call actions still remaining."
                )

            return response.output_text
        finally:
            _cleanup_uploaded_files(openai_client, uploaded_file_ids)


async def stream_cua_loop(
    input_items: list[dict[str, Any]],
    handle_action: Callable[[dict[str, Any]], None],
    take_screenshot: Callable[[], str],
    max_turns: int = 30,
) -> AsyncIterator[tuple[str, Any]]:
    """Run the async Computer Tool loop for `ResponsesAgentServerHost` streaming."""
    model = get_model_deployment_name()
    instructions = load_agent_instructions()
    uploaded_file_ids: list[str] = []
    conversation = list(input_items)

    with get_project_client() as project_client:
        openai_client = project_client.get_openai_client()
        try:
            for turn in range(1, max_turns + 1):
                response = await asyncio.to_thread(
                    openai_client.responses.create,
                    model=model,
                    instructions=instructions,
                    input=conversation,
                    tools=[COMPUTER_TOOL],
                    store=False,
                )

                computer_calls = [
                    item for item in response.output if getattr(item, "type", None) == "computer_call"
                ]
                if not computer_calls:
                    yield "reply", response.output_text or "(No response)"
                    return

                call = computer_calls[0]
                if getattr(call, "pending_safety_checks", None):
                    checks = ", ".join(f"{c.code}: {c.message}" for c in call.pending_safety_checks)
                    raise RuntimeError(f"Refusing to execute computer_call with pending safety checks: {checks}")

                action_dicts = [action.model_dump(exclude_none=True) for action in call.actions]
                yield "log", f"🖥️ Turn {turn}: executing {len(action_dicts)} computer action(s)\n"

                for action_dict in action_dicts:
                    logger.info("[turn %d] action=%s", turn, action_dict)
                    await asyncio.to_thread(handle_action, action_dict)
                    if action_dict.get("type") != "screenshot":
                        await asyncio.sleep(0.35)

                screenshot_b64 = await asyncio.to_thread(take_screenshot)
                screenshot_output = await asyncio.to_thread(
                    build_screenshot_output, openai_client, screenshot_b64, uploaded_file_ids
                )

                conversation.append(call.model_dump(exclude_none=True))
                conversation.append(
                    {
                        "type": "computer_call_output",
                        "call_id": call.call_id,
                        "output": screenshot_output,
                    }
                )

            yield "reply", f"Reached max_turns={max_turns} before the desktop task completed."
        finally:
            await asyncio.to_thread(_cleanup_uploaded_files, openai_client, uploaded_file_ids)
