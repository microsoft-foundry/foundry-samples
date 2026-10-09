<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# LangGraph Toolbox User Identity Agent (Responses)

This sample hosts a LangGraph ReAct agent on Microsoft Foundry over the
Responses protocol using
[`langchain_azure_ai.agents.hosting.run`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting).
It loads tools from a Foundry Toolbox through
`langchain_azure_ai.tools.AzureAIProjectToolbox`.

The layered deployment provisions three MCP integrations:

- WorkIQ Mail with `UserEntraToken`
- WorkIQ Calendar with `UserEntraToken`
- GitHub MCP with managed OAuth2

The toolbox is named `langgraph-toolbox-user-identity-tools` so it does not
collide with shared toolboxes in the Foundry project.

## How it works

1. The Foundry infrastructure layer provisions the project and model.
2. The dependent Bicep layer provisions the connections before the toolbox and
   hosted agent are deployed.
3. `hosting.run` loads the graph factory from `langgraph.json`, exposes the
   OpenAI-compatible `/responses` endpoint, and manages Responses streaming and
   conversation history.
4. The async graph factory uses `AzureAIProjectToolbox` to resolve
   `TOOLBOX_NAME` and load the toolbox tools as LangChain tools.
5. `langchain.agents.create_agent` builds the LangGraph ReAct agent.
6. If a connection requires consent, the tool error handler recognizes MCP
   error `-32006` and returns the validated consent URL to the caller.

## Prerequisites

- Python 3.12+
- Azure Developer CLI (`azd`) 1.25 or later
- The Microsoft Foundry `azd` extension
- An Azure subscription where you can create Foundry resources

Install the extension and sign in:

```bash
azd ext install microsoft.foundry
azd auth login
```

## Initialize and deploy

Create a directory and initialize it from this sample:

```bash
mkdir langgraph-toolbox-user-identity
cd langgraph-toolbox-user-identity
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/03-langgraph-toolbox-user-identity/azure.yaml
```

Provision the Foundry layer, followed by the dependent
[connections Bicep layer](infra/connections/main.bicep):

```bash
azd provision
```

Deploy the hosted agent:

```bash
azd deploy
```

Invoke it:

```bash
azd ai agent invoke "Summarize my upcoming calendar events."
```

## Run locally

From `src/toolbox-langgraph-user-identity`, create a local environment:

```bash
cp .env.example .env
python -m pip install uv
uv sync --frozen
```

Set `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and
`TOOLBOX_NAME` in `.env`. The project must already contain the connections and
toolbox declared by the sample; running `azd provision` creates them.

Start the server:

```bash
uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses
```

In another terminal, invoke the local Responses endpoint:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Summarize my upcoming calendar events."}'
```

You can also use `azd`:

```bash
azd ai agent run
azd ai agent invoke --local "Summarize my upcoming calendar events."
```

## User consent

The WorkIQ connections use the calling user's Microsoft Entra identity. The
GitHub connection uses Foundry-managed OAuth2. A user may need to grant consent
before a tool can access their data.

When the Foundry MCP gateway returns consent error `-32006`, the agent responds
with a URL on `consent.azure-apim.net` or a regional
`*.consent.azure-apihub.net` host. Open that URL, complete the consent flow, and
retry the request.

## Configuration

| Variable | Description |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint; injected in hosted containers. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Chat model deployment name. |
| `TOOLBOX_NAME` | Foundry Toolbox name; defaults to `langgraph-toolbox-user-identity-tools` through `azure.yaml`. |
| `PORT` | Local listening port; defaults to `8088`. |

## Troubleshooting

### The agent reports that consent is required

Open the returned consent URL, authorize the connection, and retry the same
request in a fresh session:

```bash
azd ai agent invoke --new-session --new-conversation \
  "Summarize my upcoming calendar events."
```

### The agent loads no tools

Verify that `TOOLBOX_NAME` matches a toolbox in the project identified by
`FOUNDRY_PROJECT_ENDPOINT`, and confirm that the toolbox version containing the
three MCP tools is the default version.

### A tool schema is rejected

The sample repairs the common case where an object schema omits `properties`.
For other schema errors, inspect the schema returned by the upstream MCP server.
