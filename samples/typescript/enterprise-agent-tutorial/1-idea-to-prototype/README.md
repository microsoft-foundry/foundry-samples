# Modern Workplace Assistant - TypeScript

This is a TypeScript implementation of the Modern Workplace Assistant sample, demonstrating enterprise AI patterns using Azure AI Agents SDK v2.

## Overview

This sample showcases a complete business scenario using Azure AI Agents SDK v2:
- Agent creation with the new SDK
- Thread and message management
- Robust error handling and graceful degradation
- SharePoint integration for company policies
- Microsoft Learn MCP integration for technical documentation
- Comprehensive evaluation framework

## Business Scenario

An employee needs to implement Azure AD multi-factor authentication and requires:
1. Company security policy requirements (from SharePoint)
2. Technical implementation steps (from Microsoft Learn)
3. Combined guidance showing how policy requirements map to technical implementation

## Prerequisites

- Node.js 20.0.0 or later
- Azure AI Foundry project with a deployed model
- Azure CLI installed and logged in (`az login`)
- (Optional) SharePoint connection configured in Azure AI Foundry
- (Optional) Microsoft Learn MCP server access

## Installation

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment variables:**
   
   Copy `.env.template` to `.env` and fill in your values:
   ```bash
   cp .env.template .env
   ```

   Required variables:
   - `PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
   - `MODEL_DEPLOYMENT_NAME`: Name of your deployed model (e.g., gpt-4o-mini)

   Optional variables:
   - `MCP_SERVER_URL`: Microsoft Learn MCP server URL (works out-of-the-box)
   - `SHAREPOINT_RESOURCE_NAME`: SharePoint connection name (requires setup)

3. **Build the TypeScript code:**
   ```bash
   npm run build
   ```

## Usage

### Run the Main Demo

```bash
npm start
```

This will:
1. Create the Modern Workplace Assistant agent
2. Demonstrate business scenarios with the agent
3. Offer an interactive mode for testing

### Run the Evaluation

```bash
npm run evaluate
```

This will:
1. Create an agent for evaluation
2. Run all test questions from `questions.jsonl`
3. Validate responses based on expected data sources
4. Generate an `evaluation_results.json` file

### Development Mode

For development with automatic rebuild:
```bash
npm run dev
```

## Project Structure

```
.
├── src/
│   ├── main.ts           # Main application with agent creation and demos
│   └── evaluate.ts       # Evaluation script for testing agent quality
├── package.json          # Node.js dependencies and scripts
├── tsconfig.json         # TypeScript configuration
├── questions.jsonl       # Test questions for evaluation
├── .env.template         # Environment variable template
└── README.md            # This file
```

## Key Features

### Dynamic Agent Capabilities

The agent automatically adapts based on available resources:
- **SharePoint + MCP**: Full capability with company policies and Microsoft docs
- **SharePoint only**: Company policies with general technical knowledge
- **MCP only**: Microsoft Learn documentation access
- **Neither**: General Azure and M365 technical knowledge

### Error Handling

The sample demonstrates production-ready error handling:
- Graceful degradation when tools are unavailable
- Clear diagnostic messages for troubleshooting
- Connection resolution with fallback patterns

### MCP Approval Handler

Demonstrates the MCP approval pattern with automatic approval for tool calls. In production, you can customize this for:
- RBAC checks
- Cost controls
- Logging and auditing
- Interactive approval prompts

### Evaluation Framework

The evaluation script validates:
- SharePoint tool usage (Contoso-specific content)
- MCP tool usage (Microsoft Learn links)
- Hybrid scenarios (both tools working together)
- Overall agent quality and pass rates

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   User Application                       │
│                    (main.ts)                            │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│            Azure AI Agents SDK v2                        │
│              (@azure/ai-agents-ii)                      │
└─────────────┬───────────────────┬───────────────────────┘
              │                   │
              ▼                   ▼
┌─────────────────────┐ ┌─────────────────────────────────┐
│  SharePoint Tool    │ │    Microsoft Learn MCP          │
│  (Company Policies) │ │    (Technical Docs)             │
└─────────────────────┘ └─────────────────────────────────┘
```

## Troubleshooting

### TypeScript Errors

The TypeScript errors shown before `npm install` are expected. Run:
```bash
npm install
npm run build
```

### Connection Issues

If you see "Connection not found" errors:
1. Verify your `PROJECT_ENDPOINT` in `.env`
2. Ensure you're logged in with `az login`
3. Check that your Azure account has access to the project
4. For SharePoint, verify the connection exists in Azure AI Foundry portal

### Model Deployment

If you see "Model not found" errors:
1. Check that `MODEL_DEPLOYMENT_NAME` matches your deployed model
2. Verify the model is deployed in Azure AI Foundry portal
3. Ensure you have permissions to access the model

### MCP Server

The Microsoft Learn MCP server should work out-of-the-box. If you encounter issues:
1. Verify `MCP_SERVER_URL` is set correctly
2. Check your network connectivity
3. Review the agent output for specific error messages

## Educational Focus

This sample teaches:
- **Enterprise AI Patterns**: Real-world agent implementation with Agent SDK v2
- **Business Scenarios**: Solving actual enterprise problems
- **Production Readiness**: Error handling, diagnostics, and graceful degradation
- **Tool Integration**: SharePoint and MCP tool usage patterns
- **Evaluation**: Testing agent quality and validating tool usage

## Next Steps

This tutorial is part of a series:
1. **Tutorial 1 (This)**: Idea to Prototype - Building the agent
2. **Tutorial 2**: Prototype to Production - Governance and evaluation
3. **Tutorial 3**: Production to Adoption - Monitoring and deployment

## Related Samples

- Python version: `samples/microsoft/python/enterprise-agent-tutorial/1-idea-to-prototype/`
- C# version: `samples/microsoft/csharp/enterprise-agent-tutorial/1-idea-to-prototype/`
- Java version: `samples/microsoft/java/enterprise-agent-tutorial/1-idea-to-prototype/`

## Resources

- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-studio/)
- [Azure AI Agents SDK v2](https://www.npmjs.com/package/@azure/ai-agents-ii)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please see the CONTRIBUTING.md file for guidelines.
