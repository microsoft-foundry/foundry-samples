# Coding Agent Instructions

This project is a **Microsoft Foundry hosted agent** — a containerized AI agent that runs in [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) using the Responses protocol and the GA OpenAI Computer Tool (`{"type": "computer"}`) with PyAutoGUI and Xvfb.

## Key files

- `src/openai-computer-tool/Dockerfile` — container definition with Xvfb and Tkinter Paint canvas support
- `src/openai-computer-tool/main.py` — `ResponsesAgentServerHost` handler and `--local` CLI entrypoint
- `src/openai-computer-tool/utils/agent_runner.py` — multi-turn `computer_call` execution loop
- `src/openai-computer-tool/utils/pyautogui_helper.py` — PyAutoGUI action dispatcher and Xvfb/Tkinter canvas helper
- `src/openai-computer-tool/scenarios/paint_smiley.py` — Paint Smiley desktop scenario

## Development workflow

The **Azure Developer CLI (`azd`)** manages the full lifecycle:

```bash
azd ai agent run                           # Run locally on http://localhost:8088
azd ai agent invoke --local "your message" # Test the local agent
azd deploy                                 # Deploy to Foundry
azd ai agent invoke "your message"         # Invoke the deployed agent
```
