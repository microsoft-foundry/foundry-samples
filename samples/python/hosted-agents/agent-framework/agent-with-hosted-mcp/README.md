**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to use a Hosted Model Context Protocol (MCP) server with a
[Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview#ai-agents) AI agent and
host it using [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme) and
deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.

## How It Works

### MCP Integration

This sample uses a Hosted Model Context Protocol (MCP) server to provide external tools to the agent. The MCP workflow operates as follows:

1. The agent is configured with a `HostedMCPTool` pointing to `https://learn.microsoft.com/api/mcp`
2. When you ask questions, the Azure OpenAI Responses service automatically invokes the MCP tool to search Microsoft Learn documentation
3. The agent returns answers based on the retrieved Microsoft Learn content

**Note**: In this configuration, the Azure OpenAI Responses service manages tool invocation directly - the Agent Framework does not handle MCP tool calls.

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.
The extension builds a container image for the agent, deploys it to Azure Container Instances (ACI), and creates a hosted agent version and deployment on Foundry Agent Service.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI endpoint configured
2. A deployment of a chat model (e.g., `gpt-4o-mini`)
3. Azure CLI installed and authenticated (`az login`)
4. Python 3.10+ installed

### Environment Variables

Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL (required)
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` - The deployment name for your chat model (required)

```powershell
# Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"

# Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4o-mini"
```

### Installing Dependencies

Install the required Python dependencies using pip:

```powershell
pip install -r requirements.txt
```

> It is always a good practice to use a virtual environment for Python projects.

### Running the Sample

To run the agent, execute the following command in your terminal:

```powershell
python main.py
```

This will start the hosted agent locally on `http://localhost:8088/`.

### Interacting with the Agent

You can interact with the agent using:

```powershell
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses -d '{"input": "How to create an Azure storage account using az cli?","stream":false}'
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
