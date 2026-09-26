// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

Env.NoClobber().TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT environment variable is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set.");

// Steering is an AgentServer conversation capability, so a regular model-backed agent is enough;
// no workflow or application-managed queue is required for this sample.
AIAgent agent = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful AI assistant. When another message arrives while you are working,
            treat it as a course correction and incorporate it into the next answer. Preserve text
            enclosed in square brackets exactly.
            """,
        name: "steering",
        description: "A steerable long-running AI assistant");

var builder = AgentHost.CreateBuilder(args);

// AgentServer makes the queueing decision when Responses services are first registered. Steering
// and crash recovery are separate options; this sample intentionally enables steering only.
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.SteerableConversations = true);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();
