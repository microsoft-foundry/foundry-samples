"""Run the MS Paint colored smiley face drawing task using the provisioned OpenAI Computer Tool Prompt Agent.

Prerequisites:
    1. Provision the Prompt Agent once:
           python provision_agent.py
    2. Invoke the agent with the MS Paint colored smiley user prompt:
           python paint_smiley.py

The deployed agent has generic system instructions (`agents/computer_agent/instructions.md`).
The colored smiley face drawing task is supplied purely via the user `prompt` below, and all
`computer_call` actions (`click`, `drag`, `keypress`) are executed locally using
`common/pyautogui_helper.py` (PyAutoGUI).
"""

import argparse
import ctypes
import subprocess
import time
from pathlib import Path

import dotenv
from PIL import Image

from common import handle_pyautogui_action, run_cua_loop, take_desktop_screenshot
from sample_config import ROOT_DIR

dotenv.load_dotenv()

DEFAULT_PROMPT = (
    "Microsoft Paint (mspaint) is open on the desktop with a blank white canvas already loaded. "
    "Draw a colored smiley face on the MS Paint canvas: "
    "1) Select the Oval shape tool (or Brush), draw a large circle in the center of the canvas, "
    "select the Fill with color (bucket) tool, pick Yellow from the color palette, and fill the circle yellow. "
    "2) Switch back to Black and the Brush tool to draw two eyes and a big curved smile inside the yellow circle. "
    "3) Press Ctrl+S to save the image file directly, then summarize the colored smiley face you drew."
)


def launch_mspaint(canvas_file: Path) -> None:
    """Close prior MS Paint instances, create a blank white PNG canvas, and open it in `mspaint.exe`."""
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process mspaint -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }",
        ],
        check=False,
    )

    Image.new("RGB", (800, 600), color=(255, 255, 255)).save(canvas_file, format="PNG")
    subprocess.Popen(["mspaint.exe", str(canvas_file)])

    user32 = ctypes.windll.user32
    paint_hwnd = 0
    for _ in range(30):
        time.sleep(0.2)
        paint_hwnd = user32.FindWindowW("MSPaintApp", None) or user32.FindWindowW(None, "Paint")
        if paint_hwnd:
            break

    topmost = ctypes.c_void_p(-1)
    if paint_hwnd:
        user32.ShowWindow(paint_hwnd, 9)  # SW_RESTORE
        user32.MoveWindow(paint_hwnd, 100, 60, 1100, 760, True)
        user32.SetWindowPos(paint_hwnd, topmost, 100, 60, 1100, 760, 0x0040)
    time.sleep(0.6)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoke the OpenAI Computer Tool Prompt Agent to draw a colored smiley face in MS Paint."
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Task prompt sent to the Prompt Agent.")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    canvas_file = ROOT_DIR / f"smiley_{timestamp}.png"
    launch_mspaint(canvas_file)

    run_cua_loop(
        prompt=args.prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
        max_turns=15,
    )

    if canvas_file.exists():
        print(f"\nSaved MS Paint drawing: {canvas_file}")


if __name__ == "__main__":
    main()
