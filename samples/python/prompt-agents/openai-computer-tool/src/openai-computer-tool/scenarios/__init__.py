"""Desktop task scenarios for the OpenAI Computer Tool Prompt Agent sample."""

from scenarios.calculator_notepad import DEFAULT_CALCULATOR_PROMPT, run_calculator_scenario
from scenarios.paint_smiley import DEFAULT_PAINT_PROMPT, run_paint_scenario

__all__ = [
    "DEFAULT_CALCULATOR_PROMPT",
    "DEFAULT_PAINT_PROMPT",
    "run_calculator_scenario",
    "run_paint_scenario",
]
