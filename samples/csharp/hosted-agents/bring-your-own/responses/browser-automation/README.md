# Browser Automation Agent (C#, Bring Your Own Responses)

This sample implements the Responses agent loop directly with the .NET SDK and uses the GA Azure Playwright MCP tools published through a Foundry Toolbox.

## What it demonstrates

- MCP initialization and dynamic browser tool discovery with `tools/list`
- Conversion of MCP `inputSchema` values into Responses function tools
- Generic forwarding of every browser call through MCP `tools/call`
- Multiple named browsers, default-session selection, and cross-request reuse
- Model-written answers and exact live-view links, with filtered structured tool records
- Embedded skills for form filling and data extraction

Local `load_skill`, `create_session`, `end_session`, and `list_sessions` functions preserve skill loading and friendly session management. Browser operation names and schemas come from the Toolbox MCP server; the runtime adapts the session-ID argument to accept friendly names or default selection before forwarding calls.

## Key files

| Path | Purpose |
| --- | --- |
| `src/bat-csharp-byo/Program.cs` | Responses handler, dynamic tool loop, session tracking, and public tool summaries. |
| `src/bat-csharp-byo/utils/ToolboxClient.cs` | MCP initialize, `tools/list`, and `tools/call` client. |
| `src/bat-csharp-byo/utils/Constants.cs` | Local skill schema and system prompt. |
| `src/bat-csharp-byo/skills/` | Embedded task procedures loaded by the model. |
| `hooks/setup-toolbox.*` | Publishes the GA browser automation toolbox. |

## Configuration

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
TOOLBOX_NAME=browser-automation-tools
```

For local use, run `az login` so `DefaultAzureCredential` can authenticate the model and Toolbox calls.

Toolbox requests use Azure.Core's `BearerTokenAuthenticationPolicy` to cache and refresh tokens automatically. The MCP pipeline adds no automatic HTTP retries, and calls retain their 120-second timeout.

## Run locally

```bash
cd src/bat-csharp-byo
dotnet run
```

Invoke `http://localhost:8088/responses` with a Responses request containing an `input` value. Prefix a request with `/verbose` to include tool-call progress.

## Chat output and evaluation

Responses include structured `function_call` and `function_call_output` items with matching `call_id` values, followed by the final assistant message. These items are emitted regardless of `/verbose` and retained when rebuilding conversation history; unmatched tool items at a truncated history boundary are skipped with a warning.

In structured tool records, browser-call arguments are published as `{}`. Results from `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, and `browser_run_code` are replaced with an explicit omission notice, including when tool names have a Toolbox prefix. Known failures remain marked as failures. Other tool results and errors remain visible, but standard Playwright snapshot and generated-code sections are replaced with omission notices. JSON snapshot/screenshot fields, MCP image bodies, and live-view URL fields are also omitted, and known runtime live-view URLs are redacted from text. Local `load_skill` calls retain their arguments and results.

Chat contains the model's answer, not automatic copies of raw browser results. The application streams available live-view links when a browser opens and lists active live-view links in a separate message after the model's answer. `/verbose` adds tool-name progress messages, not raw result dumps. The internal model loop retains the original arguments and full results, including failures, with live-view URLs removed from model-visible tool output. Conversation history retains filtered tool records and chat messages.

Only the structured tool records are filtered. Chat still includes access-bearing live-view links, and model-generated answers may include requested page content. This separation is not a security boundary or a guarantee that evaluations cannot see sensitive details; evaluation input mapping must be configured separately. User input, logs, and separately enabled SDK telemetry can also contain sensitive data.

## Deploy

Run initialization from outside the sample directory:

```bash
azd ai agent init -t ./browser-automation/azure.yaml
azd provision
azd deploy
```

Provisioning creates or reuses an Azure Playwright workspace, creates its GA MCP connection, and publishes a `browser_automation` toolbox. Deployment assigns the required browser role to the hosted agent identity.

## Browser lifecycle

Use `create_session` to open named browsers such as `session1`, `form-browser`, and `scraper`. The runtime maps each name to its service `browserSessionId` and supplies the names, IDs, and last-used default in later requests. Browser tools accept either a friendly name or service ID in `browserSessionId`. Omitting it uses the default, creating a browser named `default` on the first browser action if no browser exists. Direct MCP creation receives an automatic `session-N` name.

For example: "Open session1 for the form and session2 for research", then "Continue the form in session1". `list_sessions` supplies active names and the default to the model. The runtime retains live-view URLs and displays their exact values in separate chat messages.

Browsers stay open after tasks and while waiting for input, CAPTCHA, MFA, or approval. Only an explicit user close request should invoke `end_session` or the discovered close tool; `end_session` accepts a name or `all`. Failed service closes leave the session tracked so the user can retry.

This preserves application behavior, not an indefinite browser-lifetime guarantee. Hosted compute and browser-service idle limits still apply; the named session registry is in process memory.
