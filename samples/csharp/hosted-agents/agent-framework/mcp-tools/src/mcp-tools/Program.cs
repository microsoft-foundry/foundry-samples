// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a hosted agent with two layers of MCP (Model Context Protocol) tools:
//
// 1. CLIENT-SIDE MCP: The agent connects to the Microsoft Learn MCP server directly via
//    McpClient, discovers tools, and handles tool invocations locally within the agent process.
//
// 2. SERVER-SIDE MCP: The agent declares a HostedMcpServerTool for the same MCP server which
//    delegates tool discovery and invocation to the LLM provider (Azure OpenAI Responses API).
//    The provider calls the MCP server on behalf of the agent — no local connection needed.
//
// Both patterns use the Microsoft Learn MCP server to illustrate the architectural difference:
// client-side tools are resolved and invoked by the agent, while server-side tools are resolved
// and invoked by the LLM provider.

#pragma warning disable MEAI001 // HostedMcpServerTool is experimental

using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

// Load .env file if present (for local development)
Env.NoClobber().TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT environment variable is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

// ── Client-side MCP: Microsoft Learn (local resolution) ──────────────────────
// Connect directly to the MCP server. The agent discovers and invokes tools locally.
Console.WriteLine("Connecting to Microsoft Learn MCP server (client-side)...");

await using var learnMcp = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("https://learn.microsoft.com/api/mcp"),
    Name = "Microsoft Learn (client)",
}));

var clientTools = await learnMcp.ListToolsAsync();
Console.WriteLine($"Client-side MCP tools: {string.Join(", ", clientTools.Select(t => t.Name))}");

// ── Server-side MCP: Microsoft Learn (provider resolution) ───────────────────
// Declare a HostedMcpServerTool — the LLM provider (Responses API) handles tool
// invocations directly. No local MCP connection needed for this pattern.
AITool serverTool = new HostedMcpServerTool(
    serverName: "microsoft_learn_hosted",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};
Console.WriteLine("Server-side MCP tool: microsoft_docs_search (via HostedMcpServerTool)");

// ── Combine both tool types into a single agent ──────────────────────────────
// Keep microsoft_docs_search provider-hosted because registering the same tool name through
// both paths makes the Responses request invalid. The remaining tools still demonstrate
// client-side invocation while search demonstrates provider-side invocation.
List<AITool> allTools =
[
    .. clientTools.Where(tool => tool.Name != "microsoft_docs_search").Cast<AITool>(),
    serverTool
];

AIAgent agent = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful developer assistant with access to Microsoft Learn documentation.
            Use the available tools to search and retrieve documentation.
            Be concise and provide direct answers with relevant links.
            """,
        name: "mcp-tools",
        description: "Developer assistant with dual-layer MCP tools (client-side and server-side)",
        tools: allTools);

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();
