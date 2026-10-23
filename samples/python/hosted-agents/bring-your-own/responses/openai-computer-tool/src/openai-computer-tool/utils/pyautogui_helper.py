# Copyright (c) Microsoft. All rights reserved.

"""PyAutoGUI and Xvfb desktop helper for the OpenAI Computer Tool Hosted Agent.

Translates each batched action returned by the GA OpenAI Computer Tool (`computer_call`:
`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`)
into OS-level mouse and keyboard operations via PyAutoGUI, captures DPI-normalized
desktop screenshots for `computer_call_output`, and manages a lightweight Tkinter Paint
canvas when running inside a Linux `Xvfb` container without Playwright.
"""

import base64
import io
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
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

_xvfb_process: subprocess.Popen[bytes] | None = None
_paint_process: subprocess.Popen[bytes] | None = None

_TK_PAINT_SCRIPT = r"""
import os
import sys
import tkinter as tk
from PIL import ImageGrab

output_path = sys.argv[1] if len(sys.argv) > 1 else "paint_smiley.png"

root = tk.Tk()
root.title("Paint")
root.geometry("1280x800+0+0")
root.configure(bg="#f0f0f0")

state = {"tool": "oval", "color": "#FFD700", "outline": "#000000", "start_x": 0, "start_y": 0, "current_item": None}

toolbar = tk.Frame(root, bg="#e0e0e0", height=56)
toolbar.pack(side=tk.TOP, fill=tk.X)

status_var = tk.StringVar(value=f"Tool: oval | Fill: #FFD700 | Save target: {output_path}")

def set_tool(tool_name):
    state["tool"] = tool_name
    status_var.set(f"Tool: {state['tool']} | Color: {state['color']} | Save: Ctrl+S -> {output_path}")

def set_color(hex_color):
    state["color"] = hex_color
    status_var.set(f"Tool: {state['tool']} | Color: {state['color']} | Save: Ctrl+S -> {output_path}")

canvas = tk.Canvas(root, bg="white", width=1240, height=700, highlightthickness=1, highlightbackground="#888888")
canvas.pack(padx=20, pady=12, fill=tk.BOTH, expand=True)

def clear_canvas():
    canvas.delete("all")

def save_canvas(event=None):
    root.update_idletasks()
    x = canvas.winfo_rootx()
    y = canvas.winfo_rooty()
    w = x + canvas.winfo_width()
    h = y + canvas.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, w, h))
    img.save(output_path, "PNG")
    status_var.set(f"Saved: {output_path}")

for label, tname in [("Oval", "oval"), ("Brush", "brush"), ("Fill", "fill")]:
    tk.Button(toolbar, text=label, width=8, command=lambda n=tname: set_tool(n)).pack(side=tk.LEFT, padx=4, pady=8)

for label, col in [("Yellow", "#FFD700"), ("Black", "#000000"), ("Blue", "#1E90FF"), ("Red", "#E53935"), ("Green", "#43A047")]:
    tk.Button(toolbar, text=label, bg=col, fg="white" if col != "#FFD700" else "black", width=8, command=lambda c=col: set_color(c)).pack(side=tk.LEFT, padx=4, pady=8)

tk.Button(toolbar, text="Clear", width=8, command=clear_canvas).pack(side=tk.LEFT, padx=4, pady=8)
tk.Button(toolbar, text="Save", width=8, command=save_canvas).pack(side=tk.LEFT, padx=4, pady=8)
tk.Label(toolbar, textvariable=status_var, bg="#e0e0e0").pack(side=tk.RIGHT, padx=12)

def on_press(event):
    state["start_x"], state["start_y"] = event.x, event.y
    if state["tool"] == "fill":
        items = canvas.find_closest(event.x, event.y)
        if items:
            canvas.itemconfig(items[0], fill=state["color"])
    elif state["tool"] == "oval":
        fill_col = state["color"] if state["color"] != "#000000" else "#000000"
        state["current_item"] = canvas.create_oval(
            event.x, event.y, event.x, event.y,
            fill=fill_col, outline="#000000", width=4
        )

def on_drag(event):
    if state["tool"] == "brush":
        canvas.create_line(
            state["start_x"], state["start_y"], event.x, event.y,
            fill=state["color"], width=5, capstyle=tk.ROUND, smooth=True
        )
        state["start_x"], state["start_y"] = event.x, event.y
    elif state["tool"] == "oval" and state["current_item"] is not None:
        canvas.coords(state["current_item"], state["start_x"], state["start_y"], event.x, event.y)

def on_release(event):
    state["current_item"] = None

canvas.bind("<ButtonPress-1>", on_press)
canvas.bind("<B1-Motion>", on_drag)
canvas.bind("<ButtonRelease-1>", on_release)
root.bind("<Control-s>", save_canvas)
root.bind("<Control-S>", save_canvas)

root.mainloop()
"""


def ensure_virtual_desktop(output_file: Path | None = None) -> None:
    """Ensure Xvfb and the lightweight Tkinter Paint canvas are running on Linux."""
    global _xvfb_process, _paint_process
    if sys.platform == "win32":
        return

    os.environ.setdefault("DISPLAY", ":99")
    display = os.environ["DISPLAY"]
    xauth = Path.home() / ".Xauthority"
    if not xauth.exists():
        xauth.touch()

    if shutil.which("Xvfb") and (_xvfb_process is None or _xvfb_process.poll() is not None):
        pgrep = subprocess.run(["pgrep", "-x", "Xvfb"], capture_output=True, check=False)
        if pgrep.returncode != 0:
            _xvfb_process = subprocess.Popen(
                ["Xvfb", display, "-screen", "0", "1280x800x24", "-ac", "+extension", "GLX", "+render", "-noreset"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.8)

    if _paint_process is None or _paint_process.poll() is not None:
        target = str(output_file or (Path(__file__).resolve().parent.parent / "paint_smiley.png"))
        _paint_process = subprocess.Popen(
            [sys.executable, "-c", _TK_PAINT_SCRIPT, target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.8)


def _get_pyautogui() -> Any:
    """Import and configure `pyautogui` lazily so headless CI compile/import checks succeed."""
    ensure_virtual_desktop()
    import pyautogui

    pyautogui.FAILSAFE = sys.platform == "win32"
    pyautogui.PAUSE = 0.05
    return pyautogui


def handle_pyautogui_action(action: dict[str, Any]) -> None:
    """Execute a single OpenAI Computer Tool `computer_call` action with PyAutoGUI."""
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
