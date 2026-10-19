"""Shared Azure AI Foundry Prompt Agent + GA `computer` tool loop.

Shows the four core steps of a Computer Use Agent (CUA) in Azure AI Foundry:
1. Define a Prompt Agent with `PromptAgentDefinition` and `ComputerTool()` (`{"type": "computer"}`).
2. Send the user prompt to the Responses API.
3. Execute each action in `computer_call.actions` (`click`, `double_click`, `drag`, `scroll`, `type`, `keypress`, `wait`).
4. Return a base64 PNG screenshot in `computer_call_output` until the agent finishes.
"""

import base64
import os
import time
from typing import Any, Callable

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ComputerTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from openai import OpenAI


def create_agent_and_client(
    agent_name: str,
    instructions: str,
) -> tuple[OpenAI, str, dict[str, Any]]:
    """Register the Prompt Agent with the GA `ComputerTool` and return an OpenAI client, model, and extra_body."""
    endpoint = os.environ["PROJECT_ENDPOINT"].rstrip("/")
    model = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-5.4")

    # 1. Define the Prompt Agent with the GA `computer` tool ({"type": "computer"})
    agent_definition = PromptAgentDefinition(
        model=model,
        instructions=instructions,
        tools=[ComputerTool()],
    )

    # 2. Authenticate with DefaultAzureCredential and register the Prompt Agent version
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        openai_client = OpenAI(
            base_url=f"{endpoint}/openai/v1",
            api_key=api_key,
            default_headers={"api-key": api_key},
        )
        return openai_client, model, {}

    project_client = AIProjectClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
    )
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=agent_definition,
    )
    print(f"Created Prompt Agent: {agent.name} (version {agent.version})")
    extra_body = {"agent_reference": {"name": agent.name, "type": "agent_reference"}}

    return project_client.get_openai_client(), model, extra_body


def run_cua_loop(
    openai_client: OpenAI,
    model: str,
    instructions: str,
    prompt: str,
    handle_action: Callable[[dict[str, Any]], None],
    take_screenshot: Callable[[], str],
    extra_body: dict[str, Any] | None = None,
    max_turns: int = 10,
) -> str:
    """Run the multi-turn `computer_call` -> action execution -> `computer_call_output` loop."""
    computer_tool = ComputerTool().as_dict()  # {"type": "computer"}
    request_kwargs: dict[str, Any] = {"extra_body": extra_body} if extra_body else {"model": model, "tools": [computer_tool]}

    print(f"\nUser Prompt: {prompt}\n")
    response = openai_client.responses.create(
        instructions=instructions,
        input=prompt,
        **request_kwargs,
    )

    for turn in range(1, max_turns + 1):
        computer_calls = [item for item in response.output if item.type == "computer_call"]
        if not computer_calls:
            print(f"\nAgent Final Response:\n{response.output_text}")
            return response.output_text

        call = computer_calls[0]
        if getattr(call, "pending_safety_checks", None):
            checks = ", ".join(f"{c.code}: {c.message}" for c in call.pending_safety_checks)
            raise RuntimeError(f"Refusing to execute computer_call with pending safety checks: {checks}")

        print(f"[Turn {turn}] Executing {len(call.actions)} action(s) (call_id={call.call_id}):")

        # Execute each batched action returned by the model
        for action in call.actions:
            action_dict = action.model_dump(exclude_none=True)
            print(f"  -> {action_dict}")
            handle_action(action_dict)
            if action_dict.get("type") != "screenshot":
                time.sleep(0.2)

        # Capture the updated screen state and send it back in `computer_call_output`.
        # Small screenshots are sent inline as a data URI; large desktop screenshots are
        # uploaded via the Files API to stay under the 65 KB URI limit.
        screenshot_b64 = take_screenshot()
        if len(screenshot_b64) <= 60_000:
            screenshot_output = {
                "type": "computer_screenshot",
                "image_url": f"data:image/png;base64,{screenshot_b64}",
            }
        else:
            uploaded = openai_client.files.create(
                file=("screenshot.png", base64.b64decode(screenshot_b64), "image/png"),
                purpose="assistants",
            )
            screenshot_output = {
                "type": "computer_screenshot",
                "file_id": uploaded.id,
            }

        call_output: dict[str, Any] = {
            "type": "computer_call_output",
            "call_id": call.call_id,
            "output": screenshot_output,
        }

        response = openai_client.responses.create(
            previous_response_id=response.id,
            instructions=instructions,
            input=[call_output],
            **request_kwargs,
        )

    return response.output_text

