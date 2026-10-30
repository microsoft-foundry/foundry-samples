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

Responses automatically publish the actual model-facing tool schemas in `response.tools`, including local skill/session functions and adapted browser tools. Foundry's **Evaluate against agent** workflow can use these definitions without a separate evaluation script.

Responses include structured `function_call` and `function_call_output` items with matching `call_id` values, followed by the final assistant message. These items are emitted regardless of `/verbose` and retained when rebuilding conversation history; unmatched tool items at a truncated history boundary are skipped with a warning.

Structured tool records retain actual model-generated arguments and text results, including browser snapshots, generated code, and evaluate/run-code results, so tool evaluators can inspect the evidence. Known failures remain marked as failures. Screenshot fields and MCP image bodies are replaced with omission notices. Live-view URL fields are omitted, and known runtime live-view URLs and recognized token patterns are redacted from result text. Local `load_skill` calls retain their arguments and results.

Chat contains the model's answer, not automatic copies of raw browser results. The application streams available live-view links when a browser opens and lists active live-view links in a separate message after the model's answer. `/verbose` adds tool-name progress messages, not raw result dumps. The internal model loop retains the original arguments and full results, including failures, with live-view URLs removed from model-visible tool output. Conversation history retains filtered tool records and chat messages.

Browser creation results omit the live-view URL without adding a replacement note. Chat links remain enabled, so evaluators can still flag unsupported links or strict-format violations; this change does not separate UI messages from evaluation input.

Actual tool arguments and text results can contain sensitive form values or page content and are exposed in Responses output, conversation history, and evaluations that consume them. Chat still includes access-bearing live-view links. The remaining result filtering is not a security boundary; use non-sensitive evaluation data and configure access and evaluation input mapping appropriately. User input, logs, and separately enabled SDK telemetry can also contain sensitive data.

The system prompt and form-filler skill guide the model to use control-specific tools, refresh page state after failures, and retry only unfinished work. They require checking submission outcomes before retrying. These are model instructions, not automatic retries or a guarantee of error-free browser actions.

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
