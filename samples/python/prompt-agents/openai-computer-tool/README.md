# Prompt Agent with OpenAI Computer Tool (GA `computer`) — Python

A **Prompt Agent** sample demonstrating how to provision an **Azure AI Foundry Prompt Agent** equipped with the **OpenAI Computer Tool** (GA `ComputerTool` / `{"type": "computer"}` in `azure-ai-projects`, replacing `computer_use_preview`) and invoke it on local desktop tasks (**Calculator + Notepad** in `main.py` and **MS Paint Colored Smiley** in `paint_smiley.py`) using **PyAutoGUI** (`common/pyautogui_helper.py`), matching the desktop automation pattern in [`openai-cua-sample-app`](https://github.com/openai/openai-cua-sample-app).

## Architecture & Separation of Concerns

Following the structure of existing `samples/python/prompt-agents/` samples (`agent-identity-and-skills`, `shared-blob-workspace`):

1. **Agent Provisioning (`provision_agent.py` + `agents/computer_agent/instructions.md` + `azure.yaml`):**
   - Agent definition and provisioning are completely separated from task invocation.
   - `agents/computer_agent/instructions.md` holds generic desktop computer-use instructions so one deployed Prompt Agent (`openai-computer-agent`) can be reused across any desktop task.
   - `provision_agent.py` (or `azd up` via `azure.yaml`) creates the Prompt Agent version in Azure AI Foundry with `PromptAgentDefinition` and `ComputerTool()` (`{"type": "computer"}`).
2. **Local PyAutoGUI Execution Helper (`common/pyautogui_helper.py` & `common/agent_runner.py`):**
   - `common/pyautogui_helper.py` translates each batched `computer_call` action (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) into local OS mouse/keyboard actions via `pyautogui` and captures DPI-normalized screenshots (`pyautogui.size()`).
   - `common/agent_runner.py` runs the multi-turn `computer_call` -> `handle_pyautogui_action` -> `computer_call_output` loop against the provisioned agent.
3. **Task Invocation via User Prompt (`main.py` & `paint_smiley.py`):**
   - `main.py` opens Windows **Calculator** and **Notepad** side-by-side and passes the specific task (`347 * 29` -> copy -> close Calculator -> paste into Notepad -> save) **purely via the user `prompt`** (`responses.create(input=prompt)`).
   - `paint_smiley.py` opens **Microsoft Paint (`mspaint.exe`)** with a blank canvas and asks the same provisioned agent via user `prompt` to draw a colored yellow smiley face (circle outline, yellow bucket fill, eyes, and curved smile) using `drag` and `click` actions and save the drawing (`Ctrl+S`).

## Directory Structure

```text
samples/python/prompt-agents/openai-computer-tool/
├── README.md                                # Documentation and walkthrough
├── azure.yaml                               # Declarative azd configuration for Foundry Project + Prompt Agent
├── pyproject.toml                           # Project metadata and dependencies (uv / pip)
├── requirements.txt                         # Python dependencies
├── .env.sample                              # Environment variable template
├── .gitignore                               # Ignores .venv, .env, and generated output files
├── sample_config.py                         # Shared constants (AGENT_NAME) and client helpers
├── provision_agent.py                       # Separate provisioning script (create / delete Prompt Agent)
├── main.py                                  # Sample 1: Calculator + Notepad desktop task via user prompt
├── paint_smiley.py                          # Sample 2: Draw a colored smiley face in MS Paint (mspaint) via user prompt
├── agents/
│   └── computer_agent/
│       └── instructions.md                  # Generic system instructions for the Prompt Agent
└── common/
    ├── __init__.py                          # Package exports
    ├── agent_runner.py                      # Multi-turn computer_call -> computer_call_output runner
    └── pyautogui_helper.py                  # PyAutoGUI action dispatcher + DPI screenshot helper
```

## Prerequisites

- Python 3.10+ (`uv` or `pip` + `venv`)
- An Azure AI Foundry **project** with a model deployment that supports the **OpenAI Computer Tool** (`{"type": "computer"}`, such as `gpt-5.4`, `gpt-5.5`, or `gpt-5.6-sol`).
- **Azure CLI** signed in (`az login`) for `DefaultAzureCredential`.

## Configure

```bash
cp .env.sample .env
# then fill in AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
```

| Variable | Meaning |
| --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | `https://<resource>.services.ai.azure.com/api/projects/<project>` |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment supporting the GA `computer` tool (e.g., `gpt-5.4`) |
| `AGENT_NAME` | Prompt Agent name registered in Foundry (default: `openai-computer-agent`) |

## Install

```bash
# uv
uv sync

# pip
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

### 1. Provision the Prompt Agent (once, or after editing `agents/computer_agent/instructions.md`)

Using Python:

```bash
python provision_agent.py
```

Or using Azure Developer CLI (`azd`):

```bash
azd up
```

This creates a new version of `openai-computer-agent` in your Foundry project with `ComputerTool()` (`{"type": "computer"}`) and the generic system instructions from `agents/computer_agent/instructions.md`.

### 2. Invoke the Agent with a Task Prompt

#### Sample A — Calculator + Notepad (`main.py`)

```bash
python main.py
```

`main.py` launches Windows **Calculator** (left) and **Notepad** (right) and sends the task prompt to `openai-computer-agent`. The agent inspects screenshots and emits batched `computer_call` actions that `common/pyautogui_helper.py` executes locally via **PyAutoGUI** to compute `347 * 29 = 10063`, copy the result (`Ctrl+C`), close Calculator (`Alt+F4`), paste the result into Notepad (`Ctrl+V`), and save `calculation_result_<timestamp>.txt` (`Ctrl+S`).

#### Sample B — Draw a Colored Smiley Face in MS Paint (`paint_smiley.py`)

```bash
python paint_smiley.py
```

`paint_smiley.py` launches **Microsoft Paint (`mspaint.exe`)** with a blank white canvas and sends a user prompt asking `openai-computer-agent` to draw a colored yellow smiley face (circle outline, yellow bucket fill, two eyes, and a curved smile) using `drag` and `click` actions, then save the drawing (`smiley_<timestamp>.png`).

You can also pass any custom desktop prompt at runtime to either script:

```bash
python main.py --prompt "Compute 125 * 48 in Calculator, copy the result, close Calculator, and paste it into Notepad."
python paint_smiley.py --prompt "Draw a yellow smiley face with sunglasses in MS Paint and press Ctrl+S."
```

### 3. Clean Up Agent Versions (optional)

```bash
python provision_agent.py delete
```



