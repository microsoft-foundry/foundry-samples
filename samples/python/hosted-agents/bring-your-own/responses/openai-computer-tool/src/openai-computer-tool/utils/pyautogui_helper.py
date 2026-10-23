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
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def get_writable_output_path(filename: str = "paint_smiley.png") -> Path:
    """Return a writable path for saving Paint output (falls back to /tmp in read-only containers)."""
    src_dir = Path(__file__).resolve().parent.parent
    if os.access(src_dir, os.W_OK):
        return src_dir / filename
    return Path(tempfile.gettempdir()) / filename

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
_pyautogui_available: bool | None = None


class _HeadlessPaintDesktop:
    """In-memory 1280x800 virtual Paint desktop fallback when Xvfb/X11 is unavailable."""

    WIDTH = 1280
    HEIGHT = 800
    CANVAS_BOX = (20, 84, 1260, 780)
    BUTTONS: list[tuple[str, str, str, tuple[int, int, int, int]]] = [
        ("Oval", "tool", "oval", (16, 32, 96, 64)),
        ("Brush", "tool", "brush", (104, 32, 184, 64)),
        ("Fill", "tool", "fill", (192, 32, 272, 64)),
        ("Yellow", "color", "#FFD700", (288, 32, 368, 64)),
        ("Black", "color", "#000000", (376, 32, 456, 64)),
        ("Blue", "color", "#1E90FF", (464, 32, 544, 64)),
        ("Red", "color", "#E53935", (552, 32, 632, 64)),
        ("Green", "color", "#43A047", (640, 32, 720, 64)),
        ("Clear", "action", "clear", (736, 32, 816, 64)),
        ("Save", "action", "save", (824, 32, 904, 64)),
    ]

    def __init__(self, output_file: Path | None = None) -> None:
        self.output_file = output_file or get_writable_output_path("paint_smiley.png")
        self.tool = "oval"
        self.color = "#FFD700"
        self.cursor_x = 640
        self.cursor_y = 430
        self.saved = False
        cw = self.CANVAS_BOX[2] - self.CANVAS_BOX[0]
        ch = self.CANVAS_BOX[3] - self.CANVAS_BOX[1]
        self.canvas = Image.new("RGB", (cw, ch), "white")

    def set_output_file(self, output_file: Path | None) -> None:
        if output_file is not None:
            if not os.access(output_file.parent, os.W_OK):
                output_file = get_writable_output_path(output_file.name)
            if output_file != self.output_file:
                self.output_file = output_file
                self.clear()

    def clear(self) -> None:
        cw = self.CANVAS_BOX[2] - self.CANVAS_BOX[0]
        ch = self.CANVAS_BOX[3] - self.CANVAS_BOX[1]
        self.canvas = Image.new("RGB", (cw, ch), "white")
        self.saved = False

    def save(self) -> None:
        try:
            self.canvas.save(self.output_file, format="PNG")
        except OSError:
            self.output_file = Path(tempfile.gettempdir()) / self.output_file.name
            self.canvas.save(self.output_file, format="PNG")
        self.saved = True

    def _to_canvas(self, x: int, y: int) -> tuple[int, int]:
        cx0, cy0, cx1, cy1 = self.CANVAS_BOX
        return (max(0, min(cx1 - cx0 - 1, x - cx0)), max(0, min(cy1 - cy0 - 1, y - cy0)))

    def _in_canvas(self, x: int, y: int) -> bool:
        cx0, cy0, cx1, cy1 = self.CANVAS_BOX
        return cx0 <= x <= cx1 and cy0 <= y <= cy1

    def click(self, x: int, y: int) -> None:
        self.cursor_x, self.cursor_y = int(x), int(y)
        for _label, kind, val, (x0, y0, x1, y1) in self.BUTTONS:
            if x0 <= x <= x1 and y0 <= y <= y1:
                if kind == "tool":
                    self.tool = val
                elif kind == "color":
                    self.color = val
                elif val == "clear":
                    self.clear()
                elif val == "save":
                    self.save()
                return
        if self._in_canvas(x, y):
            cx, cy = self._to_canvas(x, y)
            draw = ImageDraw.Draw(self.canvas)
            if self.tool == "fill":
                try:
                    ImageDraw.floodfill(self.canvas, (cx, cy), Image.new("RGB", (1, 1), self.color).getpixel((0, 0)))
                except Exception:
                    pass
            elif self.tool == "brush":
                draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=self.color)
            self.save()

    def drag(self, path: list[dict[str, int]]) -> None:
        if not path:
            return
        x0, y0 = int(path[0]["x"]), int(path[0]["y"])
        x1, y1 = int(path[-1]["x"]), int(path[-1]["y"])
        self.cursor_x, self.cursor_y = x1, y1
        if not (self._in_canvas(x0, y0) or self._in_canvas(x1, y1)):
            return
        draw = ImageDraw.Draw(self.canvas)
        if self.tool == "oval":
            cx0, cy0 = self._to_canvas(min(x0, x1), min(y0, y1))
            cx1, cy1 = self._to_canvas(max(x0, x1), max(y0, y1))
            if cx1 - cx0 >= 2 and cy1 - cy0 >= 2:
                draw.ellipse(
                    (cx0, cy0, cx1, cy1),
                    fill=self.color,
                    outline="#000000",
                    width=4,
                )
        else:
            pts = [self._to_canvas(int(p["x"]), int(p["y"])) for p in path]
            if len(pts) >= 2:
                draw.line(pts, fill=self.color, width=6, joint="curve")
                for px, py in pts:
                    draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=self.color)
        self.save()

    def keypress(self, keys: list[str]) -> None:
        norm = [k.lower() for k in keys]
        if ("ctrl" in norm or "control" in norm) and "s" in norm:
            self.save()

    def render_screenshot(self) -> Image.Image:
        screen = Image.new("RGB", (self.WIDTH, self.HEIGHT), "#f0f0f0")
        draw = ImageDraw.Draw(screen)
        draw.rectangle((0, 0, self.WIDTH, 24), fill="#2b579a")
        draw.text((12, 5), "Paint - OpenAI Computer Tool Virtual Desktop (1280x800)", fill="white")
        draw.rectangle((0, 24, self.WIDTH, 74), fill="#e0e0e0")

        for label, kind, val, (x0, y0, x1, y1) in self.BUTTONS:
            is_selected = (kind == "tool" and self.tool == val) or (kind == "color" and self.color == val)
            bg = val if kind == "color" else ("#cce4f7" if is_selected else "#ffffff")
            fg = "white" if (kind == "color" and val != "#FFD700") else "black"
            outline = "#005a9e" if is_selected else "#777777"
            draw.rectangle((x0, y0, x1, y1), fill=bg, outline=outline, width=3 if is_selected else 1)
            draw.text((x0 + 14, y0 + 9), label, fill=fg)

        status = f"Tool: {self.tool} | Color: {self.color} | {'Saved: ' + self.output_file.name if self.saved else 'Ready'}"
        draw.text((925, 42), status, fill="#222222")

        cx0, cy0, cx1, cy1 = self.CANVAS_BOX
        draw.rectangle((cx0 - 1, cy0 - 1, cx1 + 1, cy1 + 1), outline="#888888", width=1)
        screen.paste(self.canvas, (cx0, cy0))

        # Draw visible cursor marker
        x, y = self.cursor_x, self.cursor_y
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline="#ff0000", width=2)
        return screen


