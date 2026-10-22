"""Calculator + Notepad desktop scenario for the OpenAI Computer Tool Prompt Agent.

The agent opens both Calculator and Notepad itself by using Windows Search
(clicking the Windows Start/Search button or pressing the Windows key, typing the
app name, and pressing Enter), then saves the calculation result in Notepad to
`calculation_result_<timestamp>.txt`.
"""

import time
from pathlib import Path

from utils import handle_pyautogui_action, run_cua_loop, take_desktop_screenshot


def build_calculator_prompt(output_file: Path) -> str:
    """Build the default Calculator + Notepad task prompt with the target output file path."""
    return (
        "On the Windows desktop: "
        "1) Open Windows Search (click the Start/Search button on the taskbar or press the WIN key), "
        "search for 'Calculator', and press Enter to open it. "
        "2) In Calculator, compute 347 * 29, press Ctrl+C to copy the result, and press Alt+F4 to close Calculator. "
        "3) Open Windows Search again, search for 'Notepad', and press Enter to open it. "
        "4) In a clean Notepad tab (press Ctrl+N if needed), type 'Foundry CUA Desktop Check: 347 * 29 = ' "
        "and press Ctrl+V to paste the copied result. "
        f"5) Save the file in Notepad (press Ctrl+Shift+S or Ctrl+S, type the full path '{output_file}', and press Enter). "
        "6) Once saved, summarize what you completed and state the calculated result."
    )


def run_calculator_scenario(prompt: str | None = None) -> Path:
    """Execute the Calculator + Notepad scenario where the agent opens both apps via Windows Search and saves the file."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).resolve().parent.parent / f"calculation_result_{timestamp}.txt"
    task_prompt = prompt or build_calculator_prompt(output_file)

    run_cua_loop(
        prompt=task_prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
        max_turns=20,
    )

    if output_file.exists():
        print(f"\nSaved file ({output_file.name}): {output_file.read_text(encoding='utf-8').strip()!r}")
    return output_file

