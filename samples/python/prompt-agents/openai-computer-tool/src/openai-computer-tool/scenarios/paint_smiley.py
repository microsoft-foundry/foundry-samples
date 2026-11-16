"""MS Paint colored smiley face scenario for the OpenAI Computer Tool Prompt Agent.

The agent opens Microsoft Paint itself by using Windows Search (or pressing the
Windows key, searching for Paint, and pressing Enter), draws a centered yellow
smiley face on a clean white canvas, and saves the drawing to `paint_smiley_<timestamp>.png`.
"""

import time
from pathlib import Path

from utils import handle_pyautogui_action, run_cua_loop, take_desktop_screenshot


def build_paint_prompt(output_file: Path) -> str:
    """Build the default MS Paint smiley task prompt with the target output file path."""
    return (
        "Open Windows Search (click the Start/Search button on the taskbar or press the WIN key), "
        "search for 'Paint' (mspaint), and press Enter to open MS Paint (press Ctrl+N if needed for a clean canvas). "
        "In MS Paint, draw a cheerful, polished smiley face centered on a clean white canvas. "
        "Use a large yellow circle with a smooth black outline, two evenly spaced black oval eyes, "
        "and a curved black smile. Keep the features balanced and the lines neat. "
        "Use the ellipse and curve tools where possible, and leave some white space around the face. "
        "Don’t add text or extra decorations. "
        f"When finished drawing, save the image (press Ctrl+S, type the full path '{output_file}', and press Enter)."
    )


def run_paint_scenario(prompt: str | None = None) -> Path:
    """Execute the MS Paint smiley drawing scenario via the Prompt Agent and save the image."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).resolve().parent.parent / f"paint_smiley_{timestamp}.png"
    task_prompt = prompt or build_paint_prompt(output_file)

    run_cua_loop(
        prompt=task_prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
        max_turns=40,
    )

    if output_file.exists():
        print(f"\nSaved image ({output_file.name}): {output_file} ({output_file.stat().st_size} bytes)")
    return output_file

