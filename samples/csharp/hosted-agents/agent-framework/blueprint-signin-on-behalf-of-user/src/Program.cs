#pragma warning disable OPENAI001

using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT.");
var model = Required("AZURE_AI_MODEL_DEPLOYMENT_NAME");
var toolbox = Required("TOOLBOX_NAME");
var credential = new DefaultAzureCredential();

AIAgent agent = new AIProjectClient(new Uri(endpoint), credential).AsAIAgent(
    model: model,
    name: "hosted-blueprint-greeting",
    description: "Hosted blueprint sign-in and delegated MCP greeting sample.",
    instructions: "When asked for a tool greeting, call the greeting tool from the toolbox exactly once and report its greeting and invocation ID verbatim. Never claim a tool call succeeded if it failed.");

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.Services.AddFoundryToolboxes(credential, toolbox);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());
builder.Build().Run();

static string Required(string name) =>
    Environment.GetEnvironmentVariable(name) is { Length: > 0 } value
        ? value
        : throw new InvalidOperationException($"Set {name} before starting the agent.");
