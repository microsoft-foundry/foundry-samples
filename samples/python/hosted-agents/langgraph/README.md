# LangGraph Samples

This directory contains samples that demonstrate how to use [LangGraph](https://langchain-ai.github.io/langgraph/) together with [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting) to host agents on Foundry with different capabilities and configurations. Each sample includes a README with sample queries and any sample-specific notes.

Use the configuration-driven `langchain_azure_ai.agents.hosting.run` entrypoint by default. Use a protocol-specific host class only when the agent must customize request translation, unsupported protocol options, readiness behavior, or the lifetime of async resources. The [Responses Custom Host](responses/12-custom-host/) and [Invocations Custom Host](invocations/04-custom-host/) samples demonstrate the request-translation case.

## Samples

### Responses API

| #   | Sample                                                                | Description                                                                                                                                                                              |
| --- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | [Chat](responses/01-langgraph-chat/)                                  | A minimal LangGraph agent with two local tools (`get_current_time`, `calculator`), demonstrating multi-turn conversation via `previous_response_id`.                                     |
| 2   | [LangGraph Toolbox](responses/02-langgraph-toolbox/)                  | A LangGraph agent wired to a Foundry Toolbox that exposes `web_search` plus a connection-backed GitHub Copilot MCP tool, with OAuth consent surfacing.                                   |
| 3   | [Toolbox User Identity](responses/03-langgraph-toolbox-user-identity/) | A Toolbox-backed agent that propagates the hosted end-user identity to connection-backed tools.                                                                                          |
| 5   | [Workflows](responses/05-workflows/)                                  | A custom `StateGraph` chaining three specialized LLM nodes — slogan writer, legal reviewer, formatter — each seeing only the previous agent's output.                                    |
| 6   | [Files](responses/06-files/)                                          | A LangGraph agent with local filesystem tools and a Foundry-Toolbox `code_interpreter`, demonstrating session-uploaded file handling.                                                    |
| 7   | [Human-in-the-Loop](responses/07-human-in-the-loop/)                  | A LangGraph `StateGraph` that drafts a proposal and pauses for human review via `langgraph.types.interrupt`, serialized as `mcp_approval_request` + `function_call` output items.        |
| 8   | [Observability](responses/08-observability/)                          | A LangGraph agent with GenAI OpenTelemetry tracing enabled via `enable_auto_tracing()`, emitting spans, metrics, and logs to Application Insights.                                       |
| 9   | [Resilient](responses/09-resilient/)                                 | Resilient background Responses with durable checkpoints, recovery, cancellation, steering, and human approval.                                                                        |
| 10  | [Run](responses/10-run/)                                              | A minimal configuration-driven LangGraph agent hosted over the Responses protocol with the `langchain_azure_ai.agents.hosting.run` entrypoint.                                         |
| 11  | [Deep Agents](responses/11-deep-agents/)                              | A deep research agent with Toolbox tools and a Foundry-backed checkpointer. Uses the host class for async resource lifecycle management.                                               |
| 12  | [Custom Host](responses/12-custom-host/)                              | Extends a multi-turn chat agent with a locale header and custom location messages using `ResponsesHostServer`.                                                                         |
| 13  | [Custom Stores](responses/13-custom-store/)                          | Demonstrates implementing custom response and conversation-chain stores and wiring LangGraph checkpoints and long-term memory for Foundry-hosted or on-premises agents.              |

### Invocations API

| #   | Sample                                          | Description                                                                                                                                          |
| --- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | [Chat](invocations/01-langgraph-chat/)          | A minimal LangGraph agent with two local tools, demonstrating session state via `agent_session_id` (URL param / `x-agent-session-id` response header) backed by a LangGraph checkpointer. |
| 2   | [Resilient](invocations/02-resilient/)          | Resilient Invocations with durable checkpoints, recovery, cancellation, steering, and human approval. Uses the host class for options and server-lifetime resources.                    |
| 3   | [Run](invocations/03-run/)                      | A minimal configuration-driven LangGraph agent hosted over the Invocations protocol with the `langchain_azure_ai.agents.hosting.run` entrypoint and durable Foundry checkpoint state. |
| 4   | [Custom Host](invocations/04-custom-host/)      | Extends a multi-turn chat agent with a locale header and custom location messages using `InvocationsHostServer`.                                                                     |

### Agent-to-Agent (A2A)

| Sample                  | Description                                                                                                                                                                                                 |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [A2A delegation](a2a/)  | Two LangGraph Responses agents — a `concierge` that **delegates** math questions over A2A to a `math-expert` that publishes an incoming A2A endpoint + agent card. Wired with a `RemoteA2A` connection and an `a2a_preview` Toolbox loaded over MCP. |

## Running the Agent Host Locally

For the [Custom Stores sample](responses/13-custom-store/#choose-a-deployment-path),
choose between deploying the agent to Foundry Hosted Agents and running it
on-premises with Foundry models only. Its on-premises path does not require a
hosted-agent deployment. `AZURE_AI_API_KEY` is optional for that sample; without
it, authenticate an Azure identity for `DefaultAzureCredential`, for example
with `az login` during local development.

### Using `azd`

#### Prerequisites

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) and the AI agent extension: `azd ext install azure.ai.agents`
   - Authenticated: `azd auth login`

2. **Azure Subscription**

#### Create a new project

**No cloning required**. Create a new folder, point azd at the manifest on GitHub.

```bash
mkdir hosted-langgraph-agent && cd hosted-langgraph-agent

# Initialize from the manifest (replace with the sample you want to try)
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/01-langgraph-chat/azure.yaml
```

Follow the instructions from `azd ai agent init` to complete the agent initialization. If you don't have an existing Foundry project and a model deployment, `azd ai agent init` will guide you through creating them.

#### Provision Azure Resources

> This step is only needed if you don't have an existing Foundry project and model deployment.

Run the following command to provision the necessary Azure resources:

```bash
azd provision
```

This will create the following Azure resources:

- A new resource group named `rg-[project_name]-dev`. In this guide, `[project_name]` will be `hosted-langgraph-agent`.
- Within the resource group, among other resources, the most important ones are:
  - A new Foundry instance
  - A new Foundry project, within which a new model deployment will be created
  - An Application Insights instance
  - A container registry, which will be used to store the container images for the hosted agent

#### Set Environment Variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
# And any other environment variables required by the sample
```

Or in PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
# And any other environment variables required by the sample
```

> Note: The environment variables set above are only for the current session. You will need to set them again if you open a new terminal session. If you want to set the environment variables permanently in the azd environment, you can use `azd env set <name> <value>`.

#### Running the Agent Host

```bash
azd ai agent run
```

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

Open another terminal, **navigate to the project directory**, and run the following command to invoke the agent:

```bash
azd ai agent invoke --local "Hello!"
```

Or in another terminal, without navigating to the project directory, run the following command to invoke the agent:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hello!"}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Hello!"}').Content
```

> **Invocations protocol note:** The `curl` examples above target the Responses endpoint (`/responses`). For Invocations samples, the endpoint is `/invocations` and the request body uses `"message"` instead of `"input"`. Session continuity uses the `agent_session_id` URL parameter and the `x-agent-session-id` response header. See [`invocations/01-langgraph-chat/`](invocations/01-langgraph-chat/) for full examples.

### Using `python`

#### Prerequisites

1. An existing Foundry project
2. A deployed model in your Foundry project
3. Azure CLI installed and authenticated
4. Python 3.10 or later
5. [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment if you use the uv setup option

#### Running the Agent Host with Python

Clone the repository containing the sample code:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples/samples/python/hosted-agents/langgraph
```

