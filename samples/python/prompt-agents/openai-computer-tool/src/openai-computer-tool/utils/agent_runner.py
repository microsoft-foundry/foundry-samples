"""Shared multi-turn execution loop for the Azure AI Foundry Prompt Agent + OpenAI Computer Tool.

Invokes the provisioned Prompt Agent with a user `prompt`, dispatches each action in
`computer_call.actions` to the local PyAutoGUI helper (`utils/pyautogui_helper.py`),
and returns a desktop screenshot in `computer_call_output` until the task completes.
"""

import base64
import time
from typing import Any, Callable

from openai import OpenAI

from utils.settings import AGENT_NAME, get_model_deployment_name, get_project_client


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
    prompt: str,
    handle_action: Callable[[dict[str, Any]], None],
    take_screenshot: Callable[[], str],
    agent_name: str = AGENT_NAME,
    max_turns: int = 10,
) -> str:
    """Send `prompt` to the deployed Prompt Agent and execute `computer_call` actions locally."""
    model = get_model_deployment_name()
    agent_ref = {"agent_reference": {"type": "agent_reference", "name": agent_name}}
    uploaded_file_ids: list[str] = []

    print(f"Invoking Prompt Agent '{agent_name}' (model={model})")
    print(f"User Prompt: {prompt}\n", flush=True)

    with get_project_client() as project_client:
        openai_client = project_client.get_openai_client()
        try:
            response = openai_client.responses.create(
                input=prompt,
                extra_body=agent_ref,
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
                    "output": build_screenshot_output(openai_client, take_screenshot(), uploaded_file_ids),
                }

                response = openai_client.responses.create(
                    previous_response_id=response.id,
                    input=[call_output],
                    extra_body=agent_ref,
                )

            remaining_calls = [item for item in response.output if item.type == "computer_call"]
            if remaining_calls:
                raise RuntimeError(
                    f"Reached max_turns={max_turns} with pending computer_call actions still remaining."
                )

            print(f"\nAgent Final Response:\n{response.output_text}", flush=True)
            return response.output_text
        finally:
            _cleanup_uploaded_files(openai_client, uploaded_file_ids)
