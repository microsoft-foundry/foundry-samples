# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) hosted browser automation agent using **Foundry Toolbox** and the **Browser Automation tool** (Azure Playwright Service), hosted using the **Responses protocol**. The agent connects to a remote Chromium browser via Foundry Toolbox and runs Playwright CLI commands against it for general browsing, web scraping, and form filling.

## How It Works

### Solution Overview

When a user asks for browser work, the agent:

1. Connects to a Foundry Toolbox MCP endpoint in the same Foundry project.
2. Calls `create_session` from that Toolbox to provision a remote Chromium browser via Azure Playwright Service.
3. Connects Playwright CLI to the returned CDP WebSocket URL.
4. Uses `run_playwright_cli` to invoke Playwright CLI commands against the remote browser.
5. Calls `close_browser_session` to detach Playwright CLI state and end the remote browser when done.

```text
User
  -> Foundry hosted agent
      -> Agent Framework tools
          -> Foundry Toolbox MCP create_session
              -> Azure Playwright Service remote Chromium
          -> Playwright CLI
              -> remote browser CDP session
```

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

### Prompt-Guided Behavior

The agent reads a single base prompt from `prompts/base.md`. That prompt contains the browser lifecycle, safety, web extraction, and form-filling guidance used at runtime.

See [main.py](src/browser-automation-python-maf-sample-foundry/main.py) for the full implementation and [docs/sample-structure.md](docs/sample-structure.md) for the design rationale.

## Repository layout

| Path | Purpose |
| --- | --- |
| `main.py` | Entry point: loads settings, builds the agent, and starts `ResponsesHostServer`. |
| `utils/` | Agent construction (`agent_factory.py`), tools, settings, logging, and path helpers. |
| `prompts/base.md` | Browser lifecycle, safety, cleanup, web extraction, and form-filling rules. |
| `skills/azure-playwright-browser-automation/SKILL.md` | Playwright CLI operational reference for remote Azure Playwright Service sessions. |
| `pyproject.toml` | Python project metadata and direct dependencies. |
| `uv.lock` | Locked Python dependencies for reproducible builds. |
| `docs/sample-structure.md` | Design notes explaining the sample structure and extension points. |

## Prerequisites

- An Azure AI Foundry project with a deployed chat model (e.g., `gpt-4.1`).
- Azure CLI installed and authenticated (`az login`).
- Docker, if you want to build the container locally.
- **Python 3.13 or later** and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment for local development.

For hosted-agent setup, see [Deploy hosted agents with azd](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd).

