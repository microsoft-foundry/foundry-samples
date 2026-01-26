using Azure.AI.AgentServer.AgentFramework.Extensions;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Azure.AI.OpenAI;
using Azure.Identity;

// Get configuration from environment variables
var openAiEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var toolConnectionId = Environment.GetEnvironmentVariable("TOOL_CONNECTION_ID") ?? throw new InvalidOperationException("TOOL_CONNECTION_ID is not set.");

var credential = new DefaultAzureCredential();

// Create chat client
var chatClient = new AzureOpenAIClient(new Uri(openAiEndpoint), credential)
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .UseFoundryTools(new { type = "mcp", project_connection_id = toolConnectionId }, new { type = "code_interpreter" })
    .UseOpenTelemetry(sourceName: "Agents", configure: (cfg) => cfg.EnableSensitiveData = true)
    .Build();


var agent = new ChatClientAgent(chatClient,
      name: "AgentWithTools",
      instructions: @"You are a helpful assistant with access to tools for fetching Microsoft documentation.

  IMPORTANT: When the user asks about Microsoft Learn articles or documentation:
  1. You MUST use the microsoft_docs_fetch tool to retrieve the actual content
  2. Do NOT rely on your training data
  3. Always fetch the latest information from the provided URL

  Available tools:
  - microsoft_docs_fetch: Fetches and converts Microsoft Learn documentation
  - microsoft_docs_search: Searches Microsoft/Azure documentation
  - microsoft_code_sample_search: Searches for code examples")
      .AsBuilder()
      .UseOpenTelemetry(sourceName: "Agents", configure: (cfg) => cfg.EnableSensitiveData = true)
      .Build();

// Run agent with tool support using ToolDefinition objects
await agent.RunAIAgentAsync(telemetrySourceName: "Agents");
