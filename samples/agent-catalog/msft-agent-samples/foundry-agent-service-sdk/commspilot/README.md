# CommsPilot Agent

## Summary
The CommsPilot Agent code sample enables agent creation for personalized outbound sales emails and outreach logging. Built using Azure AI Agent Service, it helps enterprise users compose high-quality, personalized, and professional emails by combining internal knowledge, real-time context, and publicly grounded data via Bing. The agent streamlines enterprise communication by handling formatting, tone, and relevant context with minimal input from the user.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

## Use Cases
1. Context-Aware Email Drafting: Generate customer-ready responses using internal tools and documentation.
2. Public Information Integration: Enrich emails with publicly available facts using Bing grounding.
3. Brand-Aligned Formatting: Automatically apply formatting guidelines (headers, bullets, inline links, etc.).
4. Rapid Comms: Help support agents, product managers, and engineers respond faster and more consistently.
5. Multi-Tool Intelligence: Integrate outputs from internal tools and APIs (e.g., product APIs, support logs) to create unified responses.

## Architecture Overview
The system consists of:

- An AI Agent built using Azure AI Agent Service with gpt-4o as the base model.
- A Bing Grounding Tool for referencing publicly available content and insights.
- Internal data tools (e.g., API wrappers, logic apps) that provide customer-specific, account-specific, or enterprise-specific content.
- A custom system prompt designed to enforce formatting, tone, and response structure guidelines.

## Architecture Overview

CommsPilot Agent uses Azure AI Agent Service and is equipped with two main knowledge sources: internal documentation and external web grounding. It receives incoming support emails, drafts polished, context-aware replies, and sends them back through Outlook via Logic Apps.

### Flow Diagram

```text
                      +------------------------+
                      |   Incoming Support     |
                      |       Request (Email)  |
                      +-----------+------------+
                                  |
                                  v
                       +------------------------+
                       |      CommsPilot Agent  |
                       |   (Azure AI Agent +    |
                       |   Custom Tooling)      |
                       +-------------+----------+
                                     |
                    +----------------+-----------------+
                    |                                  |
                    v                                  v
        +----------------------------+    +----------------------------+
        | Internal Knowledge Tool    |    | Bing Grounding Tool        |
        | (Files, FAQs, KBs, Manuals)|    | (External references,      |
        |                            |    |  validation, enhancements) |
        +----------------------------+    +----------------------------+
                                       |
                                       v
                          +---------------------------+
                          | Drafted Support Response  |
                          | - Factually accurate      |
                          | - Context-aware           |
                          | - Formatted professionally|
                          +-------------+-------------+
                                        |
                                        v
                          +----------------------------+
                          | Send via Outlook using     |
                          | Logic App Action           |
                          +----------------------------+
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
   
### Template specific requirements:
- Bing Grounding resource
- Logic App for sending email

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

5. Go to ai.azure.com, choose the same project and go to the Agents playground to find the above agent.
   
   Add the following tools:
   1. File search (internal documents, FAQs, etc.)
   2. Add the Logic Apps tool (Instructions in /assets/logic-app-setup.md)

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
Incoming support request ID: #ContosoSupport12345        
Name: FirstName LastName      
From: email@contoso.com
Question: What formats are supported by document translation service? 

#### CommsPilot Agent:
Email has been sent. Reference:

Subject: #ContosoSupport12345 Response from Contoso AI

Dear FirstName,

Thank you for reaching out about the document translation service. Below is the list of file formats supported by the service:

Supported File Formats:
Adobe PDF (.pdf): Uses OCR to extract and translate text while retaining original layout.
Comma-Separated Values (.csv): Raw data files used by spreadsheet applications.
HTML (.html, .htm): Standard markup language for web pages.
XML Localization Interchange File Format (.xliff, .xlf): Export of Translation Memory systems.
Markdown (.markdown, .md, and other variations): Used for formatted text creation.
MHTML (.mhtml, .mht): A web page archive format.
Microsoft Office Formats:
Microsoft Excel (.xls, .xlsx)
Microsoft Word (.doc, .docx)
Microsoft PowerPoint (.ppt, .pptx)
Microsoft Outlook (.msg)
OpenDocument Standards:
OpenDocument Text (.odt)
OpenDocument Presentation (.odp)
OpenDocument Spreadsheet (.ods)
Rich Text Format (.rtf): Text documents with formatting.
Tab Separated Values (.tsv, .tab): Another raw data text format.
Plain Text (.txt): Unformatted text documents.

Best regards,
Contoso AI Support Team

## Customization Tips
- Modify the system instructions in `template.py` to tailor the agent’s behavior.
- Extend the agent with additional tools or APIs (using OpenAPI spec) for more advanced automation and inbox tracking using logic apps.
- Adjust the Logic App workflow to return more or less detail as needed.

## Security & Best Practices
- **Never commit your `.env` or any file containing real secrets to the repository.**
- Use [Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/basic-concepts) for production secrets management.
- Review and follow [Azure best practices](https://learn.microsoft.com/en-us/azure/architecture/best-practices/).

## License
This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.
```
