# What this sample demonstrates

A fictional SaaS support desk hosted on Microsoft Foundry. It uses the
[OpenAI Agents SDK](https://github.com/openai/openai-agents-python) to look up
cases through MCP and hand them off to billing or technical specialists.

## How it works

1. The Responses host receives a request and loads platform-managed conversation
   history.
2. The triage agent calls the local, read-only MCP server's `lookup_case` tool.
3. If the case exists, an SDK handoff routes it to the appropriate specialist.
   The specialist calls `get_knowledge_article` and cites the article in its answer.
4. The SDK streams text through `ResponsesAgentServerHost`. Each request owns
   its model client, agents, and MCP subprocess; they are closed on completion
   or cancellation.

The MCP data is **fictional and read-only**. The agents cannot change accounts,
issue refunds, or update SSO configuration. Replace the sample data and tools
with authorized integrations for a real support system. The model uses the
Foundry Responses API with Microsoft Entra ID; no OpenAI API key is required.

Follow the shared [Python startup configuration](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/README.md#python-startup-configuration).

### Try these cases

| Case | Example input | What to look for |
| --- | --- | --- |
| `BILL-1042` | `Why does case BILL-1042 still show 12 seats when we reduced to 8?` | Billing explains that reductions apply at the next renewal, without proration, and cites `BILL-RENEWAL`. |
| `TECH-2048` | `Investigate TECH-2048 and suggest next steps.` | Technical explains the expired SSO certificate and cites `TECH-SSO-CERT`. |
| `MISSING-1` | `Look up MISSING-1. If it doesn't exist, say case not found.` | Triage reports that the case was not found rather than inventing details. |

After the billing question, ask `When does the reduction take effect?` in the
same conversation to see history in action.

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | The name of a Responses-capable model deployment in the Foundry project. |
| `FOUNDRY_PROJECT_ENDPOINT` | Local manual run | Project endpoint; injected automatically by `azd ai agent run` and hosted deployment. |

## Prerequisites

1. A Foundry project with a deployed model, or permission to create one.
2. Python 3.12 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later.
3. A local Azure identity and a hosted agent identity with permission to call
   the model deployment in the project.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

Install [azd](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
1.27.1 or later and the Foundry extension, then authenticate:

```bash
azd ext install microsoft.foundry
azd auth login
```

### Initialize the agent project

```bash
mkdir support-triage && cd support-triage
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/responses/openai-agents-sdk-triage/azure.yaml
```

Follow the prompts to select a project and model deployment. Always set the
deployment name explicitly: provisioning does not necessarily populate this
environment value. For a new project using the manifest's default deployment:

```bash
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5.4-mini
```

For an existing deployment or a custom deployment name, use its name instead:

```bash
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<deployment-name>"
```

### Provision Azure resources (if needed)

If you are creating a project and model deployment:

```bash
azd provision
```

Skip provisioning when reusing an existing project and deployment.

### Run the agent locally

```bash
azd ai agent run
```

The host listens on `http://localhost:8088`.

### Invoke the local agent

In another terminal in the project directory:

```bash
azd ai agent invoke --local --new-conversation "Why does BILL-1042 still show 12 seats when we reduced to 8?"
azd ai agent invoke --local --session-id "<session-id>" --conversation-id "<conversation-id>" "When does the reduction take effect?"
```

For the follow-up, copy the session and conversation IDs from the first command's
output. Try the technical and missing cases above with `--new-conversation`.

### Deploy to Foundry

```bash
azd deploy
```

See [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke --new-conversation "Investigate TECH-2048 and suggest next steps."
```

## Option 2: VS Code (Foundry Toolkit)

Install [VS Code](https://code.visualstudio.com/), the
[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio),
the Python extension, and Azure CLI; run `az login` in the terminal.

From the sample folder, install the locked dependencies:

```bash
cd src/openai-agents-sdk-triage
uv sync --frozen
```

Select the resulting `.venv` as the Python interpreter. Press **F5** to run
with the Toolkit and Agent Inspector, or run manually:

```bash
cp .env.example .env
# Set the project endpoint and model deployment in .env.
uv run --no-sync --env-file .env python main.py
```

Open **Foundry Toolkit: Open Agent Inspector** and send one of the case prompts.
To deploy, run **Foundry Toolkit: Deploy Hosted Agent**, choose code deployment,
and select your Foundry project.

## Tests and customization

Run local integration tests from `src/openai-agents-sdk-triage`:

```bash
uv run --no-sync python -m unittest discover -s tests -v
```

The tests use a scripted model but the real SDK runner, handoffs, and MCP
subprocess. The cloud test spec separately defines live model scenarios.
Cloud log assertions are shared across the test run; they are not per-turn
correlation.

To adapt the sample, replace `case_server.py` with an authenticated support
system, define appropriate read/write permissions and approvals, and update the
specialist instructions and tool filters. The sample's local MCP server is not
an example of production authorization.

## Troubleshooting

- **Missing endpoint or model:** set `FOUNDRY_PROJECT_ENDPOINT` and
  `AZURE_AI_MODEL_DEPLOYMENT_NAME`, or use the azd environment.
- **Model deployment not found:** use the deployment name from the selected
  Foundry project, not the underlying model name.
- **Model access denied:** grant the local or hosted identity permission to
  invoke the selected deployment.
- **MCP startup failure:** ensure `case_server.py` is present next to `main.py`
  and the locked dependencies are installed.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [OpenAI Agents SDK getting-started sample](../openai-agents-sdk/)
