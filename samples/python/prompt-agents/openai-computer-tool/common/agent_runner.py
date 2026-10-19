"""Shared multi-turn execution loop for the Azure AI Foundry Prompt Agent + OpenAI Computer Tool.

Invokes the provisioned Prompt Agent with a user `prompt`, dispatches each action in
`computer_call.actions` to the local PyAutoGUI helper (`common/pyautogui_helper.py`),
and returns a desktop screenshot in `computer_call_output` until the task completes.
"""

import base64
import time
from typing import Any, Callable

from azure.ai.projects.models import ComputerTool
from openai import OpenAI

from sample_config import AGENT_NAME, get_openai_client_and_agent_ref, load_agent_instructions


def build_screenshot_output(openai_client: OpenAI, screenshot_b64: str) -> dict[str, str]:
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
    return {
        "type": "computer_screenshot",
        "file_id": uploaded.id,
    }


def run_cua_loop(
    prompt: str,
    handle_action: Callable[[dict[str, Any]], None],
    take_screenshot: Callable[[], str],
    agent_name: str = AGENT_NAME,
    max_turns: int = 10,
) -> str:
    """Send `prompt` to the deployed Prompt Agent and execute `computer_call` actions locally."""
    openai_client, model, extra_body = get_openai_client_and_agent_ref(agent_name=agent_name)
    instructions = load_agent_instructions()
    computer_tool = ComputerTool().as_dict()  # {"type": "computer"}

    request_kwargs: dict[str, Any] = (
        {"extra_body": extra_body}
        if extra_body
        else {"model": model, "instructions": instructions, "tools": [computer_tool]}
    )

    print(f"Invoking Prompt Agent '{agent_name}' (model={model})")
    print(f"User Prompt: {prompt}\n", flush=True)

    response = openai_client.responses.create(
        reasoning={"effort": "low"},
        input=prompt,
        **request_kwargs,
    )

    for turn in range(1, max_turns + 1):
        computer_calls = [item for item in response.output if item.type == "computer_call"]
        if not computer_calls:
            print(f"\nAgent Final Response:\n{response.output_text}", flush=True)
            return response.output_text

        call = computer_calls[0]
        if getattr(call, "pending_safety_checks", None):
            checks = ", ".join(f"{c.code}: {c.message}" for c in call.pending_safety_checks)
            raise RuntimeError(f"Refusing to execute computer_call with pending safety checks: {checks}")

        print(f"[Turn {turn}] Executing {len(call.actions)} action(s) (call_id={call.call_id}):", flush=True)

        for action in call.actions:
            action_dict = action.model_dump(exclude_none=True)
            print(f"  -> {action_dict}", flush=True)
            handle_action(action_dict)
            if action_dict.get("type") != "screenshot":
                time.sleep(0.35)

        call_output: dict[str, Any] = {
            "type": "computer_call_output",
            "call_id": call.call_id,
            "output": build_screenshot_output(openai_client, take_screenshot()),
        }

        response = openai_client.responses.create(
            previous_response_id=response.id,
            reasoning={"effort": "low"},
            input=[call_output],
            **request_kwargs,
        )

    return response.output_text

