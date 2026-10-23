# Copyright (c) Microsoft. All rights reserved.

"""Paint colored smiley face scenario for the OpenAI Computer Tool Hosted Agent.

On a Linux container desktop (`Xvfb`), uses the open Tkinter Paint canvas window;
on Windows, opens Microsoft Paint (`mspaint.exe`) via Windows Search, draws a
centered yellow smiley face on a clean white canvas, and saves `paint_smiley_<timestamp>.png`.
"""

import os
import sys
import time
from pathlib import Path

from utils import (
    ensure_virtual_desktop,
    get_writable_output_path,
    handle_pyautogui_action,
    run_cua_loop,
    take_desktop_screenshot,
)


def build_paint_prompt(output_file: Path | None = None) -> str:
    """Build the default Paint smiley task prompt for the current platform."""
    target = output_file or get_writable_output_path(f"paint_smiley_{time.strftime('%Y%m%d_%H%M%S')}.png")
    if sys.platform == "win32" and os.environ.get("USE_NATIVE_WINDOWS_PAINT", "").strip() == "1":
        return (
            "Open Windows Search (click the Start/Search button on the taskbar or press the WIN key), "
            "search for 'Paint' (mspaint), and press Enter to open MS Paint (press Ctrl+N if needed for a clean canvas). "
            "In MS Paint, draw a cheerful, polished smiley face centered on a clean white canvas. "
            "Use a large yellow circle with a smooth black outline, two evenly spaced black oval eyes, "
            "and a curved black smile. Keep the features balanced and the lines neat. "
            "Use the ellipse and curve tools where possible, and leave some white space around the face. "
            "Don’t add text or extra decorations. "
            f"When finished drawing, save the image (press Ctrl+S, type the full path '{target}', and press Enter)."
        )
    return (
        "On the open Paint Canvas window, draw a cheerful, polished yellow smiley face centered on the white canvas: "
        "1. Click 'Oval' and 'Yellow' in the top toolbar, then drag a large circle in the center of the white canvas. "
        "2. Click 'Black' in the top toolbar, then drag two evenly spaced oval eyes inside the upper half of the face. "
        "3. Click 'Brush' in the top toolbar, then drag a curved black smile across the lower half of the face. "
        f"4. Click 'Save' (or press Ctrl+S) to save the finished drawing to '{target}'."
    )


def run_paint_scenario(prompt: str | None = None) -> Path:
    """Execute the Paint smiley drawing scenario and save the resulting PNG image."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = get_writable_output_path(f"paint_smiley_{timestamp}.png")
    ensure_virtual_desktop(output_file=output_file)
    task_prompt = prompt or build_paint_prompt(output_file)

    reply = run_cua_loop(
        prompt=task_prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
        max_turns=35,
    )
    print(f"\nAgent Final Response:\n{reply}", flush=True)

    if output_file.exists():
        print(f"\nSaved image ({output_file.name}): {output_file} ({output_file.stat().st_size} bytes)")
    return output_file
