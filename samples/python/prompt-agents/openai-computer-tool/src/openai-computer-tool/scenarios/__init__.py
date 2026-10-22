"""Desktop task scenarios for the OpenAI Computer Tool Prompt Agent sample."""

from scenarios.calculator_notepad import build_calculator_prompt, run_calculator_scenario
from scenarios.paint_smiley import DEFAULT_PAINT_PROMPT, run_paint_scenario

__all__ = [
    "DEFAULT_PAINT_PROMPT",
    "build_calculator_prompt",
    "run_calculator_scenario",
    "run_paint_scenario",
]
