# Prompt Agent with OpenAI Computer Tool (GA `computer`) — Python

This sample demonstrates how to build agents using the **OpenAI Computer Tool** (GA `ComputerTool` / `{"type": "computer"}` in `azure-ai-projects`, replacing `computer_use_preview`) with **Azure AI Foundry Prompt Agents** and the same local automation libraries used by [`openai-cua-sample-app`](https://github.com/openai/openai-cua-sample-app):

1. **`browser_playwright.py` (Browser Automation with Playwright):**
   Opens a local interactive **Sprint Task Board** (`task_board.html`) in Chromium and executes batched `computer_call` actions (`screenshot`, `double_click`, `drag`, `scroll`, `click`, `type`, `keypress`) from the **OpenAI Computer Tool** to inspect a task card, drag it to the **Done** column, scroll the release checklist, and submit the sign-off code.
2. **`desktop_pyautogui.py` (Desktop Automation with PyAutoGUI):**
   Controls Windows **Calculator** and **Notepad** on the local desktop using the **OpenAI Computer Tool** with `pyautogui` and `Pillow` (including high-DPI coordinate normalization via `pyautogui.size()`), computing `347 * 29`, copying the result from Calculator (`Ctrl+C`), closing Calculator (`Alt+F4`), pasting the result into Notepad (`Ctrl+V`), and saving a timestamped file (`Ctrl+S`).

## Directory Structure

```text
samples/python/prompt-agents/openai-computer-tool/
├── README.md               # Documentation and setup instructions
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .gitignore              # Ignores .venv, .env, and generated output files
├── cua_loop.py             # Shared Prompt Agent + OpenAI Computer Tool loop
├── browser_playwright.py   # Example 1: Playwright browser automation
├── task_board.html         # Interactive Sprint Task Board used by Example 1
└── desktop_pyautogui.py    # Example 2: PyAutoGUI Windows desktop automation
```

## Files

| File | Description |
| --- | --- |
| `cua_loop.py` | Creates the Foundry `PromptAgentDefinition` with the **OpenAI Computer Tool** (`ComputerTool()` / `{"type": "computer"}`) and runs the multi-turn `computer_call` -> batched actions -> `computer_call_output` loop. |
| `browser_playwright.py` | **Example 1:** Playwright browser automation on `task_board.html` (`double_click`, `drag`, `scroll`, `click`, `type`, `keypress`). |
| `task_board.html` | Self-contained interactive web task board used by `browser_playwright.py`. |
| `desktop_pyautogui.py` | **Example 2:** PyAutoGUI desktop automation with Windows Calculator and Notepad. |
| `requirements.txt` | Python dependencies (`azure-ai-projects`, `azure-identity`, `openai`, `playwright`, `pyautogui`, `pillow`, `python-dotenv`). |
| `.env.example` | Environment variable template. |

## Prerequisites

- Python 3.10+
- An Azure AI Foundry project endpoint with a model deployment that supports the **OpenAI Computer Tool** (`{"type": "computer"}`, such as `gpt-5.4`, `gpt-5.5`, or `gpt-5.6-sol`).
- Azure CLI signed in (`az login`) for `DefaultAzureCredential`, or `OPENAI_API_KEY` set in `.env`.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your Foundry project endpoint and model deployment name:

```bash
cp .env.example .env
```

## Running the Samples

### Example 1: Browser Automation (Playwright)

```bash
python browser_playwright.py
```

### Example 2: Desktop Automation (PyAutoGUI)

```bash
python desktop_pyautogui.py
```

