"""Desktop task scenarios for the OpenAI Computer Tool Prompt Agent sample."""

from scenarios.calculator_notepad import build_calculator_prompt, run_calculator_scenario
from scenarios.paint_smiley import build_paint_prompt, run_paint_scenario

__all__ = [
    "build_calculator_prompt",
    "build_paint_prompt",
    "run_calculator_scenario",
    "run_paint_scenario",
]
