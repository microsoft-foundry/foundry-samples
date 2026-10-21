# LangGraph Handoff — Responses Protocol (VoiceLive)

Multi-agent customer support handoff demo using LangGraph, served as a hosted agent through the Responses protocol. Optimized for voice-first scenarios.

## Prerequisites

1. Python 3.12 or later.
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later,
   installed and available on `PATH`.
3. Azure Developer CLI (`azd`) 1.34.2 or later with the Foundry extension for
   the `azd` workflow.
4. Azure CLI authentication (`az login`) for local model access.

## Architecture

Three specialized agents with handoff:

- **Triage Agent** — Routes requests to the appropriate specialist
- **Refund Agent** — Handles refund requests (lookup order, submit refund)
- **Order Agent** — Handles replacements/exchanges (submit replacement)

Agents transfer control via handoff tools. Status updates stream in real-time as agents hand off and tools execute.

## Local Development

#### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint (auto-injected in hosted containers) |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name in the Foundry project |

#### Run Locally

```bash
cd src/handoff-langgraph-responses-voicelive
cp .env.example .env
# Edit .env with your values
python -m pip install uv
uv sync --frozen
uv run --no-sync python main.py
```

#### Test

```bash
# Streaming
curl -sS -N -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "I need a refund for order 12345", "stream": true}'
```

## Using [`azd`](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd)

No cloning required. Create a new folder, point azd at the manifest on GitHub, and it sets up the sample and adopts its azure.yaml as the project manifest and configures your environment automatically:

```bash
# Create a new folder for the agent and navigate into it
mkdir handoff-agent-sample && cd handoff-agent-sample

# Initialize from the manifest — azd reads it, downloads the sample,
# and adopts its azure.yaml as the project manifest and configures your environment
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voicelive/handoff-langgraph-responses-voicelive/azure.yaml

# Provision Azure resources (Foundry project, model deployment, App Insights)
azd provision

# Run the agent locally (uses uv to sync dependencies, then starts the agent)
azd ai agent run
```

The agent starts on http://localhost:8088/. To invoke it:

```bash
azd ai agent invoke --local "I need a refund for order 12345"
```
### Deploying the Agent to Microsoft Foundry

Once you've tested locally, deploy to Microsoft Foundry:

```bash
# Provision Azure resources (skip if already done during local setup)
azd provision

# Build, push, and deploy the agent to Foundry
azd deploy
```

After deploying, invoke the agent running in Foundry:

```bash
azd ai agent invoke "I need a refund for order 12345"
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).
