// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Azure.AI.AgentServer.A2A;
using Azure.AI.AgentServer.Core;
using EchoA2A;

var builder = AgentHost.CreateBuilder(args);
// Match the Python reference: snapshots live in this process, not in Foundry storage.
builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
builder.AddA2A<EchoAgent>(EchoAgent.CreateCard(
    Environment.GetEnvironmentVariable("A2A_AGENT_URL") ?? "http://localhost:8088/a2a"));
await builder.Build().RunAsync();
