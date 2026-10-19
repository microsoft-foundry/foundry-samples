// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.Identity;
using BrowserAutomation;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

Env.NoClobber().TraversePath().Load();

var projectEndpoint = new Uri(
    Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException(
        "FOUNDRY_PROJECT_ENDPOINT environment variable is not set."));
var deployment =
    Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? Environment.GetEnvironmentVariable("BROWSER_AGENT_MODEL")
    ?? throw new InvalidOperationException(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set.");
var toolboxName = Environment.GetEnvironmentVariable("TOOLBOX_NAME")
    ?? "browser-automation-tools";

if (string.IsNullOrEmpty(
        Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_ENDPOINT")))
{
    Environment.SetEnvironmentVariable(
        "FOUNDRY_AGENT_TOOLSET_ENDPOINT",
        $"{projectEndpoint.ToString().TrimEnd('/')}/toolboxes");
}

var skillsDir = Path.Combine(AppContext.BaseDirectory, "skills");
if (!Directory.Exists(skillsDir))
    skillsDir = Path.Combine(Directory.GetCurrentDirectory(), "skills");

var promptsDir = Path.Combine(AppContext.BaseDirectory, "prompts");
if (!Directory.Exists(promptsDir))
    promptsDir = Path.Combine(Directory.GetCurrentDirectory(), "prompts");
var systemPrompt = File.ReadAllText(Path.Combine(promptsDir, "base.md"));

var skillsProvider = new AgentSkillsProvider(
    skillsDir,
    options: new AgentSkillsProviderOptions
    {
        DisableLoadSkillApproval = true,
        DisableRunSkillScriptApproval = true,
    });

AIAgent baseAgent = new AIProjectClient(
        projectEndpoint,
        new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "browser-automation",
        Description = "A browser automation agent using Azure Playwright tools",
        ChatOptions = new ChatOptions
        {
            ModelId = deployment,
            Instructions = systemPrompt,
        },
        AIContextProviders = [skillsProvider],
    });

var agent = baseAgent
    .AsBuilder()
    .Use(Middlewares.FunctionInvocationMiddleware)
    .Use(
        Middlewares.LiveViewUrlMiddleware,
        Middlewares.LiveViewUrlStreamingMiddleware)
    .Build();

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.Services.AddFoundryToolboxes(
    new ToolboxScopedCredential(new DefaultAzureCredential()),
    options => options.ApiVersion = "v1",
    toolboxName);
builder.RegisterProtocol(
    "responses",
    endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();
