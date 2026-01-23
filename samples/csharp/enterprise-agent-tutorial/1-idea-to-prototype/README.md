# Enterprise Agent Tutorial - Stage 1: Idea to Prototype (C#)

> **Full Feature Parity with Python Sample:** This C# implementation now uses Azure.AI.Agents.Persistent SDK with complete support for SharePoint and MCP (Model Context Protocol) tools, matching the Python sample functionality.
> - Packages: `Azure.AI.Projects` (1.0.0-beta.9) + `Azure.AI.Agents.Persistent` (1.2.0-beta.8)
> - Client: `PersistentAgentsClient` from `AIProjectClient.GetPersistentAgentsClient()`
> - Tools: `SharepointToolDefinition` + `MCPToolDefinition`
> - MCP Approvals: `SubmitToolApprovalAction` + `ToolApproval` pattern

This C# implementation demonstrates building and evaluating an enterprise agent with SharePoint and MCP integration using the Azure AI Foundry SDK.

## Project Structure

```text
1-idea-to-prototype/
├── ModernWorkplaceAssistant/    # Main agent demonstration
│   ├── Program.cs               # Agent implementation with SharePoint + MCP
│   ├── ModernWorkplaceAssistant.csproj
│   └── .env                     # Your environment configuration (create this)
├── Evaluate/                    # Evaluation project
│   ├── Program.cs               # Batch evaluation with keyword matching
│   └── Evaluate.csproj
├── questions.jsonl              # Evaluation questions
└── README.md                    # This file
```

## Quick Start

### 1. Configure Environment

Create a `.env` file in the `ModernWorkplaceAssistant` directory with your Azure AI Foundry settings:

```dotenv
# Azure AI Foundry Configuration
PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/api/projects/your-project
MODEL_DEPLOYMENT_NAME=gpt-4o-mini

# SharePoint Integration (Optional - requires full ARM resource ID)
# Format: /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{workspace}/connections/{name}
SHAREPOINT_CONNECTION_ID=/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.MachineLearningServices/workspaces/xxx/connections/ContosoCorpPolicies

# Microsoft Learn MCP Server (Optional)
MCP_SERVER_URL=https://learn.microsoft.com/api/mcp
```

### 2. Run the Main Agent

```bash
cd ModernWorkplaceAssistant
dotnet restore
dotnet run
```

This demonstrates three business scenarios:
- Company policy questions (SharePoint)
- Technical implementation questions (MCP)
- Combined business implementation (SharePoint + MCP)

### 3. Run Evaluation

```bash
cd ../Evaluate
dotnet restore
dotnet run
```

This runs batch evaluation against 4 test questions and generates `evaluation_results.json`.

## Key Features

- **Parallel Projects**: Both projects are peers, not nested
- **Shared Configuration**: Common files in `shared/` directory
- **SharePoint Integration**: Using connection ID directly (C# SDK pattern)
- **MCP Integration**: Manual approval handling for MCP tool calls
- **Business-Focused**: Realistic workplace assistant scenarios

## Environment Variables

Create a `.env` file with:

- `PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `MODEL_DEPLOYMENT_NAME`: Your deployed model name (e.g., `gpt-4o-mini`)
- `SHAREPOINT_CONNECTION_ID`: *(Optional)* **Full ARM resource ID** for SharePoint connection
  - Format: `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{workspace}/connections/{name}`
  - Note: The C# SDK requires the full ARM ID (not just the connection name)
- `MCP_SERVER_URL`: *(Optional)* Microsoft Learn MCP server URL (e.g., `https://learn.microsoft.com/api/mcp`)

## Documentation

- Python version: `samples/python/enterprise-agent-tutorial/` for reference
- For SharePoint setup, see the Azure AI Foundry documentation on connections

## Documentation

For detailed setup instructions, SharePoint configuration, and MCP server setup, see:

- `shared/README.md` - Complete setup guide
- `shared/MCP_SERVERS.md` - MCP server configuration
- `shared/SAMPLE_SHAREPOINT_CONTENT.md` - Sample SharePoint documents

## Troubleshooting

1. Ensure `.env` exists in the `ModernWorkplaceAssistant/` directory
2. Verify all required environment variables are set
3. For SharePoint, ensure you have the **full ARM resource path** (not just the name)
4. Ensure you're authenticated with `az login` for the correct tenant

## Next Steps

- **Tutorial 2**: Add governance, monitoring, and comprehensive evaluation
- **Tutorial 3**: Deploy to production with scaling and security

For more information, visit the [Azure AI Foundry documentation](https://learn.microsoft.com/azure/ai-foundry/).
