# Browser Automation Agent (Python, Responses Protocol)

A **Bring Your Own** hosted agent that automates web browsers using
[Playwright CLI](https://github.com/microsoft/playwright-cli) via Azure AI Foundry
Toolbox MCP. Built with `azure-ai-agentserver-responses` (no Agent Framework).

> This agent helps you with handling multiple sessions parellely.
Use this agent when you need the control over the streamed response, whatever you need to see in the UI or outputs, need a hands on proper raw SDKs.
There is a simple sample available available at agent-framework/responses/14-browser-automation-agent se that for the common needs.

## What This Sample Demonstrates

- **Lazy browser session creation** — no session is created until the model actually needs one
- **Multi-session support** — run multiple concurrent browsers for parallel tasks
- **Toolbox MCP integration** — uses Foundry Toolbox to provision remote Chromium browsers
- **Skills system** — guided workflows loaded on demand (form-filling, web scraping)
- **Kill session priority** — immediately honours user requests to close sessions

## Folder Structure

```
browser-automation/
├── README.md
├── azure.yaml               # Unified manifest — project, model, and agent (name, protocols, resources, env vars)
└── src/
    └── browser-automation-python-byo-sample-foundry/
        ├── main.py            # Responses handler, session management, agentic tool loop
        ├── pyproject.toml     # Python project and direct dependencies
        ├── uv.lock            # Reproducible dependency lock
        ├── Dockerfile         # Container build
        ├── skills/
        │   ├── form-filler.md # Form-filling workflow with date picker handling
        │   └── web-scraper.md # Data extraction with pagination support
        └── utils/
            ├── browser.py     # playwright-cli subprocess wrapper (BrowserSession class)
            ├── toolbox.py     # MCP client for Foundry Toolbox (browser session lifecycle)
            ├── skills.py      # Skill markdown loader
            └── constants.py   # System prompt, tool definitions, config constants
```

## How It Works

```text
User → Responses Protocol → Handler (main.py)
                                ↓
                          Model (tool-calling loop)
                                ↓
                    ┌───────────┴───────────┐
                    ↓                       ↓
           run_browser(cmd)         create_session(name)
                    ↓                       ↓
           playwright-cli           Toolbox MCP (toolbox.py)
           (browser.py)             create_browser_session()
                    ↓                       ↓
           Remote Chromium ←── CDP URL ────┘
```

1. User sends a message → handler passes it to the model with tool definitions.
2. Model calls `run_browser(command="goto", args=["https://..."])`.
3. On **first call**, a "default" session is lazily created:
   - `toolbox.py` calls Toolbox MCP `create_session` → gets `cdp_url` + `live_view_url`
   - `browser.py` runs `playwright-cli attach --cdp=<url>` to connect
4. Subsequent `run_browser` calls reuse the existing session.
5. For parallel work, the model calls `create_session(name)` for additional browsers.
6. `kill_session` closes sessions immediately when requested.

## Prerequisites

- An Azure AI Foundry project with a deployed chat model (e.g., `gpt-4.1`).
- Azure CLI installed and authenticated (`az login`).
- Python 3.12+ for local development.

> **Note:** You do not need a pre-existing Azure Playwright workspace or manual RBAC assignment. The deployment hooks create the workspace and assign roles automatically during `azd provision` and `azd deploy`. See [Deployment hooks](#deployment-hooks) below.

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint (auto-injected in hosted containers) |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name (e.g., `gpt-4.1`) |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_TIMEOUT_SECONDS` | `180` | Timeout for each playwright-cli command |

## Running Locally

```bash
cd src/bat-python-byo

# Set environment
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1"

# Install dependencies
pipx install uv==0.11.7
uv sync --frozen --python 3.12
npm install -g @playwright/cli@latest

# Run
uv run --no-sync python main.py
```

### Invoke the agent

```bash
curl -sS -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "Go to https://example.com and tell me the page title"}' | jq .
```

### Test in VS Code (Foundry Toolkit)

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

**Set up the Python virtual environment**

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

## Deploying to Foundry

```bash
# Initialize from manifest — run from the parent directory (one level up
# from this sample folder) so azd scaffolds the project alongside the
# sample rather than inside it.
cd ..
azd ai agent init -m ./browser-automation/azure.yaml

# On Linux/macOS: make hook scripts executable (azd ai agent init does not preserve file permissions)
chmod +x hooks/*.sh

# Provision — the postprovision hook handles Playwright connection + toolbox setup
azd provision

# Deploy — the postdeploy hook assigns RBAC roles
azd deploy
```

> [!NOTE]
> This sample is supported in container deployments only. The container image installs Playwright CLI, which this browser automation sample needs at runtime.

> [!IMPORTANT]
> Run `azd ai agent init` from a directory **outside** the sample folder — either a new empty directory, or one level up from this sample as shown above. Do **not** run it from inside the sample directory itself. Because the sample folder already contains `azure.yaml`, initializing in place fails with:
>
> ```
> ERROR: a project azure.yaml already exists in '.', so the sample's unified
> azure.yaml cannot be adopted there
> ```
>
> The `cd ..` step above (or using a fresh, empty directory with the remote manifest URL) avoids this.

## Deployment hooks

This sample uses `azd` hooks to automate Playwright workspace setup:

### `postprovision` — Connection & Toolbox setup

After `azd provision` completes, the `postprovision` hook runs interactively and:

1. **Prompts for a Playwright workspace** — provide an existing ARM resource ID, or leave empty to create a new one.
2. **Selects a region** (for new workspaces) — dynamically fetches available regions from the Azure RP.
3. **Selects an authentication type:**
   - **Project Managed Identity** (recommended) — the Foundry project's MSI authenticates to the workspace.
   - **Agent Identity** — the hosted agent's identity authenticates.
   - **API Key** (existing workspaces only, interactive mode only) — uses an access token you provide. Not supported in CI/non-interactive flows because the token must be entered interactively.
4. **Deploys a Bicep template** that creates the workspace (if new) and the Playwright project connection.
5. **Creates the `browser-automation-tools` toolbox** via the Foundry data-plane API and sets it as the default version.

### `postdeploy` — RBAC role assignment

After `azd deploy` completes, the `postdeploy` hook:

1. Determines the correct principal ID based on the configured auth type:
   - **Project Managed Identity** → project's system-assigned identity
   - **Agent Identity** → the deployed agent's instance identity
2. Assigns the **Playwright Workspace Contributor** role on the Playwright workspace.
3. Retries up to 3 times with a graceful warning if the assignment fails (e.g., due to Entra propagation delays).

> **Note:** API Key authentication does not require a role assignment.

#### Non-interactive / CI usage

For CI pipelines or `azd provision --no-prompt`, pre-set the required values so the hooks skip interactive prompts:

```bash
# Use an existing Playwright workspace
azd env set PLAYWRIGHT_SERVICE_RESOURCE_ID "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.LoadTestService/playwrightWorkspaces/{name}"
azd env set PLAYWRIGHT_AUTH_TYPE "ProjectManagedIdentity"   # or AgenticIdentityToken

# Or create a new workspace (omit PLAYWRIGHT_SERVICE_RESOURCE_ID)
azd env set PLAYWRIGHT_REGION "eastus"
azd env set PLAYWRIGHT_AUTH_TYPE "ProjectManagedIdentity"
```

> **⚠️ Warning:** If neither `PLAYWRIGHT_SERVICE_RESOURCE_ID` nor `PLAYWRIGHT_REGION` is set:
> - **PowerShell (Windows):** prompts time out after 60 seconds and default to creating a new workspace in **eastus**.
> - **sh (Linux/macOS):** prompts will **wait indefinitely** for input, blocking the pipeline.
>
> Always pre-set at least one of these variables in CI to avoid surprises or hanging builds.

| Variable | Required | Description |
| --- | --- | --- |
| `PLAYWRIGHT_SERVICE_RESOURCE_ID` | No | ARM resource ID of an existing workspace. Omit to create a new one. |
| `PLAYWRIGHT_REGION` | When creating new | Region for the new workspace (e.g., `eastus`). Defaults to `eastus` if not set. |
| `PLAYWRIGHT_AUTH_TYPE` | No | `ProjectManagedIdentity` (default) or `AgenticIdentityToken`. `ApiKey` is interactive-only. |

### Option 1: Let hooks provision everything (recommended)

Use this path for a fully automated setup. Just run:

```bash
azd provision   # Hook prompts for Playwright details, creates connection + toolbox
azd deploy      # Hook assigns RBAC to the identity
```

## Tools Available to the Model

| Tool | Description |
|------|-------------|
| `run_browser` | Run a playwright-cli command (session auto-created on first use) |
| `create_session` | Create an additional named browser session for parallel work |
| `kill_session` | Close a session immediately (or `"all"` to close all) |
| `run_parallel` | Execute commands across sessions concurrently |
| `list_sessions` | Show all active sessions with live view URLs |
| `load_skill` | Load a skill for guided workflow instructions |

## Multi-Session Examples

The agent supports multiple concurrent browser sessions, enabling parallel workflows and human-in-the-loop scenarios.

### Example 1: Parallel research across tabs

```
User: "Compare pricing on aws.amazon.com and azure.microsoft.com side by side"

Agent:
  → create_session("aws")
  → create_session("azure")
  → run_parallel([
      {session: "aws", command: "goto", args: ["https://aws.amazon.com/pricing/"]},
      {session: "azure", command: "goto", args: ["https://azure.microsoft.com/pricing/"]}
    ])
  → run_parallel([
      {session: "aws", command: "snapshot"},
      {session: "azure", command: "snapshot"}
    ])
  → Responds with comparison
```

### Example 2: Form filling with OTP (human-in-the-loop)

```
User: "Sign up on example.com/register with my email test@contoso.com"

Agent:
  → run_browser(command: "goto", args: ["https://example.com/register"])
  → run_browser(command: "fill", args: ["#email", "test@contoso.com"])
  → run_browser(command: "click", args: ["#send-otp"])
  → Responds: "OTP sent to test@contoso.com. Please provide the code when you receive it."

User: "The OTP is 847291"

Agent:
  → run_browser(command: "fill", args: ["#otp-input", "847291"])
  → run_browser(command: "click", args: ["#verify-btn"])
  → run_browser(command: "snapshot")
  → Responds: "Verified! Proceeding with registration..."
```

### Example 3: Monitor one page while working on another

```
User: "Fill the job application on careers.contoso.com, and keep checking my email
       on mail.contoso.com for a confirmation"

Agent:
  → create_session("application")
  → create_session("email")
  → run_browser(session: "application", command: "goto", args: ["https://careers.contoso.com/apply"])
  → ... fills the form in "application" session ...
  → run_browser(session: "email", command: "goto", args: ["https://mail.contoso.com"])
  → run_browser(session: "email", command: "snapshot")
  → Responds: "Form submitted. Checking email — no confirmation yet. I'll check again."

User: "Check email again"

Agent:
  → run_browser(session: "email", command: "reload")
  → run_browser(session: "email", command: "snapshot")
  → Responds: "Confirmation email received!"
```

### Example 4: Kill sessions when done

```
User: "Close the email browser, keep the application one"

Agent:
  → kill_session("email")
  → Responds: "Closed email session. Application session still active."
```

## Skills

Skills are markdown instruction files in `skills/`:

- **form-filler** — Step-by-step form filling with date picker handling, multi-page navigation
- **web-scraper** — Data extraction using JavaScript eval, pagination handling

The model loads skills on demand via the `load_skill` tool when it needs guided instructions for a specific workflow type.

## Customization

- Edit `constants.py` to modify the system prompt or tool definitions.
- Add new skills as `.md` files in `skills/`.
- Modify `browser.py` to add/restrict allowed playwright-cli commands.
- Adjust `azure.yaml` resources (`cpu`, `memory`) for heavier workloads.
