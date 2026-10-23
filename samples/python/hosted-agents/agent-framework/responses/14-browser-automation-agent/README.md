# Browser Automation Agent (Python, Agent Framework)

This sample hosts a Python Agent Framework agent over the Responses protocol and gives it the GA Azure Playwright browser tools through a Foundry Toolbox MCP connection.

## How it works

1. The deployment hooks provision or reuse an Azure Playwright workspace.
2. They create a Foundry project connection targeting `https://<region>.mcp.playwright.microsoft.com/playwrightworkspaces/<id>/mcp`.
3. They publish a Toolbox containing a `browser_automation` tool.
4. Agent Framework connects to the Toolbox MCP endpoint and discovers browser tools dynamically.
5. The model uses the discovered create-session tool, then passes the returned `browserSessionId` to the other browser tools.
6. Middleware removes `liveViewUrl` from model-visible tool output and streams the exact link directly to the user.

No browser tool schema is hardcoded in this sample, and no local browser CLI or CDP attachment is required.

## Key files

| Path | Purpose |
| --- | --- |
| `src/bat-python-maf/main.py` | Starts the Responses host. |
| `src/bat-python-maf/utils/agent_factory.py` | Builds the agent and response middleware. |
| `src/bat-python-maf/utils/tools.py` | Connects the Toolbox MCP server and handles exact live-view URLs. |
| `src/bat-python-maf/prompts/base.md` | Browser lifecycle and automation behavior. |
| `src/bat-python-maf/pyproject.toml` | Python project metadata and direct dependencies. |
| `src/bat-python-maf/uv.lock` | Locked Python dependencies for reproducible builds. |
| `hooks/setup-toolbox.*` | Publishes the GA browser automation toolbox. |
| `infra-modules/playwright-connection.bicep` | Creates the GA MCP project connection. |

## Prerequisites

- Azure CLI and Azure Developer CLI
- An Azure AI Foundry project with a deployed chat model
- **Python 3.11 or later** and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment for local development
- Docker for local container builds

The deployment hooks create the Playwright workspace when one is not supplied and assign the required roles after deployment.

## Configuration

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
TOOLBOX_NAME=browser-automation-tools
BROWSER_AGENT_MCP_TIMEOUT_SECONDS=120
```

The hosted runtime supplies the Foundry endpoint. For local runs, authenticate with `az login`.

## Run locally

```bash
cd src/bat-python-maf
uv sync --frozen
uv run --no-sync python main.py
```

Invoke the local Responses endpoint:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Open https://example.com and report the page title."}'
```

## Deploy

Run `azd ai agent init` from outside this sample directory, then provision and deploy:

```bash
azd ai agent init -t ./14-browser-automation-agent/azure.yaml
azd provision
azd deploy
```

On Linux or macOS, make the generated hook scripts executable before provisioning. The `postprovision` hook creates the Playwright connection and toolbox; the `postdeploy` hook assigns browser access to the configured project Identity or hosted agent identity.

## Browser lifecycle

Agent Framework discovers the browser tools through MCP `tools/list`. The agent uses the discovered tools to create and close sessions, reusing the returned `browserSessionId` for follow-up work. Live-view URLs are emitted by application code so their signed fragments are not changed by the model.

Keep the browser open after successful tasks and while waiting for user input, approval, CAPTCHA, MFA, or manual browser steps. A completed response is not a request to close the browser. Resume in the same session after the user replies, and close only when the user explicitly asks.

This is an agent behavior policy, not an indefinite browser-lifetime guarantee. Hosted compute and browser-service idle limits still apply.
