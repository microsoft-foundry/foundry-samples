# Coding Agent Instructions

This sample is a **Microsoft Foundry hosted agent** that uses
[`azure-ai-agentserver-activity`](https://pypi.org/project/azure-ai-agentserver-activity/)
and the M365 Agents SDK to respond to Microsoft Teams messages, published as a
**Microsoft 365 Autopilot** (digital worker) rather than a single-tenant Teams
bot. The platform handles hosting, security, scaling, and observability.

## Deployment mode

- **Direct code deployment:** `azure.yaml` declares the Python runtime and
  `main.py` entry point (`kind: hosted`, `codeConfiguration`). `azd deploy`
  packages and deploys the agent directly — no Dockerfile or Azure Container
  Registry build.
- **Activity ingress:** hosted Activity protocol traffic is forwarded to
  `POST /activity/messages`.
- **Bring your own project:** this sample does not provision infrastructure
  (no `infra:` block). It deploys into an **existing** Foundry project
  supplied by the active `azd` environment (`AZURE_SUBSCRIPTION_ID`,
  `AZURE_LOCATION`, `AZURE_AI_PROJECT_ID`, `FOUNDRY_PROJECT_ENDPOINT`). Do not
  run `azd provision` or `azd up`.
- **Digital-worker auth model:** `main.py` constructs
  `ActivityAgentServerHost(digital_worker=True)`. Outbound Bot Connector
  tokens are minted from the agent's managed identity **blueprint** via
  federated identity, matching the tenant-scoped Autopilot publishing model
  declared under `activity.publish` in `azure.yaml`.
- Microsoft 365 publication is a separate, explicit action performed with
  `azd ai agent publish` using the metadata in `azure.yaml`.

## Key files

- `azure.yaml` — hosted-agent service, direct code deployment, and the
  `activity.useCase: digital_worker` / `activity.publish` Autopilot metadata
- `main.py` — the activity handlers (`message` echoes the user's text;
  `conversationUpdate` welcomes new members)
- `requirements.txt` — Python runtime dependencies

## Development workflow

The **Azure Developer CLI (`azd`)** manages the full lifecycle:

```bash
azd deploy              # Deploy the code to the existing Foundry project
azd ai agent publish     # Publish the Microsoft 365 Autopilot (separate step)
```

Activity agents are push-based: the agent replies out-of-band through the Bot
Connector, so `azd ai agent invoke` (which reads a synchronous response body)
does **not** apply here. Test a deployed agent by chatting with it in
**Microsoft Teams** once the blueprint is approved and an instance is created
(see [README.md](README.md)). For a local terminal loop, POST a synthetic
activity to `http://localhost:8088/activity/messages` with a `serviceUrl`
pointing at a local catcher.

## Microsoft Foundry Skill

Install the **Microsoft Foundry Skill** for guided deployment, evaluation, and troubleshooting workflows.

Direct install (preferred, works with any coding agent):

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

Or install the Azure Skills Plugin:

- **Copilot CLI**: `/plugin marketplace add microsoft/azure-skills` then `/plugin install azure@azure-skills`
- **Claude Code**: `/plugin install azure@claude-plugins-official`

Then ask naturally, e.g. `Use the Microsoft Foundry Skill to deploy this agent.`

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Publish an Autopilot in Microsoft Agent 365](https://learn.microsoft.com/azure/foundry/agents/how-to/agent-365)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
