"""Example 1: Browser Automation with Azure AI Foundry Prompt Agent + Playwright.

Opens a local interactive Sprint Task Board (`task_board.html`) and lets the Prompt Agent
complete 4 browser interactions using the GA `computer` tool:
1. `double_click` a task card to inspect details
2. `drag` the task card from "In Progress" to "Done"
3. `scroll` the checklist panel to reveal the sign-off code
4. `click` + `type` + `keypress` (Enter) to submit the completion note
"""

import base64
import time
from pathlib import Path
from typing import Any

import dotenv
from playwright.sync_api import Page, sync_playwright

from cua_loop import create_agent_and_client, run_cua_loop

dotenv.load_dotenv()

INSTRUCTIONS = """\
You are a browser computer-use agent operating a 1024x768 Sprint Task Board.
Complete all 4 steps on the page:
1. Double-click the blue task card ("Task #101: Validate GA Computer Tool") to inspect its details.
2. Drag the task card from the "In Progress" column on the left into the "Done" column on the right.
3. Scroll down inside the "Release Checklist" panel on the bottom-left to reveal the FINAL SIGN-OFF CODE.
4. Click the "Completion Note" input on the bottom-right, type the exact sign-off code, and press Enter.
Once all 4 status badges at the top show DONE, summarize what you completed.
"""

PROMPT = (
    "Complete the 4 sprint task board steps: double-click Task #101 to inspect it, "
    "drag it to the Done column, scroll the Release Checklist to find the sign-off code, "
    "and submit that code in the Completion Note input."
)

KEY_MAP = {
    "ENTER": "Enter",
    "RETURN": "Enter",
    "TAB": "Tab",
    "SPACE": " ",
    "BACKSPACE": "Backspace",
    "DELETE": "Delete",
    "ESC": "Escape",
    "ESCAPE": "Escape",
    "UP": "ArrowUp",
    "DOWN": "ArrowDown",
    "LEFT": "ArrowLeft",
    "RIGHT": "ArrowRight",
    "PAGEUP": "PageUp",
    "PAGEDOWN": "PageDown",
    "HOME": "Home",
    "END": "End",
    "CTRL": "Control",
    "CONTROL": "Control",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "META": "Meta",
    "CMD": "Meta",
    "WIN": "Meta",
}


def handle_browser_action(page: Page, action: dict[str, Any]) -> None:
    """Map a single GA `computer_call` action to Playwright mouse/keyboard calls."""
    match action["type"]:
        case "screenshot":
            pass

        case "click":
            button = "middle" if action.get("button") == "wheel" else action.get("button", "left")
            page.mouse.click(action["x"], action["y"], button=button)

        case "double_click":
            page.mouse.dblclick(action["x"], action["y"])

        case "triple_click":
            page.mouse.click(action["x"], action["y"], click_count=3)

        case "move":
            page.mouse.move(action["x"], action["y"])

        case "drag":
            path = action["path"]
            page.mouse.move(path[0]["x"], path[0]["y"])
            page.mouse.down()
            for point in path[1:]:
                page.mouse.move(point["x"], point["y"], steps=10)
            page.mouse.up()

        case "scroll":
            page.mouse.move(action["x"], action["y"])
            page.mouse.wheel(action.get("scroll_x", 0), action.get("scroll_y", 0))

        case "type":
            page.keyboard.type(action["text"], delay=15)

        case "keypress":
            keys = [KEY_MAP.get(k.upper(), k) for k in action["keys"]]
            page.keyboard.press("+".join(keys))

        case "wait":
            time.sleep(action.get("ms", 1000) / 1000.0)


def take_browser_screenshot(page: Page) -> str:
    """Capture the Playwright viewport as a base64 PNG string."""
    png_bytes = page.screenshot(type="png")
    return base64.b64encode(png_bytes).decode("ascii")


def main() -> None:
    openai_client, model, extra_body = create_agent_and_client(
        agent_name="foundry-cua-browser-agent",
        instructions=INSTRUCTIONS,
    )

    task_board_url = (Path(__file__).resolve().parent / "task_board.html").as_uri()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.goto(task_board_url)

        run_cua_loop(
            openai_client=openai_client,
            model=model,
            instructions=INSTRUCTIONS,
            prompt=PROMPT,
            handle_action=lambda action: handle_browser_action(page, action),
            take_screenshot=lambda: take_browser_screenshot(page),
            extra_body=extra_body,
        )

        time.sleep(2.0)
        browser.close()


if __name__ == "__main__":
    main()