> **Note:** You do not need a pre-existing Azure Playwright workspace or manual RBAC assignment. The deployment hooks create the workspace and assign roles automatically during `azd provision` and `azd deploy`. See [Deployment hooks](#deployment-hooks) below.

## Configuration

This sample uses two kinds of configuration:

- **Runtime environment variables** are read by the Python agent process. Use these for local runs, or set them in the hosted agent environment when deploying.
- **Deployment hooks** handle provisioning automatically — the `postprovision` hook creates the Playwright workspace connection and toolbox, and the `postdeploy` hook assigns RBAC roles.

### Runtime environment variables

For local development, copy `.env.example` to `.env` or set these values in your shell. The Python app loads `.env` when it starts.

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1"
```

Or in PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1"
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Required locally; provided by hosted agent runtime when deployed | Foundry project endpoint used for model and Toolbox MCP calls. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Required | Model deployment name. For hosted deployment, this is set from the model deployment selected during `azd ai agent init`; for local runs, set it in your shell or `.env` file. |
| `TOOLBOX_NAME` | `browser-automation-tools` | Foundry Toolbox name provisioned by the `postprovision` hook. This is fixed and should not be changed. |
| `BROWSER_AGENT_PLAYWRIGHT_CLI_TIMEOUT_SECONDS` | `180` | Optional timeout for each Playwright CLI command. |
| `BROWSER_AGENT_MCP_TIMEOUT_SECONDS` | `120` | Optional timeout for Toolbox MCP calls. |

The Toolbox endpoint is resolved as `<FOUNDRY_PROJECT_ENDPOINT>/toolboxes/browser-automation-tools/mcp?api-version=v1` and authenticated with the hosted agent identity.

## Running the Agent Host

### Local setup

From `src/bat-python-maf`, create and synchronize the locked environment, then run the hosted-agent server locally:

```bash
uv sync --frozen
uv run --no-sync python main.py
```

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details.

Send a POST request to the server with a JSON body containing an `"input"` field:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Open https://example.com and report the page title."}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest `
  -Uri http://localhost:8088/responses `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"input": "Open https://example.com and report the page title."}').Content
```

With `azd`:

```bash
azd ai agent invoke --local --new-session "Open https://example.com and report the page title."
```

The server returns a response ID that you can use to continue the same conversation and reuse the browser session in later requests:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Now take a screenshot of the page.", "previous_response_id": "REPLACE_WITH_PREVIOUS_RESPONSE_ID"}'
```

### Test in VS Code (Foundry Toolkit)

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Python 3.13 or later** and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment.

**Set up the Python virtual environment**

- Create and synchronize the locked environment:

  ```bash
  uv sync --frozen
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**.

Type the following in the Inspector:

```
Open https://example.com and report the page title.
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

When running `azd ai agent init -m ./14-browser-automation-agent/azure.yaml` from the parent directory (one level above this sample folder), you can customize the hosted agent name with the `AGENT_NAME` parameter. Leave it blank to use the default name, `browser-automation-python-maf-sample-foundry`.

> [!IMPORTANT]
> Run `azd ai agent init` from a directory **outside** this sample folder — either a new empty directory, or one level up from this sample (i.e. `samples/python/hosted-agents/agent-framework/responses/`). Do **not** run it from inside `14-browser-automation-agent/` itself. Because the sample folder already contains `azure.yaml`, initializing in place fails with:
>
> ```
> ERROR: a project azure.yaml already exists in '.', so the sample's unified
> azure.yaml cannot be adopted there
> ```
>
> Using the parent-directory invocation shown above (or a fresh empty folder with the remote manifest URL) avoids this.

> [!NOTE]
> **Linux/macOS:** After `azd ai agent init`, run `chmod +x hooks/*.sh` to make the hook scripts executable. `azd ai agent init` downloads files via the GitHub API, which does not preserve file permissions.

The same init flow also asks for the model deployment because [`azure.yaml`](azure.yaml) declares a `model` resource named `AZURE_AI_MODEL_DEPLOYMENT_NAME`. The selected deployment is used for the generated Azure deployment configuration and for the hosted agent's `AZURE_AI_MODEL_DEPLOYMENT_NAME` runtime environment variable. It does not update the sample's local `.env` file; set that file separately only when running the agent locally.

### Deployment hooks

This sample uses `azd` hooks to automate Playwright workspace setup:

#### `postprovision` — Connection & Toolbox setup

After `azd provision` completes, the `postprovision` hook runs interactively and:

1. **Prompts for a Playwright workspace** — provide an existing ARM resource ID, or leave empty to create a new one.
2. **Selects a region** (for new workspaces) — dynamically fetches available regions from the Azure RP.
3. **Selects an authentication type:**
   - **Project Managed Identity** (recommended) — the Foundry project's MSI authenticates to the workspace.
   - **Agent Identity** — the hosted agent's identity authenticates.
   - **API Key** (existing workspaces only, interactive mode only) — uses an access token you provide. Not supported in CI/non-interactive flows because the token must be entered interactively.
4. **Deploys a Bicep template** that creates the workspace (if new) and the Playwright project connection.
5. **Creates the `browser-automation-tools` toolbox** via the Foundry data-plane API and sets it as the default version.

#### `postdeploy` — RBAC role assignment

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


## Customize the sample

- Change prompt behavior in `prompts/base.md`.
- Add deeper procedural knowledge as skills under `skills/`.
- Add new tools in `src/browser-automation-python-maf-sample-foundry/tools.py`.

See [docs/sample-structure.md](docs/sample-structure.md) for the design rationale.

## Evaluation

This sample includes a co-located eval suite under `eval/`. To run:

```bash
azd ai agent eval run --config eval.yaml --no-prompt
```

The dataset (`eval/browser_automation_queries.jsonl`) contains 16 queries covering form filling, knowledge extraction, financial data, maps, shopping, education, research, news, time/utility, dev tools, recipe, dictionary, and sports against public URLs. Evaluators: `task_completion`, `relevance`.

## Guidance

This sample is intended as a starting point, not a production-ready browser automation platform. Before using it in production, review authentication, network access, data handling, secret management, logging, browser permissions, and approval flows for state-changing actions.

The `run_playwright_cli` tool intentionally invokes only `playwright-cli` with a named session and optional `PLAYWRIGHT_MCP_CDP_ENDPOINT`; it does not expose general shell execution.

The default hosted container resources (`cpu: "0.25"`, `memory: "0.5Gi"`) are minimal. Increase them in `azure.yaml` for multi-step scraping, longer QA sessions, or data-heavy browser automation.

Useful references:

- [Hosted agents in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Agent Framework overview](https://learn.microsoft.com/en-gb/agent-framework/overview/?pivots=programming-language-python)
- [Agent Framework skills](https://learn.microsoft.com/en-gb/agent-framework/agents/skills?pivots=programming-language-python)
- [Playwright CLI](https://github.com/microsoft/playwright-cli)