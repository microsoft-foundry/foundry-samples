# What this sample demonstrates

An AWS-to-Azure migration assistant built with the [Strands Agents SDK](https://strandsagents.com) and hosted on Microsoft Foundry. It shows how to bring an existing Strands agent to Foundry Hosted Agents with Microsoft Entra ID auth, multi-agent orchestration, MCP tools, and platform-managed conversation history.

## How it works

- **Model:** Strands' `OpenAIResponsesModel` calls a Foundry model deployment through the project's OpenAI-compatible endpoint (`{FOUNDRY_PROJECT_ENDPOINT}/openai/v1`). Auth uses `DefaultAzureCredential`, so no API key is needed.
- **Agents as tools:** a `service_mapper` specialist Strands agent is exposed to the orchestrator with `Agent.as_tool()`.
- **MCP:** the orchestrator grounds answers with the public [Microsoft Learn MCP server](https://learn.microsoft.com/training/support/mcp) through Strands' `MCPClient`. Only the `microsoft_docs_search` tool is loaded.
- **Hosting:** `ResponsesAgentServerHost` from `azure-ai-agentserver-responses` serves the Responses protocol. Each request builds a fresh Strands `Agent`, seeds it with the conversation history from `context.get_history()`, and streams text deltas from `agent.stream_async()` back to the caller.

See `main.py` for the implementation.

Follow the shared [Python startup configuration](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/README.md#python-startup-configuration)
for deployment environments and dependency compatibility.

### Coming from AWS?

If you already run a Strands agent on Amazon Bedrock or Bedrock AgentCore, the agent code stays the same. Swap the model provider and wrap the agent in the Foundry host:

| Strands on AWS | Strands on Foundry Hosted Agents |
| --- | --- |
| `BedrockModel(model_id=...)` | `OpenAIResponsesModel(client=AsyncOpenAI(base_url=f"{endpoint}/openai/v1", api_key=<Entra token provider>), model_id=<deployment>)` |
| `BedrockAgentCoreApp` + `@app.entrypoint` | `ResponsesAgentServerHost` + `@app.response_handler` |
| IAM role | Agent managed identity with Azure RBAC |
| `agentcore launch` | `azd deploy` |

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name in your Foundry project. |
| `FOUNDRY_PROJECT_ENDPOINT` | Local only | Injected automatically in hosted containers and by `azd ai agent run`. |
| `LEARN_MCP_URL` | No | Overrides the MCP server URL. Defaults to `https://learn.microsoft.com/api/mcp`. |

## Prerequisites

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **Python 3.12 or later.**
3. **Roles (RBAC):** `Azure AI User` on the Foundry project for the identity that runs the agent locally.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`) 1.27.1 or later** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-agent && cd my-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/responses/strands-agents/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "We run on AWS Lambda, DynamoDB, and SQS. What should we use on Azure?"
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "We run on AWS Lambda, DynamoDB, and SQS. What should we use on Azure?"
```

Then ask a follow-up in the same conversation, such as `And Amazon S3?`. The agent answers with the earlier context because the platform replays conversation history.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then run `az login` in the VS Code integrated terminal.

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install the locked dependency graph with uv 0.11.7:

  ```bash
  cd src/strands-agents
  uv sync --frozen
  ```

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Copy `.env.example` to `.env`, set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and sign in with `az login`.
2. Start the agent: `uv run --env-file .env python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to identify the service source folder and auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Customization

- **Use your own MCP server:** set `LEARN_MCP_URL`, or replace the `MCPClient` in `_build_agent()`. Pass `headers=` for authenticated servers, and change `tool_filters` to choose which tools load.
- **Add specialists:** create another Strands `Agent` and add `agent.as_tool()` to the orchestrator's `tools` list.
- **Add Python tools:** decorate functions with `@strands.tool` and pass them in `tools`.

## Troubleshooting

- **`KeyError: 'AZURE_AI_MODEL_DEPLOYMENT_NAME'`** → the variable is not set → set it in `.env` or the azd environment.
- **`401` or `403` from the model** → the identity lacks access to the project → assign `Azure AI User` on the Foundry project and run `az login` again.
- **The agent answers without citing Microsoft Learn** → the container can't reach `learn.microsoft.com` → check outbound network access, or point `LEARN_MCP_URL` at a reachable MCP server.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [OpenAI Agents SDK sample](../openai-agents-sdk/)
- [Strands Agents documentation](https://strandsagents.com/latest/documentation/docs/)
