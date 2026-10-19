"""Example 2: Windows Desktop Automation with Azure AI Foundry Prompt Agent + PyAutoGUI.

Launches Windows Calculator and Notepad and lets the Prompt Agent interact with the
desktop through screenshots, mouse actions, and keyboard input using PyAutoGUI.
"""

import base64
import ctypes
import io
import subprocess
import time
from pathlib import Path
from typing import Any

import dotenv
import pyautogui
from PIL import Image

from cua_loop import create_agent_and_client, run_cua_loop

dotenv.load_dotenv()

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

INSTRUCTIONS = """\
You are a Windows desktop computer-use agent.
Calculator (on the left) and Notepad (on the right, with a pre-created calculation_result_<timestamp>.txt file already open) are visible on the desktop:
1. Click the Calculator window, compute 347 * 29, press Ctrl+C to copy the result, and press Alt+F4 to close Calculator.
2. Click inside the Notepad text editor, type "Foundry CUA Desktop Check: 347 * 29 = ", press Ctrl+V to paste the result, and press Ctrl+S to save the file directly (no Save As dialog is needed).
3. Once saved, summarize what you completed and state the calculated result.
"""

PROMPT = (
    "Compute 347 * 29 in Calculator, copy the result, close Calculator, "
    "then write 'Foundry CUA Desktop Check: 347 * 29 = <result>' in Notepad and save the file (Ctrl+S)."
)

KEY_MAP = {
    "ENTER": "enter",
    "RETURN": "enter",
    "TAB": "tab",
    "SPACE": "space",
    "BACKSPACE": "backspace",
    "DELETE": "delete",
    "ESC": "esc",
    "ESCAPE": "esc",
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "CTRL": "ctrl",
    "CONTROL": "ctrl",
    "ALT": "alt",
    "SHIFT": "shift",
    "WIN": "win",
    "META": "win",
}


def handle_desktop_action(action: dict[str, Any]) -> None:
    """Map a single GA `computer_call` action to PyAutoGUI mouse/keyboard calls."""
    match action["type"]:
        case "screenshot":
            pass

        case "click":
            button = "middle" if action.get("button") == "wheel" else action.get("button", "left")
            pyautogui.click(x=action["x"], y=action["y"], button=button)

        case "double_click":
            pyautogui.doubleClick(x=action["x"], y=action["y"])

        case "triple_click":
            pyautogui.tripleClick(x=action["x"], y=action["y"])

        case "move":
            pyautogui.moveTo(x=action["x"], y=action["y"], duration=0.1)

        case "drag":
            path = action["path"]
            pyautogui.moveTo(path[0]["x"], path[0]["y"])
            pyautogui.mouseDown()
            for point in path[1:]:
                pyautogui.moveTo(point["x"], point["y"], duration=0.15)
            pyautogui.mouseUp()

        case "scroll":
            pyautogui.moveTo(x=action["x"], y=action["y"])
            scroll_y = action.get("scroll_y", 0)
            if scroll_y:
                clicks = int(-scroll_y / 100) or (-1 if scroll_y > 0 else 1)
                pyautogui.scroll(clicks, x=action["x"], y=action["y"])
            scroll_x = action.get("scroll_x", 0)
            if scroll_x and hasattr(pyautogui, "hscroll"):
                hclicks = int(scroll_x / 100) or (1 if scroll_x > 0 else -1)
                pyautogui.hscroll(hclicks, x=action["x"], y=action["y"])

        case "type":
            pyautogui.write(action["text"], interval=0.02)

        case "keypress":
            keys = [KEY_MAP.get(k.upper(), k.lower()) for k in action["keys"]]
            pyautogui.hotkey(*keys)

        case "wait":
            time.sleep(action.get("ms", 1000) / 1000.0)


def take_desktop_screenshot() -> str:
    """Capture a desktop screenshot scaled to `pyautogui.size()` logical coordinates."""
    image = pyautogui.screenshot()
    screen_size = pyautogui.size()
    if image.size != screen_size:
        image = image.resize(screen_size, Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def launch_side_by_side(output_file: Path) -> None:
    """Close prior instances and open Calculator (left) and Notepad (right) with `output_file`."""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process CalculatorApp,Notepad -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }; "
         "Remove-Item \"$env:LOCALAPPDATA\\Packages\\Microsoft.WindowsNotepad_*\\LocalState\\TabState\\*\" -Force -ErrorAction SilentlyContinue"],
        check=False,
    )
    output_file.write_text("", encoding="utf-8")
    subprocess.Popen(["calc.exe"])
    subprocess.Popen(["notepad.exe", str(output_file)])
    time.sleep(1.5)

    user32 = ctypes.windll.user32
    calc_hwnd = user32.FindWindowW("ApplicationFrameWindow", "Calculator") or user32.FindWindowW(None, "Calculator")
    notepad_hwnd = user32.FindWindowW("Notepad", None)

    if calc_hwnd:
        user32.ShowWindow(calc_hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(calc_hwnd, -1, 80, 80, 420, 560, 0x0040)  # HWND_TOPMOST | SWP_SHOWWINDOW
    if notepad_hwnd:
        user32.ShowWindow(notepad_hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(notepad_hwnd, -1, 540, 80, 760, 560, 0x0040)  # HWND_TOPMOST | SWP_SHOWWINDOW
    time.sleep(0.3)


def main() -> None:
    openai_client, model, extra_body = create_agent_and_client(
        agent_name="foundry-cua-desktop-agent",
        instructions=INSTRUCTIONS,
    )

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).resolve().parent / f"calculation_result_{timestamp}.txt"
    launch_side_by_side(output_file)

    run_cua_loop(
        openai_client=openai_client,
        model=model,
        instructions=INSTRUCTIONS,
        prompt=PROMPT,
        handle_action=handle_desktop_action,
        take_screenshot=take_desktop_screenshot,
        extra_body=extra_body,
    )

    if output_file.exists():
        print(f"\nSaved file ({output_file.name}): {output_file.read_text(encoding='utf-8').strip()!r}")


if __name__ == "__main__":
    main()

