**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# OpenClaw incident briefing with Foundry Hosted Agents

Turn a set of incident updates into a brief for an on-call handoff. OpenClaw
keeps its existing conversation and messaging channels. Its plugin submits the
updates to a Microsoft Foundry Hosted Agent, and a second tool retrieves the
result. The hosted worker uses the Responses API to extract facts and prepare a
brief with impact, a timeline, suggested next actions, and unknowns. It does
not fetch incident data or take remediation actions.

The worker exposes the **Invocations** protocol. It acknowledges a request
before the briefing completes and runs the work as a resilient task. The plugin
uses the platform invocation ID to retrieve the result; OpenClaw and the
hosted worker can use different model deployments.

## Prerequisites

- An existing Foundry project with a deployed model that supports the
  Responses API. The deployment identity and hosted runtime identity need the
  required project and model permissions; the OpenClaw identity also needs
  permission to invoke the agent.
- Azure CLI (`az`), Azure Developer CLI (`azd`) 1.35.0 or later with the
  `microsoft.foundry` extension (including `azure.ai.agents` 1.0.0-beta.18 or
  later), and access to the project. Sign in with both `az login` and
  `azd auth login`.
- [OpenClaw](https://docs.openclaw.ai/) 2026.5.17 or later, a Node.js version
  supported by your OpenClaw release, and a configured tool-capable OpenClaw
  model. This model is separate from the worker's Foundry model.
- Python 3.12+ and [uv](https://docs.astral.sh/uv/) for local development.

Install the Foundry extension if needed:

```bash
azd ext install microsoft.foundry
```

## Deploy the worker

From this directory, select a new `azd` environment and point it at your
existing project. Use the actual model **deployment name**, not just the model
family name:

```bash
azd env new openclaw-brief
azd env set FOUNDRY_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<model-deployment>"
azd deploy
```

The `azure.yaml` manifest deploys the Python source directly; this sample does
not require a container registry. It disables GenAI message-content telemetry
for the worker.

Create a stable hosted session for the plugin. Pick a unique session ID and
keep it for retries and status checks:

```bash
azd ai agent sessions create openclaw-incident-brief --session-id "incident-brief-session"
```

Wait for the session to become active before using the plugin. If the session
expires, create a new session and update the plugin configuration; results in
the old session should not be assumed available through the new one.

## Configure OpenClaw

Install the plugin's locked dependencies and note the absolute plugin path:

```bash
cd plugin
npm ci
pwd
```

Merge the following into your OpenClaw configuration. Replace the path,
project endpoint, agent name if changed, and the session ID created above.
Merge the tool names into any existing `tools.alsoAllow` list; keep your other
configuration. If you have restrictive plugin or per-agent tool allowlists,
add this plugin and its tools to those lists as well.

```json
{
  "plugins": {
    "load": {
      "paths": ["/absolute/path/to/openclaw-incident-brief/plugin"]
    },
    "entries": {
      "foundry-incident-brief": {
        "enabled": true,
        "config": {
          "projectEndpoint": "https://<resource>.services.ai.azure.com/api/projects/<project>",
          "agentName": "openclaw-incident-brief",
          "sessionId": "incident-brief-session"
        }
      }
    }
  },
  "tools": {
    "alsoAllow": ["foundry_incident_brief_start", "foundry_incident_brief_status"]
  }
}
```

Restart OpenClaw or reload its configuration. The plugin uses Azure
`DefaultAzureCredential` in the OpenClaw process: use `az login` for local
development or configure an appropriate managed identity in Azure. The
credential must be available to the process running OpenClaw, not just the
interactive user's shell.

## Try it

Send this to OpenClaw through your configured channel:

```text
Use foundry_incident_brief_start with requestId INC-2026-42-rev1 and these updates:
09:12 UTC: Checkout failures rose to 14% in Canada after release 42; the
number of affected customers is unknown.
09:18 UTC: The on-call team is investigating the release and database latency.
09:26 UTC: Database latency returned to normal, but checkout failures remain
at 12%.
09:33 UTC: Support reports several customer tickets. No one has confirmed
rollback ownership or resolution.

Return the invocation ID and status. Do not invent a completed brief.
```

If the status is `pending`, wait and send a follow-up using the returned ID:

```text
Use foundry_incident_brief_status for invocationId <the-returned-invocation-id>
and show the brief if it is complete.
```

Check again later if it is still pending. A completed brief should distinguish
the reported failure rates from suggested actions and identify the unknown
customer count, rollback owner, cause, and resolution. A failed result reports
an error instead of a brief.

## Retry and isolation considerations

- `requestId` identifies one snapshot of updates within the configured
  session. Repeating the same ID and updates returns the same job; different
  updates with that ID are rejected with HTTP 409. Use a new ID for a revised
  snapshot. Each POST can receive a different invocation ID, so use the ID
  returned by that POST for its status check.
- State is stored with user isolation enabled and includes the hosted session.
  Recovery can repeat an interrupted model call, so this is not an
  exactly-once execution guarantee.
- A job has a three-minute budget from its durable reservation time, including
  recovery. If a task cannot persist its failure, the next successful status
  check or repeated submission after that deadline marks the pending job
  failed. This is lazy reconciliation, not an automatic notification or a
  guarantee that storage remains available. Late model output is not accepted
  as a completed brief.
- A shared OpenClaw credential and session represent the same Foundry
  identity. They do **not** isolate individual OpenClaw users. Restrict who
  can use these tools and do not use this sample as a multi-tenant boundary.
- The sample does not schedule polling or send notifications automatically.
  Configure OpenClaw separately if you want to schedule a later status check.

## Local checks

```bash
cd src/incident-brief
uv sync --frozen
uv run --no-sync python -m pytest -q

cd ../../plugin
npm ci
npm test
```

The included cloud contract requires a completed brief. A successful initial
acknowledgement alone does not prove that the hosted task completed.
