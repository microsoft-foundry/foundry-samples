**IMPORTANT NOTE FROM MICROSOFT:** The sample below was created by a third party, not Microsoft, and has not been tested or verified by Microsoft. Your use is subject to the terms provided by the relevant third party.  By using the third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to this sample.  


------


# HR Assist Agent

This repository provides a template for deploying and managing an Azure AI Agent for MiHCM. The project leverages Azure Bicep for infrastructure deployment and Python for interacting with Azure AI services and APIs.


## Features

- **Azure AI Agent Deployment**: Automates the deployment of Azure AI resources, including AI Hubs, AI Projects, and dependent resources.
- **Integration with MiHCM HR System**: Provides tools to interact with MiHCM's HR APIs for tasks like leave management, feedback handling, and work activity tracking.
- **OpenAPI Integration**: Uses OpenAPI specifications to define and interact with MiHCM's external APIs.

## Architecture Overview
![Architecture Overview](./ArchitectureOverview.png)
## Project Structure
- `README.md` – Project documentation  
- `LICENSE` - Project License
- `.env` – Environment variables for the project  
- `deploy.bicep` – Main Bicep file for deploying the AI Agent setup  
- `mihcmexternalAPI.json` – OpenAPI specification for MiHCM's external API  
- `template.py` – Python script for interacting with Azure AI and MiHCM APIs  
- `requirements.txt` – Python dependencies for the project  
- `modules-mi-agent/` – Bicep modules for modular resource deployment  
  - `add-capability-host.bicep` – Adds capability host resource  
  - `ai-service-role-assignments.bicep` – Sets role assignments for AI services  
  - `standard-ai-hub.bicep` – Deploys standard AI Hub  
  - `standard-ai-project.bicep` – Deploys standard AI Project  
  - `standard-dependent-resources.bicep` – Deploys dependent resources  




## Prerequisites

1. **Azure Subscription**: Ensure you have an active Azure subscription.
2. **Azure CLI**: Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli).
3. **Bicep CLI**: Install the [Bicep CLI](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/install).
4. **Python**: Install Python 3.8 or later.
5. **Dependencies**: Install Python dependencies using `pip install -r requirements.txt`.

## Deployment

### Step 1: Configure Environment Variables

Create a `.env` file in the root directory with the following variables:

```properties
PROJECT_CONNECTION_STRING="<Your AI project key>"
PROJECT_OPENAPI_CONNECTION_NAME="<Connection name of your API key>"
```

### Step 2: Deploy Azure Resources
 - Deploy the resources using the `deploy.bicep` file.
 - Update `PROJECT_CONNECTION_STRING` with the connection string obtained.

### Step 3: Define the API Key 
- Navigate to your AI Project and add your API Key as a custom key in the below format:
```
Ocp-Apim-Subscription-Key: <your key>
```
- Update the `PROJECT_OPENAPI_CONNECTION_NAME` with the connection name you created.

### Step 4: Run the python script
- Use the `template.py` script to interact with the deployed Azure AI Agent and MiHCM APIs.
- Update the `agent_request` value with different requests for the agent.

## Use Cases 
- What are my leave balances?
- Check my leave balance for 2024. If I have more than 10 days of annual leave, submit an HR request for leave encashment or carry forward.
- Please show me all my HR requests.
- Submit a work activity for 2.5 hours for the meeting with Adventure Works on the Project Kick-off.
- Submit a work activity for yesterday for 2.5 hours for the meeting with Contoso on the Project Kick-off.
- List all my work items for yesterday and today.

## Support
Have a question or need assistance? Get in touch with our team:
- Support: ai-support@mihcm.com
- Info on how to setup an account with MiHCM: https://mihcm.com/contact-us/ 
