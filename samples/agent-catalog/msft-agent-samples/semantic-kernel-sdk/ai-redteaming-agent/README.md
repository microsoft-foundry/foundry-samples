# AI Red Teaming Agent

This code sample enables creating an AI Red Teaming Agent using Azure AI Evaluation and Semantic Kernel. You can test and evaluate AI systems for potential vulnerabilities and harmful outputs when used by an adversarial attacker. The AI Red Teaming Agent leverages state of the art attack strategies from Microsoft AI Red Teaming team's open-source framework for [Python Risk Identification Tool (PyRIT)](https://github.com/Azure/PyRIT).

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

## Overview

The `template.py` script implements an AI Red Teaming Agent that can:

1. Fetch harmful prompts across different [risk categories](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/ai-red-teaming-agent#supported-risk-categories)
2. Send prompts to target generative AI models or applications
3. Apply transformations to prompts (like base64 encoding) with different [attack strategies](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/ai-red-teaming-agent#supported-attack-strategies)
4. Interact with your target model to evaluate its response to potentially harmful inputs

## Prerequisites

- Python 3.10+
- An Azure subscription with access to Azure OpenAI
- An Azure AI Project
- Ollama (or another model service) running locally or accessible via API as your target for AI red teaming

## Setup Instructions

### 1. Install Required Dependencies

```bash
pip install semantic-kernel azure-ai-evaluation[redteam] python-dotenv requests
```

### 2. Environment Variables

Create a `.env` file in the same directory as `template.py` with the following variables:

```
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
AZURE_OPENAI_API_KEY=your-api-key

# Azure AI Project Endpoint, get it on Azure AI Froundry UI project home page
AZURE_AI_PROJECT_ENDPOINT=https://your-resource-name.services.ai.azure.com/api/projects/your-project-name
```

### 3. Configure Target Model

By default, the template uses Ollama as the target model. To use Ollama:

1. Make sure Ollama is installed and running on your machine
2. Update the model name in the `call_ollama` function:

```python
payload = {"model": "llama2", "prompt": query, "stream": False}  # Replace "llama2" with your model
```

### 4. Changing the Target Model

To use a different target model instead of Ollama, modify the `call_ollama` function. For example, to use another API:

```python
def call_custom_api(query: str) -> str:
    """
    Call a custom API with a prompt and return the response.
    """
    url = "https://your-api-endpoint.com/generate"
    headers = {
        "Authorization": f"Bearer {os.environ.get('API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {"prompt": query, "max_tokens": 300}

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    try:
        return response.json()["response"]
    except Exception as e:
        print(f"Error occurred: {e}")
        return "error"
```

Then, update the `main` function to use your new target function:

```python
# Initialize the RedTeamPlugin with the target function
red_team_plugin = RedTeamPlugin(
    azure_ai_project_endpoint=ai_project_endpoint,
    target_func=call_custom_api  # Use your new function here
)
```

## Running the Agent

Execute the script:

```bash
python template.py
```

The script will:
1. Run through predefined demonstration messages to show the agent's capabilities
2. Enter interactive mode where you can interact with the agent directly

## Usage Examples

Here are some example commands you can use in interactive mode:

- `Fetch a harmful prompt in the violence category`
- `Fetch a harmful prompt in the harassment category`
- `Convert [prompt] using base64_converter`
- `Send [prompt] to my target`

## Customizing Agent Behavior

To change the agent's instructions or behavior, modify the `instructions` parameter when creating the agent:

```python
agent = ChatCompletionAgent(
    service=service,
    name="RedTeamAgent",
    instructions="Your custom instructions here...",
    plugins=[red_team_plugin],
)
```

## Security and Responsible Use

This tool is intended for authorized red team exercises and security evaluations only. Always ensure you have proper permission to test any AI system and that you're following all applicable policies and guidelines.
