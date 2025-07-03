# Exact Question Answering Agent

The **Exact Question Answering Agent** code sample supports building agents that answer predefined, high-value questions to ensure consistent and accurate responses. 

Using Azure AI Agent Service and Custom Question Answering in Azure AI Language, it can provide deterministic, exact answers with human control options. Businesses can automate responses to their most common questions, using this exact answering approach. For less frequent or more nuanced questions, a fallback to an LLM-powered RAG system can handle the long tail, while truly complex queries are routed to human agents.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

## Use Cases
1. **Customer Support**: Automate deterministic human-controlled responses to frequently asked or high value questions such as “What is your return policy?”, “How do I reset my password?”, or “What’s the warranty coverage?” while routing complex queries to human agents.
2. **IT Support**: Provide precise answers like “What is the VPN setup process?”, “Where do I download the latest security patch?”, or “How do I enroll in 2FA?” faithful to technical documentation and internal IT knowledge bases.
3. **Education and Student Help**: Respond with precise and human-controlled answers to questions like “What’s the deadline to drop a course?”, “Where do I submit my financial aid application?”, or “What’s the grading policy for AP credits?” faithful to school and academic documentation.

## Architecture Overview
The system consists of:
- An AI Agent created with Azure AI Agent Service using `gpt-4o` as the base model.
- Custom Question Answering for precise responses.
- A Bicep template to automate provisioning of Azure resources.

```text
+----------------+                         
|   User Query   |                         
| (Any Intent)   |                         
+-------+--------+                         
        |                                  
        v                                  
+-----------------+                invokes                        
|                 |-------------------------------------->   +------+
| Exact Question  |<--------------------------------------   | CQA  |
| Answering Agent |             exact answering              +------+
+-----------------+   
        |               
        v                                  
+-------------------------------------+           
| Agent Response with exact answer    |           
|                                     |           
+-------------------------------------+           

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
    3. Model deployment (type: Microsoft.CognitiveServices/accounts/deployments). 
- Custom Question Answering (CQA) deployment, see [CQA Overview](https://learn.microsoft.com/azure/ai-services/language-service/question-answering/overview)
- A custom connection of the resource used by your CQA project are added to the project of your Agent. 
  - CQA projects can be created using an Azure AI Foundry resource, AI hub resource, or Azure AI Language resource. 
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
| Parameter Name                         | Description                                                       |
|----------------------------------------|-------------------------------------------------------------------|
| `project_endpoint`                     | Endpoint for the project this agent is using                                      |
| `model_name`                           | Name of the model deployment to be used for the Agent                             |
| `language_resource_url`                | Endpoint for the language resource where your CLU and CQA projects are created    |                                       |
| `language_resource_connection_name`    | Name of the language resource connection added in the agent project               |
| `connection_id`                        | Connection ID for the language resource connection added in the agent project     |
| `cqa_project_name`                     | Name of the CQA project this agent will use                                       |
| `cqa_deployment_name`                  | Name of the deployment in the CQA project this agent will use                     |


## Sample Data Instructions
This repo contains a `sample_data/` directory with:
- cqa_import.json: A CQA project file with sample question-answer pairs that you can use to create a CQA project.

The sample data are made up based on a fictional outdoor retail company, Contoso Outdoor.

You can also use the sample data below and test the interaction by invoking the agent with prompts as listed in next section.

## Example Agent Interaction
### User: 
what is your return policy

### Agent: 
We offer a 30-day return policy on most items. If you are not satisfied with your purchase, you can return it for a full refund or exchange it for another product, as long as:

The item is unused, unworn, and in its original packaging.
You provide proof of purchase (order confirmation or receipt).
The return request is made within 30 days of receiving the item.

Certain items, such as personalized, clearance, or final sale products, may not be eligible for return. To start a return or exchange, visit our Returns & Exchanges page and follow the step-by-step instructions. We may provide a prepaid return label, but shipping fees for returns may apply.

### User: 
What tents are recommended for winter?

### Agent: 
For winter camping, neither the Alpine Explorer Tent nor the TrailMaster X4 Tent is specifically recommended for extreme winter conditions. Here are the details:

Alpine Explorer Tent:
Designed primarily for 3-season use. It can withstand light snowfall but may not support heavy snow or extreme winter conditions.
TrailMaster X4 Tent:
Also designed for 3-season use, not suitable for extreme winter conditions with heavy snow and freezing temperatures.
In summary, both tents are considered 3-season tents and may not provide adequate support for severe winter weather.

### User: 
What mountain boots are good for a casual climber?

### Agent: 
For casual climbers, I recommend the following boots:

TrekReady Hiking Boots
Comfort: Incredibly comfortable and durable.
Traction: Excellent traction and waterproof design, ideal for various hiking adventures.
Support: Features a high-top design and padded collar for great ankle support.
Break-in Period: May require some time to break in for maximum comfort.
Versatile Use: Designed primarily for hiking but can also be worn for everyday activities.
TrailWalker Hiking Shoes
Lightweight: Good for long hikes due to their lightweight design.
Waterproof: Keeps feet dry during unexpected rain.
Support: Provides excellent ankle support and comfort, although some users report slight discomfort around the toe area after extended use.
Good Traction: Features outstanding grip, suitable for challenging trails.
Both options offer excellent features for casual climbing and hiking.

## Customization Tips
- Modify the system instructions in `template.py` to your needs or preferences (e.g., style of answering).
- Extend the agent with other useful tools or APIs (using OpenAPI spec).
- Fine-tuning the associated CQA deployment, e.g. adding/modify/delete question-answer pairs, or finetune questions, etc.
