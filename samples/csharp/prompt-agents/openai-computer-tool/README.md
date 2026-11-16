<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# OpenAI Computer Tool Agent (C#, Prompt Agent)

This sample provisions a **Microsoft Foundry Prompt Agent** equipped with the GA **OpenAI Computer Tool** (`{"type": "computer"}` in `Azure.AI.Projects.Agents`, replacing `computer_use_preview`) and executes a local desktop scenario (**MS Paint Colored Smiley**) using native Win32 desktop automation in C#, matching the structured `src/` layout of the Python `openai-computer-tool` and C# `browser-automation` samples.

## What this sample demonstrates

- Provisioning a Microsoft Foundry **Prompt Agent** with `DeclarativeAgentDefinition` and the GA `{"type": "computer"}` tool (`utils/AgentFactory.cs`)
- Separating agent initialization (`dotnet run -- --create-agent` + `utils/AgentFactory.cs`), generic system instructions (`prompts/base.md`), and runtime task execution (`Program.cs` + `scenarios/PaintSmileyScenario.cs`)
- Multi-turn `computer_call` -> `DesktopAutomationHelper.HandleAction` -> `computer_call_output` execution loop (`utils/AgentRunner.cs`) with automatic temporary screenshot file cleanup
- Local OS action translation (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`) and DPI-aware PNG screenshot capture via Win32 (`user32.dll` / `gdi32.dll`) in `utils/DesktopAutomationHelper.cs`

## How it works

1. **Agent Initialization (`dotnet run -- --create-agent`)**: `dotnet run -- --create-agent` (or `hooks/postprovision.*` during `azd up`) initializes the `openai-computer-agent` Prompt Agent version in Microsoft Foundry with `{"type": "computer"}` and generic system instructions from `src/openai-computer-tool/prompts/base.md`.
2. **Runtime Execution (`dotnet run`)**: `dotnet run` invokes the provisioned Prompt Agent with the desktop task prompt (`scenarios/PaintSmileyScenario.cs` or a custom `--prompt`).
3. **Computer Call Loop (`utils/AgentRunner.cs`)**: Runs the multi-turn `computer_call` -> `DesktopAutomationHelper.HandleAction` -> `computer_call_output` loop against `openai-computer-agent`.
4. **Local Desktop Execution (`utils/DesktopAutomationHelper.cs`)**: Translates each batched `computer_call` action (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) into local OS mouse and keyboard events and captures DPI-aware desktop screenshots encoded as PNG.

## Key files

| Path | Purpose |
| --- | --- |
| `sample.yaml` | Repository build-readiness validation metadata. |
| `azure.yaml` | Declarative Azure Developer CLI (`azd`) definition for the Foundry project and Prompt Agent. |
| `hooks/postprovision.*` | Runs `dotnet run -- --create-agent` to initialize the `openai-computer-agent` Prompt Agent version after `azd provision`. |
| `src/openai-computer-tool/Program.cs` | CLI entrypoint supporting `--create-agent`, `--delete`, and running the desktop scenario (or custom `--prompt`). |
| `src/openai-computer-tool/prompts/base.md` | Generic desktop automation system instructions for the Prompt Agent. |
| `src/openai-computer-tool/utils/AgentFactory.cs` | Creates and deletes Prompt Agent versions with `DeclarativeAgentDefinition` and `{"type": "computer"}`. |
| `src/openai-computer-tool/utils/AgentRunner.cs` | Multi-turn `computer_call` -> `computer_call_output` execution loop and temporary screenshot file cleanup. |
| `src/openai-computer-tool/utils/DesktopAutomationHelper.cs` | Win32 desktop action dispatcher (`click`, `drag`, `type`, `keypress`, `scroll`) and PNG screenshot helper. |
| `src/openai-computer-tool/utils/Settings.cs` | Environment variable and `AIProjectClient` configuration helpers. |
| `src/openai-computer-tool/scenarios/PaintSmileyScenario.cs` | MS Paint Scenario: Prompt Agent opens MS Paint via Windows Search, draws a centered yellow smiley face using `drag` and `click` actions, and saves `paint_smiley_<timestamp>.png`. |

## Directory structure

```text
samples/csharp/prompt-agents/openai-computer-tool/
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
        ├── openai-computer-tool.csproj
        ├── Program.cs
        ├── prompts/
        │   └── base.md
        ├── scenarios/
        │   └── PaintSmileyScenario.cs
        └── utils/
            ├── AgentFactory.cs
            ├── AgentRunner.cs
            ├── DesktopAutomationHelper.cs
            └── Settings.cs
```

## Prerequisites

- An Azure AI Foundry / Microsoft Foundry **project** with a model deployment that supports the **OpenAI Computer Tool** (`{"type": "computer"}`, such as `gpt-5.4`)
- **Azure CLI** (`az login`) and **Azure Developer CLI** (`azd`)
- .NET 10.0 SDK (`dotnet`)
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

From the sample root (`samples/csharp/prompt-agents/openai-computer-tool`), provision the Foundry project, `gpt-5.4` deployment, and `openai-computer-agent` Prompt Agent:

```bash
azd up
```

The `postprovision` hook runs `dotnet run -- --create-agent` to register the `openai-computer-agent` Prompt Agent version with `{"type": "computer"}`.

## Option 2: Run locally with .NET CLI (`dotnet`)

### 1. Restore and build

```bash
cd src/openai-computer-tool
dotnet build
```

### 2. Create / initialize the Prompt Agent (separate one-time flow)

```bash
dotnet run -- --create-agent
```

### 3. Run the desktop scenario (`dotnet run`)

#### MS Paint Colored Smiley (`dotnet run`)

```bash
dotnet run
```

Sends the user task prompt asking `openai-computer-agent` to open **Microsoft Paint** via Windows Search, draw a cheerful, polished yellow smiley face centered on a clean white canvas with a black outline, two evenly spaced oval eyes, and a curved smile using the ellipse, fill, and curve/brush tools, and save it to `paint_smiley_<timestamp>.png`.

#### Custom task prompt

```bash
dotnet run -- --prompt "Open Windows Search, launch MS Paint, draw a blue star in the center of the canvas, and save it."
```

### 4. Clean up agent versions (optional)

```bash
dotnet run -- --delete
```

## Safety and human oversight

Because this sample executes mouse and keyboard actions on your local desktop:

- **Corner Fail-Safe** is enabled: move your mouse cursor to the top-left corner `(0, 0)` of the primary monitor to immediately abort execution.
- Run inside a dedicated desktop session or VM and keep human oversight while the agent interacts with local applications.
