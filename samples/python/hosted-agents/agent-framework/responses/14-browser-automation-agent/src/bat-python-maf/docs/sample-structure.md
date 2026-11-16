# Sample structure

This sample hosts one Agent Framework browser agent over the Responses
protocol. Browser operations are supplied by the GA Azure Playwright MCP
server through a Foundry Toolbox.

## Layers

| Layer | Path | Purpose |
| --- | --- | --- |
| Runtime | `main.py`, `utils/` | Builds and hosts the agent, connects the Toolbox MCP server, logs calls, and injects exact live-view links. |
| Prompt | `prompts/base.md` | Defines browser-session lifecycle and safe automation behavior. |
| Skill | `skills/azure-playwright-browser-automation/SKILL.md` | Operational guidance for the dynamically discovered browser tools. |
| Toolbox | Foundry Toolbox | Discovers browser tools with `tools/list` and forwards calls with `tools/call`. |
| Deployment | `azure.yaml`, `hooks/`, `infra-modules/` | Provisions the Playwright workspace, GA MCP connection, toolbox, hosted agent, and RBAC. |

The browser tool schemas are not defined in the application. Agent Framework
loads them from the Toolbox MCP endpoint. `create_browser_session` returns a
`browserSessionId` for subsequent calls and a `liveViewUrl`; middleware removes
the URL from model-visible output and writes the exact link directly to the
Responses stream.

The base prompt contains general browser behavior. Add a skill only for
repeatable domain-specific procedures, and keep tool names aligned with the
schemas returned by MCP discovery.
