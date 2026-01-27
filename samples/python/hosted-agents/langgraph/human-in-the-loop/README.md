**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [LangGraph](https://docs.langchain.com/oss/python/langgraph/workflows-agents).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to build a LangGraph agent with **human-in-the-loop capabilities** that can interrupt execution to ask for human input when needed, host it using the
[Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-langgraph/),
and deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.

## How It Works

### Human-in-the-Loop Integration

In [main.py](main.py), the agent is created using LangGraph's `StateGraph` and includes a custom `AskHuman` tool that uses the `interrupt()` function to pause execution and wait for human feedback. The key components are:

- **LangGraph Agent**: An AI agent that can intelligently decide when to ask humans for input during task execution
- **Human Interrupt Mechanism**: Uses LangGraph's `interrupt()` function to pause execution and wait for human feedback
- **Conditional Routing**: The agent determines whether to execute tools, ask for human input, or complete the task

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-langgraph/),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.
The extension builds a container image into Azure Container Registry (ACR), and creates a hosted agent version and deployment on Microsoft Foundry.

## Validate the deployed Agent
```python
# Before running the sample:
#    pip install --pre azure-ai-projects>=2.0.0b1
#    pip install azure-identity

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
import json

foundry_account = "<Your Foundry Account Name>"
foundry_project = "<Your Foundry Project Name>"
agent_name = "<Your Deployed Agent Name>"

project_endpoint = f"https://{foundry_account}.services.ai.azure.com/api/projects/{foundry_project}"

project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
)

# Get an existing agent
agent = project_client.agents.get(agent_name=agent_name)
print(f"Retrieved agent: {agent.name}")

openai_client = project_client.get_openai_client()
conversation = openai_client.conversations.create()

response = openai_client.responses.create(
    input=[{"role": "user", "content": "Ask the user where they are, then look up the weather there."}],
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)

call_id = ""
for item in response.output:
    if item.type == "function_call" and item.name == "__hosted_agent_adapter_hitl__":
        print(f"Agent ask: {item.arguments}")
        call_id = item.call_id

if not call_id:
    print(f"No human input is required, output: {response.output_text}")
else:
    human_response = {"resume": "San Francisco"}
    response = openai_client.responses.create(
        input=[
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(human_response)
            }],
        conversation=conversation.id,
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    print(f"Human response: {human_response['resume']}")
    print(f"Agent response: {response.output_text}")
```

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure OpenAI Service**
   - Endpoint configured
   - Chat model deployed (e.g., `gpt-4o-mini` or `gpt-4`)
   - Note your endpoint URL and deployment name

2. **Azure CLI**
   - Installed and authenticated
   - Run `az login` and verify with `az account show`

3. **Python 3.10 or higher**
   - Verify your version: `python --version`
   - If you have Python 3.9 or older, install a newer version:
     - Windows: `winget install Python.Python.3.12`
     - macOS: `brew install python@3.12`
     - Linux: Use your package manager

### Environment Variables

Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL (required)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` - The deployment name for your chat model (required)

This sample loads environment variables from a local `.env` file if present.

```powershell
# Replace with your actual values
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
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

### Interacting with the Agent locally

#### Initial Request (Triggering Human Input)

Send a request that will cause the agent to ask for human input:

**PowerShell (Windows):**
```powershell
$body = @{
    input = "Ask the user where they are, then look up the weather there."
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**
```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{"input": "Ask the user where they are, then look up the weather there.", "stream": false}'
```

**Response Structure:**

The agent will respond with an interrupt request:

```json
{
  "conversation": {
    "id": "conv_abc123..."
  },
  "output": [
    {
      "type": "function_call",
      "name": "__hosted_agent_adapter_interrupt__",
      "call_id": "call_xyz789...",
      "arguments": "{\"question\": \"Where are you located?\"}"
    }
  ]
}
```

#### Providing Human Feedback

Resume the conversation by providing the human's response:

**PowerShell (Windows):**
```powershell
$body = @{
    input = @(
        @{
            type = "function_call_output"
            call_id = "call_xyz789..."
            output = '{"resume": "San Francisco"}'
        }
    )
    stream = $false
    conversation = @{
        id = "conv_abc123..."
    }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**
```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{
     "input": [
       {
         "type": "function_call_output",
         "call_id": "call_xyz789...",
         "output": "{\"resume\": \"San Francisco\"}"
       }
     ],
     "stream": false,
     "conversation": {
       "id": "conv_abc123..."
     }
   }'
```

**Final Response:**

The agent will continue execution and provide the final result:

```json
{
  "conversation": {
    "id": "conv_abc123..."
  },
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": "I looked up the weather in San Francisco. Result: It's sunny in San Francisco."
    }
  ]
}
```

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
