"""MS Paint colored smiley face scenario for the OpenAI Computer Tool Prompt Agent."""

import ctypes
import subprocess
import time
from pathlib import Path

from PIL import Image

from utils import SRC_DIR, handle_pyautogui_action, run_cua_loop, take_desktop_screenshot

DEFAULT_PAINT_PROMPT = (
    "In MS Paint, draw a cheerful, polished smiley face centered on a clean white canvas. "
    "Use a large yellow circle with a smooth black outline, two evenly spaced black oval eyes, "
    "and a curved black smile. Keep the features balanced and the lines neat. "
    "Use the ellipse and curve tools where possible, and leave some white space around the face. "
    "Don’t add text or extra decorations."
)


def _find_paint_window_by_title(substring: str) -> int:
    """Find a visible MS Paint window whose title contains `substring`."""
    user32 = ctypes.windll.user32
    found_hwnd = 0

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        nonlocal found_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        if cls_buf.value != "MSPaintApp":
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        if substring.lower() in title_buf.value.lower():
            found_hwnd = hwnd
            return False
        return True

    user32.EnumWindows(enum_proc, 0)
    return found_hwnd


def launch_mspaint(canvas_file: Path) -> None:
    """Create a blank white PNG canvas and open it in `mspaint.exe` without terminating existing Paint windows."""
    existing = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Process mspaint -ErrorAction SilentlyContinue"],
        capture_output=True,
        text=True,
        check=False,
    )
    if existing.stdout.strip():
        raise RuntimeError(
            "Microsoft Paint (mspaint) is already running. Please save and close existing Paint windows before running this sample."
        )

    Image.new("RGB", (800, 600), color=(255, 255, 255)).save(canvas_file, format="PNG")
    subprocess.Popen(["mspaint.exe", str(canvas_file)])

    user32 = ctypes.windll.user32
    paint_hwnd = 0
    for _ in range(30):
        time.sleep(0.2)
        paint_hwnd = _find_paint_window_by_title(canvas_file.name)
        if paint_hwnd:
            break

    topmost = ctypes.c_void_p(-1)
    if paint_hwnd:
        user32.ShowWindow(paint_hwnd, 9)  # SW_RESTORE
        user32.MoveWindow(paint_hwnd, 100, 60, 1100, 760, True)
        user32.SetWindowPos(paint_hwnd, topmost, 100, 60, 1100, 760, 0x0040)
    time.sleep(0.6)


def run_paint_scenario(prompt: str | None = None) -> Path:
    """Launch MS Paint with a blank canvas and execute the smiley drawing prompt via the Prompt Agent."""
    task_prompt = prompt or DEFAULT_PAINT_PROMPT
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    canvas_file = SRC_DIR / f"smiley_{timestamp}.png"
    launch_mspaint(canvas_file)

    run_cua_loop(
        prompt=task_prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
        max_turns=15,
    )

    if canvas_file.exists():
        print(f"\nSaved MS Paint drawing: {canvas_file}")
    return canvas_file
