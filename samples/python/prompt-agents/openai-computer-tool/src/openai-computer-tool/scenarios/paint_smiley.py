"""MS Paint colored smiley face scenario for the OpenAI Computer Tool Prompt Agent.

The agent opens Microsoft Paint itself by using Windows Search (or pressing the
Windows key, searching for Paint, and pressing Enter), then draws a centered yellow
smiley face on a clean white canvas.
"""

from utils import handle_pyautogui_action, run_cua_loop, take_desktop_screenshot

DEFAULT_PAINT_PROMPT = (
    "Open Windows Search (click the Start/Search button on the taskbar or press the WIN key), "
    "search for 'Paint' (mspaint), and press Enter to open MS Paint (press Ctrl+N if needed for a clean canvas). "
    "In MS Paint, draw a cheerful, polished smiley face centered on a clean white canvas. "
    "Use a large yellow circle with a smooth black outline, two evenly spaced black oval eyes, "
    "and a curved black smile. Keep the features balanced and the lines neat. "
    "Use the ellipse and curve tools where possible, and leave some white space around the face. "
    "Don’t add text or extra decorations."
)


def run_paint_scenario(prompt: str | None = None) -> None:
    """Execute the MS Paint smiley drawing scenario via the Prompt Agent."""
    task_prompt = prompt or DEFAULT_PAINT_PROMPT
    run_cua_loop(
        prompt=task_prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
        max_turns=40,
    )