#### Environment setup

1. Navigate to the sample directory you want to explore. Create a virtual environment:

   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\Activate

   # macOS/Linux
   source .venv/bin/activate
   ```

2. Install the sample dependencies using the dependency file present in the sample's service directory.

   For samples with `requirements.txt`, ensure `pip` is version 26.1 or newer (check with `pip --version`); older versions fail to resolve the samples' dependencies. Upgrade if needed, then install:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   For samples with `pyproject.toml`, use [`uv`](https://docs.astral.sh/uv/) to create and synchronize the locked environment:

   ```bash
   uv sync --frozen
   ```

3. Create a `.env` file with your Foundry configuration following the `.env.example` file in the sample.

4. Make sure you are logged in with the Azure CLI:

   ```bash
   az login
   ```

#### Running the Agent Host

From the sample's source directory, run the protocol selected by its `azure.yaml`:

```bash
python -m langchain_azure_ai.agents.hosting.run --protocol responses
```

The resilient Invocations, deep-agent, and custom-host exceptions use `python main.py` because they configure unsupported host behavior or manage resources for the server lifetime.

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

On another terminal, run the following command to invoke the agent:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hello!"}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Hello!"}').Content
```

> **Invocations protocol note:** See the [Invocations protocol note](#invoking-the-agent) above for the endpoint, body shape, and session-id mechanics used by Invocations samples.

## Deploying the Agent to Foundry

Once you've tested locally, deploy to Microsoft Foundry.

### With an Existing Foundry Project

If you already have a Foundry project and the necessary Azure resources provisioned, you can skip the setup steps and proceed directly to deploying the agent.

After running `azd ai agent init -m <azure.yaml>` and following the prompts to configure your agent, you will have a project ready for deployment.

### Setting Up a New Foundry Project

Follow the steps in [Using `azd`](#using-azd) to set up the project and provision the necessary Azure resources for your Foundry deployment.

### Deploying the Agent

Once the project is setup and resources are provisioned, you can deploy the agent to Foundry by running:

```bash
azd deploy
```

> The Foundry hosting infrastructure will inject the following environment variables into your agent at runtime:
>
> - `FOUNDRY_PROJECT_ENDPOINT`: The endpoint URL for the Foundry project where the agent is deployed.
> - `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of the model deployment in your Foundry project. This is configured during the agent initialization process with `azd ai agent init`.
> - `APPLICATIONINSIGHTS_CONNECTION_STRING`: The connection string for Application Insights to enable telemetry for your agent.

This will package your agent and deploy it to the Foundry environment, making it accessible through the Foundry project endpoint. Once it's deployed, you can also access the agent through the Foundry UI.

For the full deployment guide, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

Once deployed, learn more about how to manage deployed agents in the [official management guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent).
