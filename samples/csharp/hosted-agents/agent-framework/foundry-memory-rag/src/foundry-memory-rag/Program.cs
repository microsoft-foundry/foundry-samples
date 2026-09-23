// Copyright (c) Microsoft. All rights reserved.

// Foundry Memory RAG Agent
//
// Demonstrates how to host an agent that uses FoundryMemoryProvider so user-private memories
// persist across requests and across sessions. The agent plays a personal coach who remembers
// the user's training goals, dietary preferences, and constraints, and uses them in later turns.
//
// Memory store creation: EnsureMemoryStoreCreatedAsync runs once at startup and is idempotent.
// The store name and embedding model are environment-driven so azd provisioning can wire them.

#pragma warning disable MAAI001 // Microsoft.Agents.AI.Foundry experimental APIs (FoundryMemoryProvider, FoundryMemoryProviderScope)

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

Env.NoClobber().TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT environment variable is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var embeddingDeployment = Environment.GetEnvironmentVariable("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-small";
var memoryStoreName = Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID") ?? "foundry-memory-rag-store";

var projectClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());

// Scope memory to the platform-provided user identity so different users never share memories.
var memoryProvider = new FoundryMemoryProvider(
    projectClient,
    memoryStoreName,
    stateInitializer: HostedFoundryMemoryProviderScopes.PerUser());

// Create the memory store on startup if it does not already exist. Idempotent.
await memoryProvider.EnsureMemoryStoreCreatedAsync(deployment, embeddingDeployment, "Memory store for the personal-coach RAG sample.");

const string Instructions = """
    You are a friendly personal coach. When the user shares training goals, dietary preferences,
    injuries, equipment, or scheduling constraints, remember them and use them in later turns.
    Use known memories about the user when responding, and do not invent details. When you are
    unsure, ask one clarifying question rather than guessing.
    """;

var agent = projectClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "foundry-memory-rag",
    Description = "A personal coach that remembers your training goals across sessions.",
    ChatOptions = new ChatOptions
    {
        ModelId = deployment,
        Instructions = Instructions
    },
    AIContextProviders = [memoryProvider]
});

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();
