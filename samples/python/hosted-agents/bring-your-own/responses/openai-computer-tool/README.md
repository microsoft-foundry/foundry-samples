<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# OpenAI Computer Tool Agent (Python, Bring Your Own Responses Hosted Agent)

This sample implements a **Microsoft Foundry Hosted Agent** (`kind: hosted`) using the **Bring Your Own** approach with the **Responses protocol** (`azure-ai-agentserver-responses`) and the GA **OpenAI Computer Tool** (`{"type": "computer"}` / `ComputerTool`, replacing `computer_use_preview`). Inside the container, it runs a lightweight virtual X11 desktop (`Xvfb :99` + Tkinter Paint canvas) and executes `computer_call` actions (**Paint Colored Smiley**) using **PyAutoGUI** without Playwright.

## What this sample demonstrates

- Hosting a custom **Responses protocol** agent with `ResponsesAgentServerHost` (`azure-ai-agentserver-responses`)
- Invoking a Microsoft Foundry model deployment with the GA **OpenAI Computer Tool** (`tools=[{"type": "computer"}]`)
- Multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` execution loop (`utils/agent_runner.py`) with automatic temporary screenshot file cleanup
- Executing OS-level mouse and keyboard actions (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) and capturing DPI-normalized desktop screenshots via **PyAutoGUI** (`utils/pyautogui_helper.py`)
- Running the **Paint Smiley** desktop scenario inside a containerized `Xvfb` virtual framebuffer with a built-in Tkinter Paint canvas (`scenarios/paint_smiley.py`), or against **MS Paint** (`mspaint.exe`) when run locally on Windows

## How it works

1. **Container & Virtual Desktop (`Dockerfile`)**: Starts an `Xvfb :99` virtual X11 display (`1280x800x24`) and launches the `ResponsesAgentServerHost` server on port `8088`.
2. **Hosted Agent Responses Handler (`main.py`)**: Accepts OpenAI Responses protocol requests (`POST /responses`), reconstructs conversation history, and streams the multi-turn Computer Tool loop back to the caller. Also supports `--local` CLI execution (`python main.py --local`) for direct desktop testing.
3. **Computer Call Loop (`utils/agent_runner.py`)**: Calls the Foundry Responses API with `tools=[{"type": "computer"}]` and system instructions from `prompts/base.md`, dispatches each `computer_call` batch to `handle_pyautogui_action`, and returns a `computer_screenshot` in `computer_call_output` until the task completes.
4. **PyAutoGUI + Virtual Paint Canvas (`utils/pyautogui_helper.py` + `scenarios/paint_smiley.py`)**: Translates `computer_call` actions into mouse/keyboard input via `pyautogui`. On Linux (`Xvfb`), automatically opens a lightweight Tkinter Paint canvas so the agent can draw a yellow smiley face and save `paint_smiley_<timestamp>.png`; on Windows, the agent uses Microsoft Paint (`mspaint.exe`).

## Key files

| Path | Purpose |
| --- | --- |
| `sample.yaml` | Repository build-readiness validation metadata. |
| `azure.yaml` | Declarative Azure Developer CLI (`azd`) definition for the Foundry project and Hosted Agent (`kind: hosted`, `protocol: responses`). |
| `src/openai-computer-tool/Dockerfile` | Container definition with `uv`, `xvfb`, `python3-tk`, and `scrot` for virtual desktop execution. |
| `src/openai-computer-tool/main.py` | Hosted Agent Responses protocol server (`ResponsesAgentServerHost`) and `--local` CLI entrypoint. |
| `src/openai-computer-tool/prompts/base.md` | Desktop automation system instructions for the OpenAI Computer Tool agent. |
| `src/openai-computer-tool/utils/agent_runner.py` | Multi-turn `computer_call` -> `computer_call_output` execution loop and temporary screenshot file cleanup. |
| `src/openai-computer-tool/utils/pyautogui_helper.py` | PyAutoGUI action dispatcher (`click`, `drag`, `type`, `keypress`, `scroll`), `Xvfb` / Tkinter Paint canvas launcher, and DPI screenshot helper. |
| `src/openai-computer-tool/utils/settings.py` | Environment variable (`FOUNDRY_PROJECT_ENDPOINT` / `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`) and `AIProjectClient` helpers. |
| `src/openai-computer-tool/scenarios/paint_smiley.py` | Paint Smiley scenario prompt and runner (`build_paint_prompt`, `run_paint_scenario`). |

## Directory structure

```text
samples/python/hosted-agents/bring-your-own/responses/openai-computer-tool/
├── AGENTS.md
├── README.md
├── azure.yaml
├── sample.yaml
└── src/
    └── openai-computer-tool/
        ├── .dockerignore
        ├── .env.example
        ├── .gitignore
        ├── Dockerfile
        ├── main.py
        ├── pyproject.toml
        ├── uv.lock
        ├── prompts/
        │   └── base.md
        ├── scenarios/
        │   ├── __init__.py
        │   └── paint_smiley.py
        └── utils/
            ├── __init__.py
            ├── agent_runner.py
            ├── pyautogui_helper.py
            └── settings.py
```

## Prerequisites

- An Azure AI Foundry / Microsoft Foundry **project** with a model deployment that supports the **OpenAI Computer Tool** (`{"type": "computer"}`, such as `gpt-5.4`)
- **Azure CLI** (`az login`) and **Azure Developer CLI** (`azd >= 1.27.1`) with the `azure.ai.agents` extension
- Python 3.12 or later
- `uv 0.11.7` or later (or `pip` + `venv`)

## Configuration

Copy `src/openai-computer-tool/.env.example` to `src/openai-computer-tool/.env`:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4
```

Run `az login` before starting locally so `DefaultAzureCredential` can authenticate against your Foundry project.

## Option 1: Azure Developer CLI (`azd`)

From a new directory or from the sample directory, initialize, provision, and run the Hosted Agent:

```bash
azd provision
azd ai agent run
```

Invoke the local Responses endpoint with the default Paint Smiley task (`"paint_smiley"` or a custom prompt):

```bash
azd ai agent invoke --local "Draw a yellow smiley face on the Paint canvas and save it."
```

Deploy the containerized Hosted Agent to Microsoft Foundry and invoke it:

```bash
azd deploy
azd ai agent invoke "Draw a yellow smiley face on the Paint canvas and save it."
```

## Option 2: Run locally with Python (`uv` or `pip`)

### 1. Install dependencies

```bash
cd src/openai-computer-tool
uv sync --frozen --python 3.12
```

### 2. Start the Hosted Agent Responses server (`http://localhost:8088/responses`)

```bash
uv run --no-sync python main.py
```

Then invoke the local Responses endpoint in another terminal:

```bash
curl -sS -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Draw a yellow smiley face on the Paint canvas and save it."}'
```

### 3. Run the Paint Smiley scenario directly in CLI mode (`--local`)

```bash
python main.py --local
```

Or pass a custom desktop task prompt:

```bash
python main.py --local --prompt "Draw a cheerful yellow smiley face in the center of the canvas and save it."
```

## Safety and human oversight

Because this sample executes OS mouse and keyboard actions via `pyautogui`:

- Inside the container, all actions are isolated inside the virtual `Xvfb :99` display (`1280x800x24`).
- When run directly on a local desktop (`python main.py --local`), **PyAutoGUI Fail-Safe** is enabled (`pyautogui.FAILSAFE = True`): move your mouse cursor to any corner of the primary monitor to immediately abort execution (`pyautogui.FailSafeException`).
