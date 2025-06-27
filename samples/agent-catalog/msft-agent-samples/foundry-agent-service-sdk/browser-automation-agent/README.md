# 🌐 Browser Automation Agent

This template helps build an agent that enables users to perform real-world browser tasks through natural language prompts. Powered by **Azure AI Agent Service** and **Azure Playwright Service**, it facilitates multi-turn conversations to automate browser-based workflows such as searching, navigating, filling forms, and booking.

**WARNING:** Browser automation comes with significant security risks. Both errors in judgment by the AI and the presence of malicious or confusing instructions on web pages which the AI encounters may cause it to execute commands you or others do not intend, which could compromise the security of your or other users’ browsers, computers, and any accounts to which the browser or AI has access, including personal information, financial, or enterprise systems.  We recommend that any agent built using this Browser Automation Agent code sample be used only in isolated environments and only with controlled access, such as browsers running within dedicated VMs.  By using the Browser Automation Agent sample, you are acknowledging that you bear responsibility and liability for any use of it and of any resulting agents you create with it, including with respect to any other users to whom you make it or resulting agents available.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

 # 🧠 Scenario Overview

This agent demonstrates a browser automation experience where the user interacts with a website conversationally—like booking a class online. Here's how it works:

1. **User Prompt**: The user asks for available classes.
2. **Session Provisioning**: The request is received by Azure AI Agent Service, which provisions a private browser session using Azure Playwright Service.
3. **Web Interaction**: The browser performs Playwright-driven actions to retrieve and display class options.
4. **Follow-Up Commands**: The user provides further input to complete the booking, all within the same multi-turn thread.

---

## 💼 Use Cases

- **Booking & Reservations**: Automate form-filling and schedule confirmation across booking portals.
- **Product Discovery**: Navigate ecommerce or review sites, search by criteria, and extract summaries.
- **Web Form Interactions**: Log in, submit applications, or upload documents through web UIs.
- **Customer Support Tasks**: Automatically navigate portals to retrieve account status, ticket updates, etc.

---

## 🧩 Tools

This agent leverages **Azure AI Agent Service** and uses:

- **Browser Automation Tool** (via Playwright): Executes browser-based tasks on your behalf, securely and asynchronously.
- **Azure Playwright Service**: Powers the browser session backend with serverless browser capabilities.

The agent is configured through a Python script (`browser_automation.py`) and authenticated using managed identity.

---

## ⚙️ Setup Instructions

### Prerequisites

1. Azure subscription with the following permissions
   - Contributor or Cognitive Services Contributor role (for resource deployment)
   - Azure AI Developer and Cognitive Services user role (for agent creation)
2. Agent setup: deploy the latest agent setup using this ([Agents Set Up](https://learn.microsoft.com/en-us/azure/ai-services/agents/overview#get-started-with-foundry-agent-service)).
   - The above creates:
      - AI Services resource
      - AI Project
      - Model deployment
3. Playwright Resource setup: 
   - Create a Microsoft Playwright Resource: https://learn.microsoft.com/en-us/azure/playwright-testing/how-to-manage-playwright-workspace?tabs=playwright
   - Generate an API Key for the Playwright resource: https://learn.microsoft.com/en-us/azure/playwright-testing/how-to-manage-access-tokens
   - Access the Workspace region endpoint from the Workspace Details. 
4. Create a serverless connection in the Azure AI Foundry project with the Playwright workspace region endpoint and the Playwright Access Key. 
   - Go to the Azure AI Foundry portal and select your AI Project. Go to the Management center and Click connected resources.
   - Create a new connection of type Serverless Model and enter the following information.
      - Target URI - Playwright Workspace Region Endpoint (example - wss://eastus.api.playwright.microsoft.com/accounts/eastus_xxxxxxxxxxxxxxxxxxxxxxx/browsers).
      - Key - Playwright Access Key
   - For more info to create a connection, see [Create a connection](https://learn.microsoft.com/azure/ai-foundry/how-to/connections-add)
5. Python 3.8+
6. Azure CLI

### Environment Variables

Set the following environment variables before running the sample:

```bash
PROJECT_ENDPOINT=<your_project_endpoint>
MODEL_DEPLOYMENT_NAME=<your_model_deployment_name>
PLAYWRIGHT_CONNECTION_ID=<serverless_connection_id>


