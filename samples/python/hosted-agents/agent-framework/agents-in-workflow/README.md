**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to use AI agents as executors within a workflow, hosted using
[Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme) and
deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.

## How It Works

### Agents in Workflows

This sample demonstrates the integration of AI agents within a workflow pipeline. The workflow operates as follows:

1. **Research Agent** - Research market and product
2. **Market Agent** - Create market strategy
3. **Legal Agent** - Review legal considerations for the market strategy

The agents will work concurrently in a workflow, creating a comprehensive report that demonstrates:

- How AI-powered agents can be seamlessly integrated into workflow pipelines
- concurrent execution of multiple agents within a workflow

### Agent Hosting

The agent workflow is hosted using the [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent workflow using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent workflow can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.
The extension builds a container image for the agent, deploys it to Azure Container Instances (ACI), and creates a hosted agent version and deployment on Foundry Agent Service.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure OpenAI Service**
   - Endpoint configured
   - Chat model deployed (e.g., `gpt-4o-mini` or `gpt-4`)
   - Note your endpoint URL and deployment name

2. **Azure AI Foundry Project**
   - Project created in [Azure AI Foundry](https://ai.azure.com)
   - Note your project endpoint URL

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
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` - The deployment name for your chat model (required)
- `AZURE_AI_PROJECT_ENDPOINT` - Your Azure AI Foundry project endpoint (required)

**Finding your Azure AI Project Endpoint:**
1. Go to [Azure AI Foundry portal](https://ai.azure.com)
2. Navigate to your project
3. Find the endpoint under **Project Settings** > **Properties**
4. Format: `https://{project-name}.{region}.api.azureml.ms` or `https://{resource}.services.ai.azure.com/api/projects/{project-name}`

```powershell
# Replace with your actual values
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"
$env:AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4o-mini"
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-project.region.api.azureml.ms"
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

This will start the hosted agent workflow locally on `http://localhost:8088/`.

**Expected Output:**
```
2026-01-22 11:27:02,086 - azure.ai.agentserver - INFO - Starting FoundryCBAgent server on port 8088
INFO:     Uvicorn running on http://0.0.0.0:8088 (Press CTRL+C to quit)
```

### Interacting with the Agent

**PowerShell (Windows):**
```powershell
$body = @{
    input = "We are launching a new budget-friendly electric bike for urban commuters."
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**
```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
  -d '{"input": "We are launching a new budget-friendly electric bike for urban commuters.","stream":false}'
```

**Expected Response:**

You'll receive a comprehensive response from all three agents running concurrently:
- **Research Agent**: Market insights, opportunities, and risks
- **Marketing Agent**: Value propositions and targeted messaging
- **Legal Agent**: Compliance and policy considerations

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
