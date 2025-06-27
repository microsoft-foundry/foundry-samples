# Intent Routing Agent

This **Intent Routing Agent** code sample helps create agents that detect user intent and provide exact answering, using Azure AI Agent Service, Conversational Language Understanding (CLU) and Custom Question Answering (CQA) in Azure AI Language. It detects user intent and provides exact answers, perfect for deterministic intent routing and precise question answering with human controls. With it, businesses can 
use human-controlled intent detection and question answering, while leveraging LLM RAG solutions to handle long-tail queries. Helpful for deterministically intent routing and excat question answering with human controls.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

## Use Cases
1. **Customer Support**: Identify user intent (e.g., "cancel my order" vs. "where is my package") to enable routing to deterministic workflows accordingly. For frequently asked or high value questions (e.g., return policy, warranty info), provide precise answers from a verified knowledge base.  
2. **E-commerce**: Detect customer shopping intents such as comparing products or tracking orders. Offer fact-based answers like “Which jackets are waterproof under $200?” or “When will my order arrive?”, while handing off complex support needs to a human.


## Architecture Overview
The system consists of:
- An AI Agent created with Azure AI Agent Service using `gpt-4o` as the base model.
- Conversational Language Understanding for intent detection.
- Custom Question Answering for precise responses.
- A Bicep template to automate provisioning of Azure resources.

```text
+----------------+                         
|   User Query   |                         
| (Any Intent)   |                         
+-------+--------+                         
        |                                  
        V                         invokes                         
+-----------------+ --------------------------------------------------->   +------+
|                 |<----------------------------------------------------   |  CLU |
| Intent Routing  |      detected intent (predefined, or undefined)        +------+
|                 |        
|       Agent     |        invoke if quesiton intent is detected            +------+
|                 |----------------------------------------------------->   |  CQA |
+-----------------+<-----------------------------------------------------   +------+
        |                        exact answers                
        v                                  
+-------------------------------------------------+           
| Agent Response with detected intent             |           
| or exact answer if question intent is detected  |           
+-------------------------------------------------+           

```
## Setup Instructions

### Prerequisites
- Python 3.8+
- Azure CLI
- Azure subscription
- Agent setup: deploy the latest agent setup using ([this custom deployment](https://aka.ms/basic-agent-deployment)).
  - The above creates:
    1. AI Services resource (type: Microsoft.CognitiveServices/accounts),
    2. AI Project (type: Microsoft.CognitiveServices/accounts/projects),
    3. Model deployment (type: Microsoft.CognitiveServices/accounts/deployments). Recommended model version: gpt-4o (at least 2024-11-20).
- Custom Question Answering (CQA) deployment, see [CQA Overview](https://learn.microsoft.com/azure/ai-services/language-service/question-answering/overview)
- Conversational Language Understanding (CLU) deployment, see [CLU Overview](https://learn.microsoft.com/azure/ai-services/language-service/conversational-language-understanding/overview)
- A custom connection of the resource used by your CLU and CQA projects are added to the project of your Agent. 
  - CLU and CQA projects can be created using an Azure AI Foundry resource, AI hub resource, or Azure AI Language resource. 
  - In your agent project management center, use "Custom keys" connection when adding the custom connection in the connected resources page. 
  - To add a "Custom keys" connection, add a key value pair with Ocp-Apim-Subscription-Key as the key name, and the resource key as the value. For Azure AI Foundry resource and AI hub resource, you can find the resource key value in the resource overview page in the Azure AI Foundry portal management center. You can also find the key of any type of resources in the Azure portal. 
  - For more info to create a connection, see [Create a connection](https://learn.microsoft.com/azure/ai-foundry/how-to/connections-add)

### Steps
1. **Clone the Repository**

2. **Set Config Variables**

4. **Run the Agent Script**
```bash
 python template.py
```

## ⚙️ Configuration Guide
| Parameter Name                         | Description                                                                       |
|----------------------------------------|-----------------------------------------------------------------------------------|
| `project_endpoint`                     | Endpoint for the project this agent is using                                      |
| `model_name`                           | Name of the model deployment to be used for the Agent                             |
| `language_resource_url`                | Endpoint for the language resource where your CLU and CQA projects are created    |                                       |
| `language_resource_connection_name`    | Name of the language resource connection added in the agent project               |
| `connection_id`                        | Connection ID for the language resource connection added in the agent project     |
| `cqa_project_name`                     | Name of the CQA project this agent will use                                       |
| `cqa_deployment_name`                  | Name of the deployment in the CQA project this agent will use                     |
| `clu_project_name`                     | Name of the CLU project this agent will use                                       |
| `clu_deployment_name`                  | Name of the model deployment in the CLU project this agent will use               |


## Sample Data Instructions
This repo contains a `sample_data/` directory with:
- clu_import.json: A CLU project file with sample intent-utterance pairs that you can use to create a CLU project. 
- cqa_import.json: A CQA project file with sample question-answer pairs that you can use to create a CQA project.

The sample data are made up based on a fictional outdoor retail company, Contoso Outdoor.

You can also use the sample data and test the interaction by invoking the agent with prompts as listed in next section.

## Example Agent Interaction

### User: 
Where is my order?

### Agent:
Detected Intent: CheckOrderStatus

### User: 
i need change my shipping destination

### Agent: 
Detected Intent: UpdateShippingInfo


### User: 
I need ro return my order

### Agent: 
Detected Intent: ProcessReturnsAndExchanges

### User: 
what is your return policy

### Agent: 
We offer a 30-day return policy on most items. If you are not satisfied with your purchase, you can return it for a full refund or exchange it for another product, as long as:

The item is unused, unworn, and in its original packaging.
You provide proof of purchase (order confirmation or receipt).
The return request is made within 30 days of receiving the item.

Certain items, such as personalized, clearance, or final sale products, may not be eligible for return. To start a return or exchange, visit our Returns & Exchanges page and follow the step-by-step instructions. We may provide a prepaid return label, but shipping fees for returns may apply.

## Customization Tips
- Modify the system instructions in `template.py` to your needs (e.g., style of responding).
- Fine-tuning the associated CLU deployment, e.g. adding/modify/delete intents or entities etc
- Fine-tuning the associated CQA deployment, e.g. adding/modify/delete question-answer paires, or finetune questions, etc
- Extend the agent with other useful tools or APIs (using OpenAPI spec).
