# Copyright (c) Microsoft. All rights reserved.

"""Shared utilities for the OpenAI Computer Tool Hosted Agent sample."""

from utils.agent_runner import COMPUTER_TOOL, run_cua_loop, stream_cua_loop
from utils.pyautogui_helper import (
    ensure_virtual_desktop,
    get_writable_output_path,
    handle_pyautogui_action,
    take_desktop_screenshot,
)
from utils.settings import (
    PROMPTS_PATH,
    SAMPLE_ROOT_DIR,
    SRC_DIR,
    get_model_deployment_name,
    get_project_client,
    get_project_endpoint,
    load_agent_instructions,
)

__all__ = [
    "COMPUTER_TOOL",
    "PROMPTS_PATH",
    "SAMPLE_ROOT_DIR",
    "SRC_DIR",
    "ensure_virtual_desktop",
    "get_model_deployment_name",
    "get_project_client",
    "get_project_endpoint",
    "get_writable_output_path",
    "handle_pyautogui_action",
    "load_agent_instructions",
    "run_cua_loop",
    "stream_cua_loop",
    "take_desktop_screenshot",
]
