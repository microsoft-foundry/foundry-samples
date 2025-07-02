# Meeting Prep Agent

## Summary
This code sample helps build an agent that helps with meetings by researching attendees and generating contextual summaries. Built using Azure AI Agent Service, it helps users retrieve meeting and call details, attendee lists, and differentiate between internal and external participants by integrating with Azure Logic Apps. The agent also leverages the **Bing Grounding Tool** to provide relevant, publicly available insights about meeting participants.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

## Use Cases
1. **Meeting Preparation**: Retrieve upcoming meetings, calls, and attendee lists for a user.
2. **External Participant Identification**: Identify and list external participants in meetings.
3. **Public Insights**: Fetch public information about meeting participants using Bing.
4. Summarize meeting information and help plan ahead.

## Architecture Overview
The system consists of:
- An AI Agent created with Azure AI Agent Service using `gpt-4o` as the base model.
- A Bing Grounding Tool integrated via Azure Bing Account and connected to the agent.
- A Logic App action tool for meeting/event retrieval, integrated via a Python function and Azure Logic App callback.
- Bicep templates to automate provisioning of Azure resources.

```text
                  +-------------------+
                  |     User Query    |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  | Meetings &        |
                  | Insights Agent    |
                  |   (AI Agent)      |
                  +---------+---------+
                            |
                     +------+------+
                     |             |
                     v             v
+------------------------+      +----------------------------+
| Logic App Tool         |      | Bing Grounding Tool        |
| (Fetch meetings, calls |      | (Public info & insights)   |
|  and attendees)        |      |                            |
+------------------------+      +----------------------------+
                            |
                            v
            +------------------------------+
            | Agent Response:              |
            | - Meeting/call details       |
            | - Attendee info              |
            | - Public insights (from Bing)|
            +------------------------------+
```

## Setup Instructions

### Prerequisites

1. Azure subscription with the following permissions
   - Contributor or Cognitive Services Contributor role (for resource deployment)
   - Azure AI Developer and Cognitive Services user role (for agent creation)
2. Agent setup: deploy the latest agent setup using this ([custom deployment](https://www.aka.ms/basic-agent-deployment)).
   - The above creates:
      - AI Services resource
      - AI Project
      - Model deployment
3. Python 3.8+
4. Azure CLI
   
- Bing Grounding resource
- Logic App for meeting/event retrieval

### Steps

1. **Clone the Repository**

2. **Set Environment Variables**
```bash
PROJECT_ENDPOINT="<your-project-endpoint>" # (https://<your-ai-services-account-name>.services.ai.azure.com/api/projects/<your-project-name>)
MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
BING_CONNECTION_ID="<your-bing-connection-id>"
SUBSCRIPTION_ID="<your-azure-subscription-id>"
RESOURCE_GROUP_NAME="<your-resource-group>"
LOGIC_APP_NAME="<your-logic-app-name>"
TRIGGER_NAME="<your-logic-app-trigger-name>" # e.g. When_a_HTTP_request_is_received
```

3. **Deploy Resources Using Bicep**
```bash
az deployment group create \
  --resource-group <your-rg> \
  --template-file bing-logicApp-connection.bicep \
  --parameters \
      bingAccountName="bing-grounding-agent" \
      bingSku="S1" \
      connectionName="bing-grounding-conn" \
      accountResource="<AI-Project-Name>" \
      logicAppName="<your-logic-app-name>"
```

4. **Run the Agent Script**
```bash
python template.py
```

## ⚙️ Configuration Guide

| Parameter Name         | Description                                                        |
|------------------------|--------------------------------------------------------------------|
| `bingAccountName`      | Unique name for the Bing grounding resource                        |
| `bingSku`              | Pricing tier (e.g., `S1`)                                          |
| `connectionName`       | Name for the AML connection to Bing                                |
| `bingTargetEndpoint`   | Bing API endpoint (defaults to `https://api.bing.microsoft.com/`)  |
| `LOGIC_APP_NAME`       | Name of your Logic App for meeting/event retrieval                 |
| `TRIGGER_NAME`         | Name of the Logic App trigger (e.g., `When_a_HTTP_request_is_received`) |
| `isSharedToAll`        | Whether the connection is shared with all users                    |

## Example Agent Interaction

#### User:
What meetings do I have on 5/12/2025?

#### Meetings and Insights Agent:
You have the following meetings scheduled for 5/12/2025:
- **Project Sync**: 10:00 AM - 11:00 AM, Attendees: alice@contoso.com, bob@contoso.com
- **External Partner Call**: 2:00 PM - 3:00 PM, Attendees: external@externalemail.com

Would you like public insights about any of the attendees?

#### User:
Yes, tell me about external@externalemail.com.

#### Meetings and Insights Agent:
According to Bing, "external" is a project manager at External Corp, with experience in cloud solutions and digital transformation. (Source: online public sources)

## Customization Tips
- Modify the system instructions in `template.py` to tailor the agent’s behavior.
- Extend the agent with additional tools or APIs (using OpenAPI spec) for more advanced meeting analytics or integrations.
- Adjust the Logic App workflow to return more or less detail as needed.

## Security & Best Practices
- **Never commit your `.env` or any file containing real secrets to the repository.**
- Use [Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/basic-concepts) for production secrets management.
- Review and follow [Azure best practices](https://learn.microsoft.com/en-us/azure/architecture/best-practices/).

## License
This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.
```
