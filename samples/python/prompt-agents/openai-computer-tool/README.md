<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# OpenAI Computer Tool Agent (Python, Prompt Agent)

This sample provisions a **Microsoft Foundry Prompt Agent** equipped with the GA **OpenAI Computer Tool** (`ComputerTool` / `{"type": "computer"}` in `azure-ai-projects`, replacing `computer_use_preview`) and executes a local desktop scenario (**MS Paint Colored Smiley**) using **PyAutoGUI**, matching the structured `src/` layout of the C# and Python `browser-automation` samples.

## What this sample demonstrates

- Provisioning a Microsoft Foundry **Prompt Agent** with `PromptAgentDefinition` and `ComputerTool()` (`{"type": "computer"}`)
- Separating agent initialization (`create_agent.py` + `utils/agent_factory.py`), generic system instructions (`prompts/base.md`), and runtime task execution (`main.py` + `scenarios/paint_smiley.py`)
- Multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` execution loop (`utils/agent_runner.py`) with automatic temporary screenshot file cleanup
- Local OS action translation (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`) and DPI-normalized screenshot capture via **PyAutoGUI** (`utils/pyautogui_helper.py`)

## How it works

1. **Agent Initialization (`create_agent.py`)**: `python create_agent.py` (or `hooks/postprovision.*` during `azd up`) initializes the `openai-computer-agent` Prompt Agent version in Microsoft Foundry with `ComputerTool()` (`{"type": "computer"}`) and generic system instructions from `src/openai-computer-tool/prompts/base.md`.
2. **Runtime Execution (`main.py`)**: `python main.py` invokes the provisioned Prompt Agent with the desktop task prompt (`scenarios/paint_smiley.py` or a custom `--prompt`).
3. **Computer Call Loop (`utils/agent_runner.py`)**: Runs the multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` loop against `openai-computer-agent`.
4. **Local PyAutoGUI Execution (`utils/pyautogui_helper.py`)**: Translates each batched `computer_call` action (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) into local OS mouse and keyboard events via `pyautogui` and captures DPI-normalized desktop screenshots.

## Key files

| Path | Purpose |
| --- | --- |
| `sample.yaml` | Repository build-readiness validation metadata. |
| `azure.yaml` | Declarative Azure Developer CLI (`azd`) definition for the Foundry project and Prompt Agent. |
| `hooks/postprovision.*` | Runs `python create_agent.py` to initialize the `openai-computer-agent` Prompt Agent version after `azd provision`. |
| `src/openai-computer-tool/create_agent.py` | Standalone agent initialization flow (`python create_agent.py` to create/update the Prompt Agent; `--delete` to delete versions). |
| `src/openai-computer-tool/main.py` | Runtime CLI entrypoint that invokes the provisioned Prompt Agent on the desktop task (`python main.py`). |
| `src/openai-computer-tool/prompts/base.md` | Generic desktop automation system instructions for the Prompt Agent. |
| `src/openai-computer-tool/utils/agent_factory.py` | Creates and deletes Prompt Agent versions with `PromptAgentDefinition` and `ComputerTool()`. |
| `src/openai-computer-tool/utils/agent_runner.py` | Multi-turn `computer_call` -> `computer_call_output` execution loop and temporary screenshot file cleanup. |
| `src/openai-computer-tool/utils/pyautogui_helper.py` | PyAutoGUI action dispatcher (`click`, `drag`, `type`, `keypress`, `scroll`) and DPI screenshot helper. |
| `src/openai-computer-tool/utils/settings.py` | Environment variable and `AIProjectClient` configuration helpers. |
| `src/openai-computer-tool/scenarios/paint_smiley.py` | MS Paint Scenario: Prompt Agent opens MS Paint via Windows Search, draws a centered yellow smiley face using `drag` and `click` actions, and saves `paint_smiley_<timestamp>.png`. |

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
        ├── create_agent.py
        ├── main.py
        ├── prompts/
        │   └── base.md
        ├── scenarios/
        │   ├── __init__.py
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
- Windows desktop session with `mspaint.exe` for the built-in MS Paint scenario

## Configuration

Copy `src/openai-computer-tool/.env.example` to `src/openai-computer-tool/.env`:

```dotenv
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

The `postprovision` hook runs `python create_agent.py` to register the `openai-computer-agent` Prompt Agent version with `ComputerTool()`.

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

### 2. Create / initialize the Prompt Agent (separate one-time flow)

```bash
python create_agent.py
```

### 3. Run the desktop scenario (`main.py`)

#### MS Paint Colored Smiley (`python main.py`)

```bash
python main.py
```

Sends the user task prompt asking `openai-computer-agent` to open **Microsoft Paint** via Windows Search, draw a cheerful, polished yellow smiley face centered on a clean white canvas with a black outline, two evenly spaced oval eyes, and a curved smile using the ellipse, fill, and curve/brush tools, and save it to `paint_smiley_<timestamp>.png`.

#### Custom task prompt

```bash
python main.py --prompt "Open Windows Search, launch MS Paint, draw a blue star in the center of the canvas, and save it."
```

### 4. Clean up agent versions (optional)

```bash
python create_agent.py --delete
```

## Safety and human oversight

Because this sample executes mouse and keyboard actions on your local desktop via `pyautogui`:

- **PyAutoGUI Fail-Safe** is enabled (`pyautogui.FAILSAFE = True`): move your mouse cursor to any corner of the primary monitor to immediately abort execution (`pyautogui.FailSafeException`).
- Run inside a dedicated desktop session or VM and keep human oversight while the agent interacts with local applications.
