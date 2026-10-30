# Copyright (c) Microsoft. All rights reserved.

"""OpenAI Computer Tool — Bring Your Own Responses Hosted Agent.

Hosts an OpenAI Responses protocol endpoint (`ResponsesAgentServerHost` on port 8088)
that invokes a Microsoft Foundry model deployment with the GA OpenAI Computer Tool
(`{"type": "computer"}`) and executes `computer_call` actions on the virtual (`Xvfb`)
or local desktop using PyAutoGUI.

Can also be executed directly from the command line with `--local`:
    python main.py --local
    python main.py --local --prompt "Draw a yellow smiley face on the Paint canvas and save it."
"""

import argparse
import asyncio
import logging
import time
from pathlib import Path

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses.models import get_input_expanded

from scenarios import build_paint_prompt, run_paint_scenario
from utils import (
    ensure_virtual_desktop,
    get_writable_output_path,
    handle_pyautogui_action,
    stream_cua_loop,
    take_desktop_screenshot,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_ROLE_MAP = {"output_text": "assistant", "input_text": "user"}


def _get_input_text(request: CreateResponse) -> str | None:
    """Extract the user input text from a Responses API request payload."""
    value = request.get("input")
    if isinstance(value, str):
        return value
    for item in get_input_expanded(request):
        content = item.get("content")
        if isinstance(content, str):
            return content
        for part in content or []:
            if text := part.get("text"):
                return text
    return None


def _build_input(current_input: str, history: list) -> list[dict]:
    """Convert platform conversation history and current input into Responses API input items."""
    input_items: list[dict] = []
    for item in history:
        for content in item.get("content") or []:
            role = _ROLE_MAP.get(content.get("type"))
            text = content.get("text")
            if role and text:
                input_items.append({"role": role, "content": text})
    input_items.append({"role": "user", "content": current_input})
    return input_items


app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(
        default_fetch_history_count=10,
        sse_keep_alive_interval_seconds=15,
    ),
)


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    """Handle an incoming Responses protocol request using the GA OpenAI Computer Tool loop."""
    stream = ResponseEventStream(
        response_id=context.response_id,
        request=request,
    )
    yield stream.emit_created()
    yield stream.emit_in_progress()

    user_input = (_get_input_text(request) or "").strip()
    verbose_mode = user_input.startswith("/verbose")
    if verbose_mode:
        user_input = user_input.replace("/verbose", "", 1).strip()

    output_file = get_writable_output_path(f"paint_smiley_{time.strftime('%Y%m%d_%H%M%S')}.png")
    ensure_virtual_desktop(output_file=output_file)

    if not user_input or user_input.lower() in {"paint_smiley", "smiley"}:
        user_input = build_paint_prompt(output_file)

    try:
        history = await context.get_history()
    except Exception as exc:
        logger.warning("get_history failed; continuing without history: %s", exc)
        history = []

    input_items = _build_input(user_input, history)
    final_reply = ""

    async for kind, value in stream_cua_loop(
        input_items=input_items,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
    ):
        if cancellation_signal.is_set():
            yield stream.emit_incomplete()
            return
        if kind == "log" and verbose_mode:
            for event in stream.output_item_message(value):
                yield event
        elif kind == "reply":
            final_reply = value

    if cancellation_signal.is_set():
        yield stream.emit_incomplete()
        return

    if output_file.exists():
        final_reply = f"{final_reply}\n\nSaved image: `{output_file.name}` ({output_file.stat().st_size} bytes)"

    for event in stream.output_item_message(final_reply or "Task completed."):
        yield event
    yield stream.emit_completed()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the OpenAI Computer Tool Hosted Agent server or execute the Paint Smiley scenario locally."
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run the Paint Smiley desktop scenario directly in CLI mode instead of starting the HTTP server.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional custom desktop task prompt (implies --local when provided).",
    )
    args, unknown = parser.parse_known_args()

    if args.local or args.prompt:
        run_paint_scenario(prompt=args.prompt)
    else:
        app.run()


if __name__ == "__main__":
    main()
