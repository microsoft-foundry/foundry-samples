// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Azure.AI.AgentServer.A2A;
using Azure.AI.AgentServer.Core;
using TravelAgents;

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
builder.Services.AddSingleton<ResearchRuntime>();
builder.AddA2A<TravelAgent>(TravelAgent.CreateCard(
    Settings.Required("AGENT_ROLE"),
    Environment.GetEnvironmentVariable("A2A_AGENT_URL") ?? "http://localhost:8088/a2a"));
await builder.Build().RunAsync();

public partial class Program;