_headless_desktop = _HeadlessPaintDesktop()

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
    if sys.platform != "win32":
        import shutil, subprocess
        if shutil.which("scrot"):
            subprocess.run(["scrot", "-o", output_path], check=False)
            status_var.set(f"Saved: {output_path}")
            return
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
    """Ensure Xvfb and the lightweight Tkinter Paint canvas are running on Linux, or initialize the virtual fallback."""
    global _xvfb_process, _paint_process, _pyautogui_available
    _headless_desktop.set_output_file(output_file)
    if sys.platform == "win32":
        _pyautogui_available = os.environ.get("USE_NATIVE_WINDOWS_PAINT", "").strip() == "1"
        return

    os.environ.setdefault("DISPLAY", ":99")
    display = os.environ["DISPLAY"]
    xauth = Path(tempfile.gettempdir()) / ".Xauthority"
    os.environ.setdefault("XAUTHORITY", str(xauth))
    try:
        if not xauth.exists():
            xauth.touch()
    except OSError:
        pass

    if shutil.which("Xvfb") and (_xvfb_process is None or _xvfb_process.poll() is not None):
        pgrep = subprocess.run(["pgrep", "-x", "Xvfb"], capture_output=True, check=False)
        if pgrep.returncode != 0:
            _xvfb_process = subprocess.Popen(
                ["Xvfb", display, "-screen", "0", "1280x800x24", "-ac", "+extension", "GLX", "+render", "-noreset"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.8)

    display_num = display.lstrip(":").split(".")[0] or "99"
    has_x11_socket = Path(f"/tmp/.X11-unix/X{display_num}").exists()
    if not has_x11_socket:
        _pyautogui_available = False
        return

    if _paint_process is None or _paint_process.poll() is not None:
        target = str(output_file or (Path(__file__).resolve().parent.parent / "paint_smiley.png"))
        _paint_process = subprocess.Popen(
            [sys.executable, "-c", _TK_PAINT_SCRIPT, target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.8)


def _get_pyautogui() -> Any | None:
    """Import and configure `pyautogui` when an OS/X11 display is reachable; otherwise return None for headless fallback."""
    global _pyautogui_available
    ensure_virtual_desktop()
    if _pyautogui_available is False:
        return None
    try:
        import pyautogui

        pyautogui.FAILSAFE = sys.platform == "win32"
        pyautogui.PAUSE = 0.05
        _pyautogui_available = True
        return pyautogui
    except Exception as exc:
        logger.info("PyAutoGUI X11 display unavailable (%s); using built-in virtual Paint desktop.", exc)
        _pyautogui_available = False
        return None


def handle_pyautogui_action(action: dict[str, Any]) -> None:
    """Execute a single OpenAI Computer Tool `computer_call` action with PyAutoGUI or the virtual Paint desktop."""
    pyautogui = _get_pyautogui()
    if pyautogui is None:
        match action["type"]:
            case "screenshot":
                pass
            case "click" | "double_click" | "triple_click":
                _headless_desktop.click(int(action["x"]), int(action["y"]))
            case "move":
                _headless_desktop.cursor_x = int(action["x"])
                _headless_desktop.cursor_y = int(action["y"])
            case "drag":
                _headless_desktop.drag(action["path"])
            case "keypress":
                _headless_desktop.keypress(action["keys"])
            case "wait":
                time.sleep(min(action.get("ms", 500) / 1000.0, 1.0))
            case _:
                pass
        return

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
    """Capture a desktop screenshot scaled to logical coordinates (or from the virtual Paint desktop)."""
    pyautogui = _get_pyautogui()
    if pyautogui is None:
        image = _headless_desktop.render_screenshot()
    elif sys.platform != "win32" and shutil.which("scrot"):
        tmp_shot = Path(tempfile.gettempdir()) / "_cua_screenshot.png"
        subprocess.run(
            ["scrot", "-o", str(tmp_shot)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with Image.open(tmp_shot) as captured:
            image = captured.convert("RGB")
        screen_size = pyautogui.size()
        if image.size != screen_size:
            image = image.resize(screen_size, Image.Resampling.LANCZOS)
    else:
        image = pyautogui.screenshot()
        screen_size = pyautogui.size()
        if image.size != screen_size:
            image = image.resize(screen_size, Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
