**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to build a web search agent using Bing Grounding, hosted using
[Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/) and
deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.

## How It Works

### Web Search Agent

The agent uses Bing Grounding to search the web for current information and provide accurate, well-sourced answers. This demonstrates:

- How to integrate Bing Grounding as a tool in an AI agent
- How to use the `HostedWebSearchTool` from the Agent Framework

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.
The extension builds a container image into Azure Container Registry (ACR), and creates a hosted agent version and deployment on Microsoft Foundry.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. An Azure AI Foundry project configured
2. A deployment of a chat model (e.g., `gpt-4.1-mini`)
3. A Bing Grounding connection in your project
4. Azure CLI installed and authenticated (`az login`)
5. Python 3.10+ installed

### Environment Variables

Create a `.env` file with the following environment variables:

> **Note:** The `.env` file is for local development only. When deploying to Azure AI Foundry, remove the `.env` file and configure environment variables in `agent.yaml` instead.

```bash
AZURE_AI_PROJECT_ENDPOINT=https://<your-foundry-account>.services.ai.azure.com/api/projects/<your-project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=<your-model-deployment>  # e.g., gpt-4.1-mini
BING_GROUNDING_CONNECTION_ID=/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project>/connections/<bing-connection-name>
```

### Installing Dependencies

Install the required Python dependencies using pip:

```bash
pip install -r requirements.txt
```

### Running the Sample

To run the agent, execute the following command in your terminal:

```bash
python main.py
```

This will start the hosted agent locally on `http://localhost:8088/`.

### Interacting with the Agent

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is the latest news in AI?"}' | jq .
```

### Deploying the Agent to Microsoft Foundry

To deploy your agent to Microsoft Foundry, follow the comprehensive deployment guide at https://aka.ms/azdaiagent/docs

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

We **recommend using `azd` cloud build**, which always builds images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds**

Use this command to build the image locally:

```shell
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
