# 🤖 Foundry Autopilot Agent Example

> A minimal example of deploying a Foundry Autopilot agent with Azure Developer CLI

---

## 📋 Prerequisites

**Note:** You must be enrolled in the [Frontier preview program](https://adoption.microsoft.com/en-us/copilot/frontier-program/) to publish a Foundry agent as Autopilot.

Ensure you have the following installed:

| Requirement | Description |
|-------------|-------------|
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | Azure authentication and role management |
| [Azure Developer CLI 1.27.1+](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Infrastructure and Toolbox deployment tool |
| [Python 3.11+](https://www.python.org/downloads/) | Agent runtime (built and packaged inside the Docker image) |

### 🔐 Required Permissions

- **Owner** role on the Azure subscription
- **Foundry User** role on the Foundry project
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
- **Agent instructions:** [agent.py](./src/hello_world_a365_agent/agent.py) (the `AGENT_PROMPT` constant on `FoundryDigitalWorkerAgent`)
- **MCP tools:** [ToolingManifest.json](./src/hello_world_a365_agent/ToolingManifest.json) - [Learn more](https://learn.microsoft.com/en-us/microsoft-agent-365/tooling-servers-overview)
- **Foundry Toolbox:** [toolbox.yaml](./toolbox.yaml), which provides web search and code interpreter tools through one managed MCP endpoint

#### Deploy

```powershell
azd env set PUBLIC_NETWORK_ACCESS Enabled
azd provision
```

Provisioning creates the `foundry-autopilot-tools` Toolbox, stores its stable
consumer endpoint in `TOOLBOX_ENDPOINT`, and injects that endpoint into the
hosted agent container. The agent authenticates to the Toolbox with its managed
identity. The existing Microsoft 365 MCP tools continue to use the signed-in
user's delegated token.

After deployment completes, inspect your resource values:

```powershell
azd env get-values
```

### Optional: Enable the Azure DevOps remote MCP server

The Azure DevOps MCP server is disabled unless an organization is configured. Before
provisioning, set the organization name without the `https://dev.azure.com/` prefix:

```powershell
azd env set AZURE_DEVOPS_ORGANIZATION <organization-name>
```

The agent requests a delegated token for
`https://mcp.dev.azure.com/.default`. The agent blueprint's Entra application must
have the `Ado.Mcp.Tools` delegated permission for resource application
`2a72489c-aab2-4b65-b93a-a91edccf33b8`, and the signed-in user must have access to
the Azure DevOps organization.

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

This deployment orchestrates five key components to create a fully functional Autopilot agent:

### 1️⃣ Creating a Foundry Project

Creates a Foundry project configured to support hosted agents with appropriate permissions on an Azure Container Registry for building and storing Docker images.

📚 [Learn more about prerequisites](https://github.com/microsoft/container_agents_docs?tab=readme-ov-file#11---prerequisites)

### 2️⃣ Building a Hosted Agent Docker Image

Compiles the Python sample into a Docker container and registers it as a hosted agent with the Foundry project.

📚 [Learn more about building agents](https://github.com/microsoft/container_agents_docs?tab=readme-ov-file#14---build-agent-image)

### 3️⃣ Creating the Agent

Creates the hosted agent using the Docker image above.

📚 [Learn more about agent deployment](https://github.com/microsoft/container_agents_docs?tab=readme-ov-file#step-2-deploy-agent)

### 4️⃣ Creating a Foundry Toolbox

Creates `foundry-autopilot-tools` with web search and code interpreter tools,
then stores its consumer endpoint for the hosted agent.

### 5️⃣ Publishing to Your Organization

Publishes the agent to Microsoft 365 via Foundry

### Using Foundry Toolbox

The Toolbox defined in [toolbox.yaml](./toolbox.yaml) exposes two managed tools:

- **Web search** for current public information.
- **Code interpreter** for calculations and data analysis.

Web-search URL annotations are returned as numbered Teams citations. If the
tool returns only plain URLs, the agent converts them to citation references
before sending the response.

For ordinary questions received in Teams, the agent sends the answer through
the current Activity so citation metadata reaches the Teams client. The Teams
MCP server is exposed only when the user explicitly asks to send, post, or
forward a message to a Teams chat or channel.

The agent connects to the Toolbox's unversioned consumer endpoint, so a future
default Toolbox version can be promoted without rebuilding the agent image.
Toolbox is optional when running locally; set `TOOLBOX_ENDPOINT` in
`src/hello_world_a365_agent/.env` to enable it.

---

## 📜 Hosted Agent Logs

If you receive an error, the response will include a `FOUNDRY_AGENT_SESSION_ID`. Use it to stream the hosted agent's session logs:

```bash
eval "$(azd env get-values)"
export FOUNDRY_AGENT_SESSION_ID="<session-id-from-error-response>"
ACCESS_TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"

curl -N \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -H "Cache-Control: no-cache" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  "https://$ACCOUNT_NAME.services.ai.azure.com/api/projects/$PROJECT_NAME/agents/$AGENT_NAME/sessions/$FOUNDRY_AGENT_SESSION_ID:logstream?api-version=2025-11-15-preview"
```

The agent sends aiohttp requests, outgoing dependencies, exceptions, Python logs, and GenAI spans to Application Insights. It calls the Responses API through `azure-ai-projects`, whose model-call span includes `gen_ai.operation.name`, `gen_ai.input.messages`, and `gen_ai.output.messages`. The enclosing activity span is named `invoke_agent FoundryDigitalWorker` and includes `gen_ai.operation.name=invoke_agent`, `gen_ai.agent.id`, `microsoft.gen_ai.main_agent.id`, `gen_ai.response.id`, `gen_ai.input.messages`, and `gen_ai.output.messages`. Both agent ID attributes use the `<agentName>:<agentVersion>` format from the Foundry-injected `FOUNDRY_AGENT_NAME` and `FOUNDRY_AGENT_VERSION` environment variables. The `gen_ai.response.id` attribute contains the actual Responses API response ID required by trace-based evaluations. Every exported span includes the `FOUNDRY_PROJECT_ARM_ID` value in the `microsoft.foundry.project.id` custom dimension. Telemetry emitted while `CloudAdapter` processes an activity shares the `/activity/messages` `operation_Id`.

Foundry injects `APPLICATIONINSIGHTS_CONNECTION_STRING` into the hosted container. Set the same environment variable when running locally. GenAI tracing and message-content capture are enabled when Application Insights is configured; set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` before startup when message text must not be recorded.

---

## 📖 Additional Resources

- [Foundry Container Agents Documentation](https://github.com/microsoft/container_agents_docs)
- [Azure Developer CLI Documentation](https://learn.microsoft.com/azure/developer/azure-developer-cli/)
- [Agent Blueprint Configuration](https://dev.teams.microsoft.com/tools/agent-blueprint)

---

## 🤝 Support

For issues or questions, please refer to the official documentation or contact your Azure administrator.
