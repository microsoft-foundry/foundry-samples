"""Run the Calculator + Notepad desktop task using the provisioned OpenAI Computer Tool Prompt Agent.

Prerequisites:
    1. Provision the Prompt Agent once:
           python provision_agent.py
    2. Invoke the agent with a user task prompt:
           python main.py

The deployed agent has generic system instructions (`agents/computer_agent/instructions.md`).
The specific task is supplied purely via the user `prompt` below, and all `computer_call`
actions are executed locally using `common/pyautogui_helper.py` (PyAutoGUI).
"""

import argparse
import ctypes
import subprocess
import time
from pathlib import Path

import dotenv

from common import handle_pyautogui_action, run_cua_loop, take_desktop_screenshot
from sample_config import ROOT_DIR

dotenv.load_dotenv()

DEFAULT_PROMPT = (
    "Calculator (on the left) and Notepad (on the right, with a pre-created calculation_result_<timestamp>.txt "
    "file already open) are visible on the desktop. "
    "1) Click the Calculator window, compute 347 * 29, press Ctrl+C to copy the result, and press Alt+F4 to close Calculator. "
    "2) Click inside the Notepad text editor, type 'Foundry CUA Desktop Check: 347 * 29 = ', press Ctrl+V to paste the result, "
    "and press Ctrl+S to save the file directly. "
    "3) Once saved, summarize what you completed and state the calculated result."
)


def _find_window_by_title_substring(substring: str, class_name: str | None = None) -> int:
    """Find a visible top-level window whose title contains `substring`."""
    user32 = ctypes.windll.user32
    found_hwnd = 0

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        nonlocal found_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        if class_name:
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value != class_name:
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


def launch_side_by_side(output_file: Path) -> None:
    """Open Calculator (left) and Notepad (right) with `output_file` without terminating existing user apps."""
    output_file.write_text("", encoding="utf-8")
    subprocess.Popen(["calc.exe"])
    subprocess.Popen(["notepad.exe", str(output_file)])

    user32 = ctypes.windll.user32
    calc_hwnd = 0
    notepad_hwnd = 0
    for _ in range(25):
        time.sleep(0.2)
        if not calc_hwnd:
            calc_hwnd = (
                user32.FindWindowW("ApplicationFrameWindow", "Calculator")
                or user32.FindWindowW(None, "Calculator")
            )
        if not notepad_hwnd:
            notepad_hwnd = _find_window_by_title_substring(output_file.name, class_name="Notepad")
        if calc_hwnd and notepad_hwnd:
            break

    topmost = ctypes.c_void_p(-1)
    if calc_hwnd:
        user32.ShowWindow(calc_hwnd, 9)  # SW_RESTORE
        user32.MoveWindow(calc_hwnd, 80, 80, 420, 560, True)
        user32.SetWindowPos(calc_hwnd, topmost, 80, 80, 420, 560, 0x0040)
    if notepad_hwnd:
        user32.ShowWindow(notepad_hwnd, 9)  # SW_RESTORE
        user32.MoveWindow(notepad_hwnd, 540, 80, 760, 560, True)
        user32.SetWindowPos(notepad_hwnd, topmost, 540, 80, 760, 560, 0x0040)
    time.sleep(0.4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke the OpenAI Computer Tool Prompt Agent on a desktop task.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Task prompt sent to the Prompt Agent.")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = ROOT_DIR / f"calculation_result_{timestamp}.txt"
    launch_side_by_side(output_file)

    run_cua_loop(
        prompt=args.prompt,
        handle_action=handle_pyautogui_action,
        take_screenshot=take_desktop_screenshot,
    )

    if output_file.exists():
        print(f"\nSaved file ({output_file.name}): {output_file.read_text(encoding='utf-8').strip()!r}")


if __name__ == "__main__":
    main()
