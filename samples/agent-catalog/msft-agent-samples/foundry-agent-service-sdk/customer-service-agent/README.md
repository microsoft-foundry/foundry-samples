# 💬 Customer Support Agent

This is a code sample for a multi-phase workflow built with Azure AI Agent Service, designed to assist customers with secure authentication and billing inquiries. It uses a state-based orchestration to verify customer identity and retrieve billing information, while supporting human-in-the-loop escalation.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

---

## 💼 Use Cases

- **Customer Authentication**: Verify users through ID or account number prior to handling sensitive queries.
- **Billing Inquiry Support**: Retrieve and explain billing details for a verified account.
- **Agent Escalation Readiness**: Stream output to users and fallback to human-in-loop if input or context is missing.
- **Workflow Handoff**: Easily expandable to handle follow-ups like payment assistance, usage summaries, or complaint handling.

---

## 🧩 Tools & Capabilities

This agent is orchestrated using **Azure AI Agent Service** with the following states and components:

### 🔐 `Authentication` State

- **Agent**: `CustomerAuthenticator`  
- **Purpose**: Validates the customer and extracts a `CustomerId`
- **Human-in-the-loop**: Enabled on missing input or failed authentication
- **Output**:  
  - `CustomerAccount → CustomerId`

---

### 💳 `Billing` State

- **Agent**: `CustomerServiceAgent`  
- **Purpose**: Retrieves customer billing details using `CustomerId` as input
- **Human-in-the-loop**: Enabled if no message or context is missing
- **Input**:  
  - `accountNumber ← CustomerId`

---

## ⚙️ Setup Instructions

### Prerequisites

1. Azure subscription with the following permissions
   - Contributor or Cognitive Services Contributor role (for resource deployment)
   - Azure AI Developer and Cognitive Services user role (for agent creation)
2. Agent setup: deploy the latest agent setup using this ([custom deployment](https://www.aka.ms/basic-agent-deployment)).
   - The above creates:
      - AI Services resource
      - AI Project
      - Model deployment
3. Azure CLI
4. Install VS Code
5. Download VSCode Extension (Early acccess) from this link https://github.com/azure-ai-foundry/foundry-samples/tree/main/samples/agent-catalog/vscode_ext_early_access
6. Install the early_access extension using the VSIX package
![image](https://github.com/user-attachments/assets/59709d9d-a68b-491d-b8c9-938f3ae46b33)
7. Clone this repo or download the customer_service_agent directory only


### VSCode extension (early access) setup

WARNING: This extension is an experimental version and is not recommended for us in production environments. The official version of the Azure AI Foundry VS Code Extension will be supporting multi-agent workflows in the near future.

1. In shell, run the 'Easy Setup' script below to deploy all the agents and workflows
   
```
set -eu
export CONNECTION_STRING= "<host>;<subscription_id>;<resource_group>;<project_name>"

FILE_PATH="./core/HumanEscalationAgent.agent"  ./src/scripts/deploy.sh
FILE_PATH="./core/RoutingAgent.agent"  ./src/scripts/deploy.sh
FILE_PATH="./core/SelfServiceAgent.agent"  ./src/scripts/deploy.sh
FILE_PATH="./core/TicketCreationAgent.agent"  ./src/scripts/deploy.sh
FILE_PATH="./core/TicketResolutionAgent.agent"  ./src/scripts/deploy.sh
FILE_PATH="./core/WindowsSupport.agent"  ./src/scripts/deploy.sh
FILE_PATH="./workflows/CustomerSupport.fdl"  ./src/scripts/deploy.sh

```

2. Open the 'samples' directory in VS Code
3. Open the customer_support.fdl file in (add path here). You will see the workflows visualizer appear.
![image](https://github.com/user-attachments/assets/5d2e1d3f-9f83-4359-bb59-66b3324cfeb9)
4. Click on 'run' to open the chatbot and interact with the workflow
![image](https://github.com/user-attachments/assets/ae5737e9-a82e-40ff-a6aa-2b80344fb0b5)



### Example Prompts
  - User: I am having trouble launching apps on Windows
  - SelfServiceAgent: The uploaded file contains troubleshooting steps for Windows license activation issues, but it does not address problems related to launching apps on Windows. Let me provide general troubleshooting steps for your issue:

Restart Your Computer: Sometimes, a simple restart can resolve app launch issues.

Check for Windows Updates:

Go to Settings > Update & Security > Windows Update.
Click Check for updates and install any pending updates.
Run the App Troubleshooter:

Open Settings > Update & Security > Troubleshoot.
Select Additional troubleshooters and choose Windows Store Apps.
Run the troubleshooter to detect and fix issues.
Reset the Problematic App:

Go to Settings > Apps > Apps & features.
Select the app that is not launching and click Advanced options.
Click Reset to restore the app to its default state.
Check for Corrupted System Files:

Open Command Prompt as Administrator.
Run the following command:
cmd
sfc /scannow
This will scan and repair corrupted system files.
Reinstall the App:

Uninstall the problematic app and reinstall it from the Microsoft Store or its official website.
Check for Compatibility Issues:

Ensure the app is compatible with your version of Windows. Check the app's system requirements.
Update Graphics Drivers:

Outdated graphics drivers can cause apps to fail. Update your drivers through Device Manager or the manufacturer's website.
Please try these steps and let me know if the issue is resolved or persists. If the problem continues, I will escalate the issue for further assistance.
![image](https://github.com/user-attachments/assets/2d8c5db5-bedd-489e-848d-7f690e84b780)

