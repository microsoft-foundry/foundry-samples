**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to build a Microsoft Agent Framework chat agent with **human-in-the-loop** approval workflows, host it using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/), and deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.

This sample is adapted from the [agent-framework sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/tools/ai_function_with_approval_and_threads.py).

## How It Works

### Human-in-the-loop approval

In [main.py](main.py), the agent is created using `AzureOpenAIChatClient` and includes an `@ai_function` decorated with `approval_mode="always_require"`. This means any call to the function (e.g., `add_to_calendar`) will escalate to a human reviewer before execution.

When the agent determines it needs to call an approval-required function, the response includes a `function_call` with name `__hosted_agent_adapter_hitl__`. The caller must then provide feedback (`approve`, `reject`, or additional guidance) to continue the workflow.

### Thread persistence

- The sample uses `JsonLocalFileAgentThreadRepository` for `AgentThread` persistence, creating a JSON file per conversation ID under `./thread_storage`. 

- An in-memory alternative, `InMemoryAgentThreadRepository`, lives in the `azure.ai.agentserver.agentframework.persistence` module.

- To store thread messages elsewhere, inherit from `SerializedAgentThreadRepository` and override the following methods:
```python
class SerializedAgentThreadRepository(AgentThreadRepository):
    async def read_from_storage(self, conversation_id: str) -> Optional[Any]:
        """Read the serialized thread from storage.

        :param conversation_id: The conversation ID.
        :type conversation_id: str

        :return: The serialized thread if available, None otherwise.
        :rtype: Optional[Any]
        """
        ...

    async def write_to_storage(self, conversation_id: str, serialized_thread: Any) -> None:
        """Write the serialized thread to storage.

        :param conversation_id: The conversation ID.
        :type conversation_id: str
        :param serialized_thread: The serialized thread to save.
        :type serialized_thread: Any
        :return: None
        :rtype: None
        """
        ...
```

These hooks let you plug in any backing store (blob storage, databases, etc.) without changing the rest of the sample.

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/), which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension. The extension builds a container image into Azure Container Registry (ACR), and creates a hosted agent version and deployment on Microsoft Foundry.

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
    input="Add a dentist appointment on March 15th",
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)

call_id = ""
for item in response.output:
    if item.type == "function_call" and item.name == "__hosted_agent_adapter_hitl__":
        args = json.loads(item.arguments)
        print(f"Agent will add {args['event_name']} on {args['date']}")
        call_id = item.call_id

if not call_id:
    print(f"No human input is required, output: {response.output_text}")
else:
    human_response = "approve"
    response = openai_client.responses.create(
        input=[
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": human_response
            }],
        conversation=conversation.id,
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    print(f"Human response: {human_response}")
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
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` - The deployment name for your chat model (required)
- `OPENAI_API_VERSION` - The API version (e.g., `2025-03-01-preview`)

This sample loads environment variables from a local `.env` file if present. Copy `.envtemplate` to `.env` and fill in your Azure OpenAI details:

```
AZURE_OPENAI_ENDPOINT=https://<endpoint-name>.cognitiveservices.azure.com/
OPENAI_API_VERSION=2025-03-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=<deployment-name>
```

```powershell
# Replace with your actual values
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"
$env:AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4o-mini"
$env:OPENAI_API_VERSION="2025-03-01-preview"
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

**Step 1: Send a user request**

**PowerShell (Windows):**
```powershell
$body = @{
    agent = @{ name = "local_agent"; type = "agent_reference" }
    stream = $false
    input = "Add a dentist appointment on March 15th"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**
```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{"agent":{"name":"local_agent","type":"agent_reference"},"stream":false,"input":"Add a dentist appointment on March 15th"}'
```

A response that requires a human decision looks like this (formatted for clarity):

```json
{
  "conversation": {"id": "<conversation_id>"},
  "output": [
    {...},
    {
      "type": "function_call",
      "id": "func_xxx",
      "name": "__hosted_agent_adapter_hitl__",
      "call_id": "<call_id>",
      "arguments": "{\"event_name\":\"Dentist Appointment\",\"date\":\"2024-03-15\"}"
    }
  ]
}
```

Capture these values from the response; you will need them to provide feedback:

- `conversation.id`
- The `call_id` associated with `__hosted_agent_adapter_hitl__`

**Step 2: Provide human feedback**

Send a `CreateResponse` request with a `function_call_output` message that contains your decision (`approve`, `reject`, or additional guidance). Replace the placeholders before running the command:

**PowerShell (Windows):**
```powershell
$body = @{
    agent = @{ name = "local_agent"; type = "agent_reference" }
    stream = $false
    conversation = @{ id = "<conversation_id>" }
    input = @(
        @{
            call_id = "<call_id>"
            output = "approve"
            type = "function_call_output"
        }
    )
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**
```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{"agent":{"name":"local_agent","type":"agent_reference"},"stream":false,"conversation":{"id":"<conversation_id>"},"input":[{"call_id":"<call_id>","output":"approve","type":"function_call_output"}]}'
```

When the reviewer response is accepted, the agent executes the approved function and returns the final output.

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
