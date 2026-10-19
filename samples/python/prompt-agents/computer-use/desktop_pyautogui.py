"""Example 2: Windows Desktop Automation with Azure AI Foundry Prompt Agent + PyAutoGUI.

Launches Windows Calculator and Notepad and lets the Prompt Agent interact with the
desktop through screenshots, mouse actions, and keyboard input using PyAutoGUI.
"""

import base64
import io
import subprocess
import time
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
Calculator and Notepad are open on the desktop:
1. Click the Calculator window to focus it, compute 347 * 29, and press Ctrl+C to copy the result from Calculator.
2. Click inside the Notepad text area, type "Foundry CUA Desktop Check: 347 * 29 = ", and paste (Ctrl+V) or type the result shown in Calculator.
3. Once the full line is visible in Notepad, summarize what you completed and state the calculated result.
"""

PROMPT = (
    "Use Calculator to compute 347 * 29, copy the result from Calculator, "
    "and write 'Foundry CUA Desktop Check: 347 * 29 = <result>' in Notepad."
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
            pyautogui.scroll(-action.get("scroll_y", 0), x=action["x"], y=action["y"])

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


def main() -> None:
    openai_client, model = create_agent_and_client(
        agent_name="foundry-cua-desktop-agent",
        instructions=INSTRUCTIONS,
    )

    subprocess.Popen(["calc.exe"])
    subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)

    run_cua_loop(
        openai_client=openai_client,
        model=model,
        instructions=INSTRUCTIONS,
        prompt=PROMPT,
        handle_action=handle_desktop_action,
        take_screenshot=take_desktop_screenshot,
    )


if __name__ == "__main__":
    main()

