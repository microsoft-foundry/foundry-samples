# Foundry Toolbox Autopilot

- Keep the sample focused on one Agent Framework agent consuming one dedicated,
  read-only Foundry Toolbox with anonymous Microsoft Learn and native Bing-backed
  Foundry Web Search. Only public search terms and URLs belong in tool arguments.
  Write actions, interactive consent, approval cards, workflows, and conversation
  history are out of scope.
- `agent/app.py` uses `ActivityAgentServerHost(digital_worker=True)` and its
  unmodified M365 stack. Preserve `/activity/messages`, the Teams selectors,
  and separate `azd deploy` / `azd ai agent publish` workflows.
- Create the agent and `FoundryToolbox` inside each Activity turn using
  `agent/toolbox.py:create_agent`. Never share MCP connections across turns:
  their background tasks inherit caller context at connection time. Preserve
  the SDK's platform headers for both model and Toolbox calls. Never synthesize
  user headers or call IDs.
- Use managed identity for hosted model and Toolbox access, and Azure CLI
  credentials for local execution. Neither source requires downstream user
  credentials, project connections, or secrets. Native Web Search is billed
  under Bing grounding terms, not a free anonymous external MCP service.
- Validate that `TOOLBOX_ENDPOINT` belongs to the configured Foundry project
  before sending a bearer token. Keep the positive allowlist in
  `agent/toolbox.py` consistent with `toolbox.yaml`; require both sources.
  Native Web Search is `type: web_search`, named `web_search`, with a required
  string `search_query`. Preserve source links in its embedded text-resource
  results. Distinguish official Microsoft guidance from other web sources.
- Learn wire names may use `.` or `___` between the server label and tool.
  Accept only the explicit aliases in `TOOL_NAMES`, reject duplicate aliases,
  and use exact discovered names for SDK filtering and calls. Native
  `web_search` is unprefixed; do not add an MCP server label or rename it.
- Preserve resource cleanup and explicit errors for empty tools, missing
  sources, unsupported approval policies, failed calls, and empty model replies.
- AgentServer owns telemetry initialization. Preserve the sensitive-content
  opt-out and disable only unused OpenAI Agents SDK instrumentation.
- Reuse the sibling guided-provisioning script and create/reuse Bicep pattern.
  Provisioning must not alter reused resources or role assignments. Manage the
  toolbox separately with `azd ai toolbox create --from-file toolbox.yaml`.
  Preserve its labels and read-only allowlists; copy azd's version-pinned MCP
  endpoint to `TOOLBOX_ENDPOINT`. When choosing a new version, refresh the
  endpoint from `azd ai toolbox show --output json` and redeploy.
- Use a capability-first README: short numbered setup steps, shared Hello World
  prerequisites and approval guidance, then
  example questions and expected Teams replies. Keep the sample-specific
  Toolbox requirements and provisioning/configuration/deployment commands here.
  Assume familiarity only with Hello World, not with other samples. Explain
  Agent Framework's value for this agent's tool handling without sample comparisons.
  Keep local development and offline tests out of the required deployment path.
  Focus the demonstration on questions and user-visible answers, not traces or
  SDK internals. Keep maintenance guidance brief; developer details belong here
  or in the source, not in a long post-demonstration appendix.
  Do not refer to development history or duplicate the full common setup guide.
- Keep `requirements.txt` fully pinned with cross-platform markers, including
  transitives. Do not make `pywin32` unconditional. Use Python 3.13 explicitly;
  use a fresh virtual environment when changing Python minor versions.
- Run `python -m unittest discover -s tests -v` in the sample environment.
  Tests use real SDKs with HTTP test transports; preserve both-source execution,
  concurrent caller isolation, Activity ingress, cleanup, and failure coverage.
  Offline transports do not prove live Foundry permissions or hosted deployment.
