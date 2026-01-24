**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [LangGraph](https://docs.langchain.com/oss/python/langgraph/workflows-agents).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to build a LangGraph react agent that can use **Foundry tools**
(for example, code interpreter and MCP tools), host it using the
[Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-langgraph/),
and deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.

## How It Works

### Foundry tools integration

In [main.py](main.py), the agent is created using `langchain.agents.create_agent` and is configured with
`use_foundry_tools`. The middleware enables tool usage via Foundry-supported tool types:

- `code_interpreter` (foundry configured tools)
- `mcp` (connected mcp tool, configured with a Foundry project connection id)

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-langgraph/),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.
The extension builds a container image into Azure Container Registry (ACR), and creates a hosted agent version and deployment on Microsoft Foundry.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure OpenAI Service**
   - Endpoint configured
   - Chat model deployed (e.g., `gpt-4o-mini` or `gpt-4`)
   - Note your endpoint URL and deployment name

2. **Azure AI Foundry Project**
   - Project created in [Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-foundry?view=foundry#microsoft-foundry-portals)
   - Add 'Microsoft Learn' MCP from foundry tool catalog.
   ![microsoft_learn](microsoft_learn.png)

3. **Azure CLI**
   - Installed and authenticated
   - Run `az login` and verify with `az account show`

4. **Python 3.10 or higher**
   - Verify your version: `python --version`
   - If you have Python 3.9 or older, install a newer version:
     - Windows: `winget install Python.Python.3.12`
     - macOS: `brew install python@3.12`
     - Linux: Use your package manager

### Environment Variables

Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL (required)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` - The deployment name for your chat model (required)
- `AZURE_AI_PROJECT_ENDPOINT` - Your Azure AI Foundry project endpoint (required)
- `AZURE_AI_PROJECT_TOOL_CONNECTION_ID` - Foundry project connection id used to configure the `mcp` tool (required)

This sample loads environment variables from a local `.env` file if present.

**Finding your tool connection id** (portal names may vary):
1. Go to [Azure AI Foundry portal](https://ai.azure.com)
2. Navigate to your project -> Build -> Tools
3. Find your connected MCP tool (e.g., "Microsoft Learn")
4. Copy your tool's name and set it as `AZURE_AI_PROJECT_TOOL_CONNECTION_ID`

```powershell
# Replace with your actual values
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
$env:AZURE_AI_PROJECT_ENDPOINT="https://{resource}.services.ai.azure.com/api/projects/{project-name}"
$env:AZURE_AI_PROJECT_TOOL_CONNECTION_ID="<your-tool-connection-id>"
```

### Installing Dependencies

Install the required Python dependencies using pip:

```powershell
pip install -r requirements.txt
```

### Running the Sample

To run the agent, execute the following command in your terminal:

```powershell
python main.py
```

This will start the hosted agent locally on `http://localhost:8088/`.

### Interacting with the Agent

**PowerShell (Windows):**
```powershell
$body = @{
   input = "use the python tool to calculate what is 4 * 3.82. and then find its square root and then find the square root of that result"
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**
```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{"input": "use the python tool to calculate what is 4 * 3.82. and then find its square root and then find the square root of that result","stream":false}'
```

The agent may use Foundry tools (for example `web_search_preview` and/or `mcp`) as needed to answer.

### Deploying the Agent to Microsoft Foundry

To deploy your agent to Microsoft Foundry, follow the comprehensive deployment guide at https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli

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