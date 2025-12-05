# Enterprise Agent Tutorial - Stage 1: Idea to Prototype (C#)

> **SDK v2.0 Update:** This sample has been updated to use Azure AI Agents SDK version 2.0.0-alpha.20251016.2. Key changes:
> - Package: `Azure.AI.Agents.Persistent` → `Azure.AI.Agents` + `OpenAI`
> - Client: `PersistentAgentsClient` → `AgentsClient`
> - Agent creation: `CreateAgentAsync()` → `CreateAgentVersionAsync()` with `PromptAgentDefinition`
> - Conversation: Thread/Run pattern → OpenAI Client with `ResponseCreationOptions`
> - Agent references: Use `agent.Name` instead of `agent.Id`

This C# implementation demonstrates building and evaluating an enterprise agent with SharePoint and MCP integration using the Azure AI Foundry SDK.

## Project Structure

```text
1-idea-to-prototype/
├── ModernWorkplaceAssistant/    # Main agent demonstration
│   ├── Program.cs               # Agent implementation with SharePoint + MCP
│   └── ModernWorkplaceAssistant.csproj
├── Evaluate/                    # Evaluation project
│   ├── Program.cs               # Batch evaluation with keyword matching
│   └── Evaluate.csproj
├── shared/                      # Shared configuration files
│   ├── .env                     # Environment variables (user-specific)
│   ├── .env.template            # Environment variables template
│   ├── questions.jsonl          # Evaluation questions
│   ├── README.md                # Detailed setup instructions
│   ├── MCP_SERVERS.md           # MCP server configuration guide
│   └── SAMPLE_SHAREPOINT_CONTENT.md  # Sample SharePoint documents
└── README.md                    # This file
```

## Quick Start

### 1. Configure Environment

Copy the template and configure your Azure AI Foundry settings:

```bash
cd shared
cp .env.template .env
# Edit .env with your Azure AI Foundry project details
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

The `.env` file in `shared/` requires:

- `PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `MODEL_DEPLOYMENT_NAME`: Your deployed model name (e.g., `gpt-4o-mini`)
- `AI_FOUNDRY_TENANT_ID`: Your Azure AI Foundry tenant ID
- `MCP_SERVER_URL`: Microsoft Learn MCP server URL
- `SHAREPOINT_CONNECTION_ID`: Full ARM resource path to SharePoint connection

See `shared/.env.template` for details.

## Documentation

For detailed setup instructions, SharePoint configuration, and MCP server setup, see:

- `shared/README.md` - Complete setup guide
- `shared/MCP_SERVERS.md` - MCP server configuration
- `shared/SAMPLE_SHAREPOINT_CONTENT.md` - Sample SharePoint documents

## Troubleshooting

Both projects load environment variables from `../shared/.env`. If you encounter issues:

1. Ensure `.env` exists in the `shared/` directory
2. Verify all required environment variables are set
3. Check that SharePoint connection ID is the full ARM resource path
4. Ensure you're authenticated with `az login` for the correct tenant

## Next Steps

- **Tutorial 2**: Add governance, monitoring, and comprehensive evaluation
- **Tutorial 3**: Deploy to production with scaling and security

For more information, visit the [Azure AI Foundry documentation](https://learn.microsoft.com/azure/ai-foundry/).
