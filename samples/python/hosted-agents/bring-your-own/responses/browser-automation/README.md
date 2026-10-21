# Browser Automation Agent (Python, Bring Your Own Responses)

This sample implements the Responses agent loop directly with the Python SDK and uses the GA Azure Playwright MCP tools published through a Foundry Toolbox.

## What this sample demonstrates

- MCP initialization and dynamic browser-tool discovery with `tools/list`
- Conversion of MCP `inputSchema` values into Responses function tools
- Generic forwarding of browser calls through MCP `tools/call`
- Multiple named browsers, default-session selection, and cross-request reuse
- Model-written answers and exact live-view links, with filtered structured tool records
- Local skills for form filling and data extraction

Local `load_skill`, `create_session`, `end_session`, and `list_sessions` functions preserve skill loading and friendly session management. Browser operation names and schemas come from the Toolbox MCP server; the runtime adapts the session-ID argument to accept friendly names or default selection before forwarding calls.

## How it works

1. The runtime connects to the configured Toolbox MCP endpoint.
2. It initializes MCP and discovers browser tools through `tools/list`.
3. MCP schemas are converted into Responses function-tool definitions.
4. Model tool calls are forwarded generically through `tools/call`.
5. Friendly session names are mapped to service browser IDs across requests.
6. The model loop uses full browser arguments and results, with `liveViewUrl` removed from tool output. Chat contains model-written answers and exact runtime-provided live-view links, while structured tool records are filtered.

## Key files

| Path | Purpose |
| --- | --- |
| `src/bat-python-byo/main.py` | Responses handler, dynamic tool loop, session tracking, and public tool summaries. |
| `src/bat-python-byo/utils/toolbox.py` | MCP initialize, `tools/list`, and `tools/call` client. |
| `src/bat-python-byo/utils/constants.py` | Local skill schema and system prompt. |
| `src/bat-python-byo/skills/` | Optional task procedures loaded by the model. |
| `hooks/setup-toolbox.*` | Publishes the GA browser automation toolbox. |

## Prerequisites

- An Azure AI Foundry project with a deployed chat model
- Azure CLI and Azure Developer CLI
- Python 3.12 or later
- `uv`

The provisioning hook can create a Playwright workspace when the current identity has permission. Set `PLAYWRIGHT_SERVICE_RESOURCE_ID` to reuse an existing workspace.

## Configuration

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
TOOLBOX_NAME=browser-automation-tools
```

Run `az login` before starting locally so `DefaultAzureCredential` can authenticate model and Toolbox calls.

Toolbox requests use Azure Identity's `get_bearer_token_provider` for SDK-managed token caching and refresh. MCP calls retain their 120-second timeout without adding automatic HTTP retries.

## Option 1: Azure Developer CLI

Initialize from a directory outside the sample:

```bash
azd ai agent init -t ./browser-automation/azure.yaml
azd provision
```

The `postprovision` hook creates or reuses the Playwright workspace, creates the GA MCP connection, and publishes the `browser_automation` toolbox.

Run and invoke locally:

```bash
azd ai agent run
azd ai agent invoke --local --new-session "Open https://example.com and report the page title."
azd ai agent invoke --local "Follow the first link using the same browser session."
```

Deploy and invoke:

```bash
azd deploy
azd ai agent invoke --new-session "Open https://example.com and report the page title."
```

The `postdeploy` hook assigns the browser role required by the configured project or hosted-agent identity.

## Option 2: VS Code

Install the Foundry Toolkit and Python extensions. After initialization, select the generated virtual environment and press **F5** to run the agent and open Agent Inspector.

To run manually:

```bash
cd src/bat-python-byo
uv sync --frozen --python 3.12
uv run --no-sync python main.py
```

Invoke the local Responses endpoint:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Open https://example.com and report the page title."}'
```

Prefix a request with `/verbose` to include tool-call progress in the streamed response.

## Chat output and evaluation

Responses include structured `function_call` and `function_call_output` items with matching `call_id` values, followed by the final assistant message. These items are emitted regardless of `/verbose` and retained when rebuilding conversation history; unmatched tool items at a truncated history boundary are skipped with a warning.

In structured tool records, browser-call arguments are published as `{}`. Results from `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, and `browser_run_code` are replaced with an explicit omission notice, including when tool names have a Toolbox prefix. Known failures remain marked as failures. Other tool results and errors remain visible, but standard Playwright snapshot and generated-code sections are replaced with omission notices. JSON snapshot/screenshot fields, MCP image bodies, and live-view URL fields are also omitted, and known runtime live-view URLs are redacted from text. Local `load_skill` calls retain their arguments and results.

Chat contains the model's answer, not automatic copies of raw browser results. The application streams available live-view links when a browser opens and lists active live-view links in a separate message after the model's answer. `/verbose` adds tool-name progress messages, not raw result dumps. The internal model loop retains the original arguments and full results, including failures, with live-view URLs removed from model-visible tool output. Conversation history retains filtered tool records and chat messages.

Only the structured tool records are filtered. Chat still includes access-bearing live-view links, and model-generated answers may include requested page content. This separation is not a security boundary or a guarantee that evaluations cannot see sensitive details; evaluation input mapping must be configured separately. User input, logs, and separately enabled SDK telemetry can also contain sensitive data.

## Browser lifecycle

Use `create_session` to open named browsers such as `session1`, `form-browser`, and `scraper`. The runtime maps each name to its service `browserSessionId` and supplies the names, IDs, and last-used default in later requests. Browser tools accept either a friendly name or service ID in `browserSessionId`. Omitting it uses the default, creating a browser named `default` on the first browser action if no browser exists. Direct MCP creation receives an automatic `session-N` name.

For example: "Open session1 for the form and session2 for research", then "Continue the form in session1". `list_sessions` supplies active names and the default to the model. The runtime retains live-view URLs and displays their exact values in separate chat messages.

Browsers stay open after tasks and while waiting for input, CAPTCHA, MFA, or approval. Only an explicit user close request should invoke `end_session` or the discovered close tool; `end_session` accepts a name or `all`. Failed service closes leave the session tracked so the user can retry.

This preserves application behavior, not an indefinite browser-lifetime guarantee. Hosted compute and browser-service idle limits still apply; the named session registry is in process memory.

## CI and non-interactive provisioning

Set at least one of the following before `azd provision --no-prompt`:

```bash
azd env set PLAYWRIGHT_SERVICE_RESOURCE_ID "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.LoadTestService/playwrightWorkspaces/<name>"
azd env set PLAYWRIGHT_AUTH_TYPE "ProjectManagedIdentity"
```

To create a workspace instead:

```bash
azd env set PLAYWRIGHT_REGION "eastus"
azd env set PLAYWRIGHT_AUTH_TYPE "ProjectManagedIdentity"
```

Supported authentication values are `ProjectManagedIdentity`, `AgenticIdentityToken`, and interactive `ApiKey`.

## Customize the sample

- Edit `utils/constants.py` to change the system prompt or local skill tool.
- Add skill documents under `skills/`.
- Adjust MCP forwarding and sanitization in `utils/toolbox.py`.
- Change hosted resources in `azure.yaml`.
