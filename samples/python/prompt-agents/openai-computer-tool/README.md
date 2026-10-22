<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# OpenAI Computer Tool Agent (Python, Prompt Agent)

This sample provisions a **Microsoft Foundry Prompt Agent** equipped with the GA **OpenAI Computer Tool** (`ComputerTool` / `{"type": "computer"}` in `azure-ai-projects`, replacing `computer_use_preview`) and executes local desktop scenarios (**Calculator + Notepad** and **MS Paint Colored Smiley**) using **PyAutoGUI**, matching the structured `src/` layout of the C# and Python `browser-automation` samples.

## What this sample demonstrates

- Provisioning a Microsoft Foundry **Prompt Agent** with `PromptAgentDefinition` and `ComputerTool()` (`{"type": "computer"}`)
- Separating agent provisioning (`utils/agent_factory.py`), generic system instructions (`prompts/base.md`), and task-specific user prompts (`scenarios/`)
- Multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` execution loop (`utils/agent_runner.py`) with automatic temporary screenshot file cleanup
- Local OS action translation (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`) and DPI-normalized screenshot capture via **PyAutoGUI** (`utils/pyautogui_helper.py`)

## How it works

1. `hooks/postprovision.*` (or `python main.py provision`) creates the `openai-computer-agent` Prompt Agent version in Microsoft Foundry with `ComputerTool()` (`{"type": "computer"}`) and generic system instructions from `src/openai-computer-tool/prompts/base.md`.
2. `src/openai-computer-tool/main.py` invokes the deployed Prompt Agent with a scenario-specific user task prompt (`--scenario calculator` or `--scenario paint`).
3. `src/openai-computer-tool/utils/agent_runner.py` runs the multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` loop against `openai-computer-agent`.
4. `src/openai-computer-tool/utils/pyautogui_helper.py` translates each batched `computer_call` action (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) into local OS mouse and keyboard events via `pyautogui` and captures DPI-normalized desktop screenshots.

## Key files

| Path | Purpose |
| --- | --- |
| `sample.yaml` | Repository build-readiness validation metadata. |
| `azure.yaml` | Declarative Azure Developer CLI (`azd`) definition for the Foundry project and Prompt Agent. |
| `hooks/postprovision.*` | Provisions the `openai-computer-agent` Prompt Agent version after `azd provision`. |
| `src/openai-computer-tool/main.py` | CLI entrypoint (`provision`, `run --scenario calculator`, `run --scenario paint`, `delete`). |
| `src/openai-computer-tool/prompts/base.md` | Generic desktop automation system instructions for the Prompt Agent. |
| `src/openai-computer-tool/utils/agent_factory.py` | Creates and deletes Prompt Agent versions with `PromptAgentDefinition` and `ComputerTool()`. |
| `src/openai-computer-tool/utils/agent_runner.py` | Multi-turn `computer_call` -> `computer_call_output` execution loop and temporary screenshot file cleanup. |
| `src/openai-computer-tool/utils/pyautogui_helper.py` | PyAutoGUI action dispatcher (`click`, `drag`, `type`, `keypress`, `scroll`) and DPI screenshot helper. |
| `src/openai-computer-tool/utils/settings.py` | Environment variable and `AIProjectClient` configuration helpers. |
| `src/openai-computer-tool/scenarios/calculator_notepad.py` | Scenario 1: Prompt Agent opens Calculator and Notepad via Windows Search, computes `347 * 29 = 10063`, copies the result, pastes it into Notepad, and saves `calculation_result_<timestamp>.txt`. |
| `src/openai-computer-tool/scenarios/paint_smiley.py` | Scenario 2: Prompt Agent opens MS Paint via Windows Search and draws a centered yellow smiley face using `drag` and `click` actions. |

## Directory structure

```text
samples/python/prompt-agents/openai-computer-tool/
├── README.md
├── azure.yaml
├── sample.yaml
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

- An Azure AI Foundry / Microsoft Foundry **project** with a model deployment that supports the **OpenAI Computer Tool** (`{"type": "computer"}`, such as `gpt-5.4`)
- **Azure CLI** (`az login`) and **Azure Developer CLI** (`azd`)
- Python 3.10 or later (`uv` or `pip` + `venv`)
- Windows desktop session with `calc.exe`, `notepad.exe`, and `mspaint.exe` for the built-in desktop scenarios

## Configuration

Copy `src/openai-computer-tool/.env.example` to `src/openai-computer-tool/.env`:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL_DEPLOYMENT=gpt-5.4
AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4
AGENT_NAME=openai-computer-agent
```

Run `az login` before starting locally so `DefaultAzureCredential` can authenticate against your Foundry project.

## Option 1: Azure Developer CLI (`azd`)

From the sample root (`samples/python/prompt-agents/openai-computer-tool`), provision the Foundry project, `gpt-5.4` deployment, and `openai-computer-agent` Prompt Agent:

```bash
azd up
```

The `postprovision` hook runs `python main.py provision` to register the `openai-computer-agent` Prompt Agent version with `ComputerTool()`.

## Option 2: Run locally with Python (`pip` or `uv`)

### 1. Install dependencies

```bash
cd src/openai-computer-tool

# Using uv
uv sync

# Using pip + venv (Windows)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Provision the Prompt Agent

```bash
python main.py provision
```

### 3. Run desktop scenarios

#### Scenario 1 — Calculator + Notepad (`--scenario calculator`)

```bash
python main.py run --scenario calculator
```

Sends the user task prompt to `openai-computer-agent` to open **Calculator** via Windows Search, compute `347 * 29 = 10063`, copy the result (`Ctrl+C`), close Calculator (`Alt+F4`), open **Notepad** via Windows Search, paste the result (`Ctrl+V`), and save it to `calculation_result_<timestamp>.txt`.

#### Scenario 2 — MS Paint Colored Smiley (`--scenario paint`)

```bash
python main.py run --scenario paint
```

Sends the user task prompt asking `openai-computer-agent` to open **Microsoft Paint** via Windows Search and draw a cheerful, polished yellow smiley face centered on a clean white canvas with a black outline, two evenly spaced oval eyes, and a curved smile using the ellipse, fill, and curve/brush tools.

#### Custom task prompt

```bash
python main.py run --scenario calculator --prompt "Compute 125 * 48 in Calculator, copy the result, close Calculator, and paste it into Notepad."
```

### 4. Clean up agent versions (optional)

```bash
python main.py delete
```

## Safety and human oversight

Because this sample executes mouse and keyboard actions on your local desktop via `pyautogui`:

- **PyAutoGUI Fail-Safe** is enabled (`pyautogui.FAILSAFE = True`): move your mouse cursor to any corner of the primary monitor to immediately abort execution (`pyautogui.FailSafeException`).
- Run inside a dedicated desktop session or VM and keep human oversight while the agent interacts with local applications.
