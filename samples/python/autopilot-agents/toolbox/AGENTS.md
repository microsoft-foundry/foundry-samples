# Coding Agent Instructions - Toolbox Autopilot

This sample is a Microsoft Foundry hosted agent that uses the M365 Agents SDK
and Activity protocol to respond to Microsoft Teams messages. Its model can
discover and invoke tools through a Foundry Toolbox MCP endpoint.

## Deployment mode

- `azure.yaml` declares the Foundry project, model deployment, toolbox, and
  directly deployed Python agent.
- `ActivityAgentServerHost` owns `POST /activity/messages`, readiness, storage,
  connection configuration, and OpenTelemetry setup.
- Create the Agent Framework agent and `FoundryToolbox` inside each Activity
  request. The toolbox captures request-scoped Foundry caller context when its
  MCP connection opens.
- Keep `TOOLBOX_ENDPOINT` mapped to the toolbox service output in `azure.yaml`.
- Microsoft 365 publication is a separate `azd ai agent publish` action.

## Key files

- `azure.yaml` - project, toolbox, hosted agent, and Autopilot publication
- `main.py` - direct code deployment entry point
- `agent/app.py` - Teams handlers and request-scoped toolbox agent
- `agent/activity_routing.py` - supported Teams conversation selectors
- `requirements.txt` - fully resolved runtime dependencies
- `README.md` - complete deployment and publication walkthrough

Do not commit Foundry Toolkit-generated `.vscode` files.

## Dependency workflow

Keep `requirements.txt` fully resolved with exact direct and transitive pins.
Allow prerelease packages because the Activity and toolbox hosting integrations
are previews.

## Development workflow

Use `azd up` for the initial project, toolbox, and agent deployment. Use
`azd deploy` for code-only changes and `azd deploy --all` after changing the
toolbox or model configuration. Do not republish the Microsoft 365 app for
code-only changes.
