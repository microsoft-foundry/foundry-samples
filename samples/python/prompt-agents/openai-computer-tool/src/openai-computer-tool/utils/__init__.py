"""Shared utilities for the OpenAI Computer Tool Prompt Agent sample."""

from utils.agent_factory import delete_agent, provision_agent
from utils.agent_runner import run_cua_loop
from utils.pyautogui_helper import handle_pyautogui_action, take_desktop_screenshot
from utils.settings import (
    AGENT_NAME,
    PROMPTS_PATH,
    SAMPLE_ROOT_DIR,
    SRC_DIR,
    get_model_deployment_name,
    get_project_client,
    get_project_endpoint,
    load_agent_instructions,
)

__all__ = [
    "AGENT_NAME",
    "PROMPTS_PATH",
    "SAMPLE_ROOT_DIR",
    "SRC_DIR",
    "delete_agent",
    "get_model_deployment_name",
    "get_project_client",
    "get_project_endpoint",
    "handle_pyautogui_action",
    "load_agent_instructions",
    "provision_agent",
    "run_cua_loop",
    "take_desktop_screenshot",
]
