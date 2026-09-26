// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Core;
using Azure.AI.AgentServer.Invocations;
using DotNetEnv;
using InvocationsEchoAgent;
using Microsoft.Agents.AI;

// Load environment variables from a .env file if present (for local development).
Env.NoClobber().TraversePath().Load();

var builder = AgentHost.CreateBuilder(args);

// Register the echo agent as a singleton (no LLM needed).
builder.Services.AddSingleton<EchoAIAgent>();

// Register the Invocations SDK services and wire the handler.
builder.Services.AddInvocationsServer();
builder.Services.AddScoped<InvocationHandler, EchoInvocationHandler>();

// Register the Invocations endpoints through AgentHost so the shared port, middleware,
// health checks, platform headers, and telemetry initialization remain active.
builder.RegisterProtocol("invocations", endpoints => endpoints.MapInvocationsServer());

var app = builder.Build();
app.Run();
