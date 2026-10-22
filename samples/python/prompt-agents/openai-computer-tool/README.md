# OpenAI Computer Tool Agent (Python, Prompt Agent)

This sample provisions an **Azure AI Foundry Prompt Agent** equipped with the GA **OpenAI Computer Tool** (`ComputerTool` / `{"type": "computer"}` in `azure-ai-projects`, replacing `computer_use_preview`) and executes local desktop scenarios (**Calculator + Notepad** and **MS Paint Colored Smiley**) using **PyAutoGUI**, matching the structured `src/` layout of the C# and Python `browser-automation` samples.

## How it works

1. `hooks/postprovision.*` (or `python main.py provision`) creates the `openai-computer-agent` Prompt Agent version in Azure AI Foundry with `ComputerTool()` (`{"type": "computer"}`) and generic system instructions from `src/openai-computer-tool/prompts/base.md`.
2. `src/openai-computer-tool/main.py` invokes the deployed Prompt Agent with a scenario-specific user task prompt (`--scenario calculator` or `--scenario paint`).
3. `src/openai-computer-tool/utils/agent_runner.py` runs the multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` loop against `openai-computer-agent`.
4. `src/openai-computer-tool/utils/pyautogui_helper.py` translates each batched `computer_call` action (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) into local OS mouse and keyboard events via `pyautogui` and captures DPI-normalized desktop screenshots.

## Key files

| Path | Purpose |
| --- | --- |
| `azure.yaml` | Declarative Azure Developer CLI (`azd`) definition for the Foundry project and Prompt Agent. |
| `hooks/postprovision.*` | Provisions the `openai-computer-agent` Prompt Agent version after `azd provision`. |
| `src/openai-computer-tool/main.py` | CLI entrypoint (`provision`, `run --scenario calculator`, `run --scenario paint`, `delete`). |
| `src/openai-computer-tool/prompts/base.md` | Generic desktop automation system instructions for the Prompt Agent. |
| `src/openai-computer-tool/utils/agent_factory.py` | Creates and deletes Prompt Agent versions with `PromptAgentDefinition` and `ComputerTool()`. |
| `src/openai-computer-tool/utils/agent_runner.py` | Multi-turn `computer_call` -> `computer_call_output` execution loop and temporary screenshot file cleanup. |
| `src/openai-computer-tool/utils/pyautogui_helper.py` | PyAutoGUI action dispatcher (`click`, `drag`, `type`, `keypress`, `scroll`) and DPI screenshot helper. |
| `src/openai-computer-tool/utils/settings.py` | Environment variable and `AIProjectClient` configuration helpers. |
| `src/openai-computer-tool/scenarios/calculator_notepad.py` | Scenario 1: Launches Calculator & Notepad side-by-side and runs the calculation prompt (`347 * 29 = 10063`). |
| `src/openai-computer-tool/scenarios/paint_smiley.py` | Scenario 2: Launches MS Paint (`mspaint.exe`) and draws a centered yellow smiley face using `drag` and `click` actions. |

## Directory Structure

```text
samples/python/prompt-agents/openai-computer-tool/
├── README.md
├── azure.yaml
├── hooks/
│   ├── postprovision.ps1
│   └── postprovision.sh
└── src/
    └── openai-computer-tool/
        ├── .env.example
        ├── .gitignore
        ├── pyproject.toml
        ├── requirements.txt
        ├── main.py
        ├── prompts/
        │   └── base.md
        ├── scenarios/
        │   ├── __init__.py
        │   ├── calculator_notepad.py
        │   └── paint_smiley.py
        └── utils/
            ├── __init__.py
            ├── agent_factory.py
            ├── agent_runner.py
            ├── pyautogui_helper.py
            └── settings.py
```

## Prerequisites

- Python 3.10+ (`uv` or `pip` + `venv`)
- An Azure AI Foundry **project** with a model deployment that supports the **OpenAI Computer Tool** (`{"type": "computer"}`, such as `gpt-5.4`).
- **Azure CLI** (`az login`) and **Azure Developer CLI** (`azd`).

## Configuration

Copy `src/openai-computer-tool/.env.example` to `src/openai-computer-tool/.env`:

```dotenv
AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4
AGENT_NAME=openai-computer-agent
```

## Run

### 1. Install dependencies

```bash
cd src/openai-computer-tool
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Provision the Prompt Agent

Using Azure Developer CLI (`azd`) from the sample root:

```bash
azd up
```

Or directly via the Python CLI from `src/openai-computer-tool`:

```bash
python main.py provision
```

### 3. Run Desktop Scenarios

#### Scenario 1 — Calculator + Notepad (`--scenario calculator`)

```bash
python main.py run --scenario calculator
```

Launches Windows **Calculator** (left) and **Notepad** (right) and sends the user task prompt to `openai-computer-agent` to compute `347 * 29 = 10063`, copy the result (`Ctrl+C`), close Calculator (`Alt+F4`), paste into Notepad (`Ctrl+V`), and save `calculation_result_<timestamp>.txt` (`Ctrl+S`).

#### Scenario 2 — MS Paint Colored Smiley (`--scenario paint`)

```bash
python main.py run --scenario paint
```

Launches **Microsoft Paint (`mspaint.exe`)** with a clean white canvas and sends the user task prompt asking `openai-computer-agent` to draw a cheerful, polished yellow smiley face with a black outline, two evenly spaced oval eyes, and a curved smile using the ellipse, fill, and curve/brush tools, then save `smiley_<timestamp>.png`.

#### Custom Task Prompt

```bash
python main.py run --scenario calculator --prompt "Compute 125 * 48 in Calculator, copy the result, close Calculator, and paste it into Notepad."
```

### 4. Clean Up Agent Versions (optional)

```bash
python main.py delete
```



