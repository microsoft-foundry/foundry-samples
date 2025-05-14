# Meeting Prep Agent

## Summary
This code sample helps build an agent that helps with meetings by researching attendees and generating contextual summaries. Built using Azure AI Agent Service, it helps users retrieve meeting and call details, attendee lists, and differentiate between internal and external participants by integrating with Azure Logic Apps. The agent also leverages the **Bing Grounding Tool** to provide relevant, publicly available insights about meeting participants.

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

The component descriptions:
- Logic App Tool – Retrieves meeting and call details via Azure Logic Apps. 
- Bing Grounding Tool – Provides public data about meeting participants. 
- AI Agent – Uses `gpt-4o` as the base model to analyze meeting context and summarize attendee information.

## Setup Instructions

### Prerequisites
- Python 3.8+
- Required Dependencies (install via requirements.txt)
```bash
pip install -r requirements.txt
```
- Azure CLI
- Azure subscription
- Agent setup: deploy the latest agent setup using ([this custom deployment](https://github.com/azure-ai-foundry/foundry-samples/tree/main/use-cases/agents/setup/basic-setup)).
  - The above creates:
    1. AI Services resource
    2. AI Project
    3. Model deployment 
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

## Troubleshooting Guide

**Issue: Authentication Error in Logic Apps**

- Ensure that Azure credentials are correctly configured. 
- Run the following to refresh credentials:
```bash
az login --tenant <your-tenant-id>
```

**Issue: Bing Search Not Returning Results**

- Check your `BING_CONNECTION_ID` in environment variables. 
- Verify Bing API rate limits in Azure Monitor.

## License
This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.
```
