"""Local PyAutoGUI helper for executing OpenAI Computer Tool (`computer_call`) actions on the desktop.

Translates each batched action returned by the Azure AI Foundry Prompt Agent
(`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`)
into OS-level mouse and keyboard operations via PyAutoGUI, and captures DPI-normalized
desktop screenshots for `computer_call_output`.
"""

import base64
import io
import time
from typing import Any

from PIL import Image

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
    "PAGEUP": "pageup",
    "PAGEDOWN": "pagedown",
    "HOME": "home",
    "END": "end",
    "CTRL": "ctrl",
    "CONTROL": "ctrl",
    "ALT": "alt",
    "SHIFT": "shift",
    "WIN": "win",
    "META": "win",
    "CMD": "win",
}


def _get_pyautogui() -> Any:
    """Import and configure `pyautogui` lazily so headless CI compile/import checks succeed."""
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


def handle_pyautogui_action(action: dict[str, Any]) -> None:
    """Execute a single OpenAI Computer Tool `computer_call` action locally with PyAutoGUI."""
    pyautogui = _get_pyautogui()
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
            pyautogui.moveTo(path[0]["x"], path[0]["y"], duration=0.1)
            pyautogui.mouseDown(button="left")
            time.sleep(0.05)
            for point in path[1:]:
                pyautogui.moveTo(point["x"], point["y"], duration=0.12)
            time.sleep(0.05)
            pyautogui.mouseUp(button="left")

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
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
            if keys == ["win"]:
                time.sleep(0.6)

        case "wait":
            time.sleep(action.get("ms", 1000) / 1000.0)


def take_desktop_screenshot() -> str:
    """Capture a desktop screenshot scaled to `pyautogui.size()` logical coordinates."""
    pyautogui = _get_pyautogui()
    image = pyautogui.screenshot()
    screen_size = pyautogui.size()
    if image.size != screen_size:
        image = image.resize(screen_size, Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
