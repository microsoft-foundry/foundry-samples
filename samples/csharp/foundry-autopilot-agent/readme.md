# 🤖 Foundry Autopilot Agent Example

> A minimal example of deploying a Foundry Autopilot agent with Azure Developer CLI

---

## 📋 Prerequisites

**Note:** You must be enrolled in the [Frontier preview program](https://adoption.microsoft.com/en-us/copilot/frontier-program/) to publish a Foundry agent as Autopilot.

Ensure you have the following installed:

| Requirement | Description |
|-------------|-------------|
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | Azure authentication and role management |
| [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Infrastructure deployment tool |
| [.NET 9.0 SDK](https://dotnet.microsoft.com/download) | Development framework |

### 🔐 Required Permissions

- **Owner** role on the Azure subscription
- **Foundry User** or **Cognitive Services User** role at subscription or resource group level
- Access to a Microsoft 365 administrator who can approve and activate the agent blueprint

---

## 🚀 Quick Start

### Step 1: Authenticate

Log in to your Azure tenant with Azure CLI and Azure Developer CLI:

```powershell
# Log in to Azure CLI
az login --tenant <tenant-id>

# Log in to Azure Developer CLI
azd auth login --tenant-id <tenant-id>
```

### Step 2: Deploy Everything

> **📍 Region availability:** This sample uses [Foundry hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd). Your Foundry account and other resources must be in a region where hosted agents are available. At the time of writing, supported regions are:
>
> Australia East, Brazil South, Canada Central, Canada East, East US, East US 2, France Central, Germany West Central, Italy North, Japan East, Korea Central, North Central US, Norway East, Poland Central, South Africa North, South Central US, South India, Southeast Asia, Spain Central, Sweden Central, Switzerland North, UAE North, UK South, West Central US, West US, West US 3.

#### Optional: Customize Your Agent

Before deploying, you can customize:
- **Agent instructions:** [AgentInstructions.cs](./src/hello_world_a365_agent/AgentLogic/AgentInstructions.cs)
- **MCP tools:** [ToolManifest.json](./src/hello_world_a365_agent/ToolingManifest.json) - [Learn more](https://learn.microsoft.com/en-us/microsoft-agent-365/tooling-servers-overview)

#### Deploy

```powershell
azd provision
```

After deployment completes, inspect your resource values:

```powershell
azd env get-values
```

### Step 3: Tenant Admin Approves the Agent in Microsoft Admin Center

1. Navigate to the [Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested)
2. Under **Requests**, locate your **agent blueprint**:
   ![Microsoft 365 admin center showing an agent blueprint request](image.png)

3. Click the **Approve request and activate** button to approve the blueprint:
   ![Screenshot of the agent blueprint approval dialog with the 'Approve request and activate' button highlighted](image-1.png)

### Step 4: Create Agent Instances

1. In Microsoft Teams, navigate to **Apps** → **Agents for your team**
2. Find your agent blueprint and create an instance:
   ![Screenshot of Microsoft Teams showing the 'Agents for your team' section with an agent listed](image-4.png)

---

## 🏗️ Architecture Overview

This deployment orchestrates four key components to create a fully functional Autopilot agent:

### 1️⃣ Creating a Foundry Project

Creates a Foundry project configured to support hosted agents with appropriate permissions on an Azure Container Registry for building and storing Docker images.

📚 [Learn more about prerequisites](https://github.com/microsoft/container_agents_docs?tab=readme-ov-file#11---prerequisites)

### 2️⃣ Building a Hosted Agent Docker Image

Compiles the sample code into a Docker container and registers it as a hosted agent with the Foundry project.

📚 [Learn more about building agents](https://github.com/microsoft/container_agents_docs?tab=readme-ov-file#14---build-agent-image)

### 3️⃣ Creating the Agent

Creates the hosted agent using the Docker image above.

📚 [Learn more about agent deployment](https://github.com/microsoft/container_agents_docs?tab=readme-ov-file#step-2-deploy-agent)

### 4️⃣ Publishing to Your Organization

Publishes the agent to Microsoft 365 via Foundry


---

## 📜 Hosted Agent Logs

If you receive an error, the response will include a `FOUNDRY_AGENT_SESSION_ID`. Use it to stream the hosted agent's session logs:

```bash
eval "$(azd env get-values)"
export FOUNDRY_AGENT_SESSION_ID="<session-id-from-error-response>"
ACCESS_TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"

curl -N \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: text/event-stream" \
  -H "Cache-Control: no-cache" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  "https://$ACCOUNT_NAME.services.ai.azure.com/api/projects/$PROJECT_NAME/agents/$AGENT_NAME/sessions/$FOUNDRY_AGENT_SESSION_ID:logstream?api-version=2025-11-15-preview"
```

The agent also sends ASP.NET Core requests, outgoing HTTP dependencies, exceptions, and `ILogger` entries to Application Insights. Request correlation is preserved when `CloudAdapter` moves an activity to its background queue, so telemetry from `A365AgentApplication` shares the `/activity/messages` `operation_Id`. Foundry injects `APPLICATIONINSIGHTS_CONNECTION_STRING` into the hosted container. Set the same environment variable when running locally if you want local telemetry in Application Insights.

---

## 📖 Additional Resources

- [Foundry Container Agents Documentation](https://github.com/microsoft/container_agents_docs)
- [Azure Developer CLI Documentation](https://learn.microsoft.com/azure/developer/azure-developer-cli/)
- [Agent Blueprint Configuration](https://dev.teams.microsoft.com/tools/agent-blueprint)

---

## 🤝 Support

For issues or questions, please refer to the official documentation or contact your Azure administrator.
