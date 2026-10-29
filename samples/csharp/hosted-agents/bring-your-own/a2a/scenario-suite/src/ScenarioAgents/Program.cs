// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Azure.AI.AgentServer.A2A;
using Azure.AI.AgentServer.Core;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using ScenarioSuite;
using static ScenarioSuite.SampleCode;

int scenario = int.Parse(Environment.GetEnvironmentVariable("A2A_SUITE_SCENARIO")
    ?? throw new InvalidOperationException("A2A_SUITE_SCENARIO is required."));
if (scenario is < 1 or > 12) { throw new InvalidOperationException("Scenario must be between 1 and 12."); }
AgentCard card = CreateCard();
card.Name = $"A2A scenario {scenario:D2}";
card.Description = $"Fixed sample scenario {scenario:D2}.";
card.SupportedInterfaces[0].Url = Environment.GetEnvironmentVariable("A2A_AGENT_URL") ?? "http://localhost:8088/a2a";

void Configure(AgentHostBuilder builder)
{
    builder.Services.AddSingleton(card);
    if (scenario is not (7 or 12)) { builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>(); }
    builder.Services.AddSingleton(new SuiteIdentity(scenario, Environment.GetEnvironmentVariable("A2A_SUITE_SOURCE_SHA") ?? "local"));
    builder.Services.AddHostedService<ConfigurationVerifier>();
}

switch (scenario)
{
    case 1:
        A2AAgentServer.Run<EchoAgent>(card, args, Configure);
        break;
    case 2:
        A2AAgentServer.Run<TaskAgent>(card, args, Configure);
        break;
    case 3:
        card.Capabilities.Streaming = true;
        A2AAgentServer.Run<StreamingAgent>(card, args, Configure);
        break;
    case 4:
        A2AAgentServer.Run<ClarificationAgent>(card, args, Configure);
        break;
    case 5:
    {
        var builder = AgentHost.CreateBuilder(args);
        Configure(builder);
        builder.Services.AddSingleton<IReportWriter, ReportWriter>();
        builder.AddA2A<ReportAgent>(card);
        builder.Build().Run();
        break;
    }
    case 6:
    {
        var builder = AgentHost.CreateBuilder(args);
        Configure(builder);
        ConfigureServices(builder.Services);
        builder.AddA2A<GreetingAgent>(card, options => options.AutoAppendHistory = false);
        builder.Build().Run();
        break;
    }
    case 7:
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton<ITaskStore, InMemoryTaskStore>();
        services.AddA2AAgent<TaskAgent>(card);
#pragma warning disable ASP0000 // This scenario deliberately hosts a separately owned native request handler.
        await using var nativeServices = services.BuildServiceProvider();
#pragma warning restore ASP0000
        var handler = nativeServices.GetRequiredService<IA2ARequestHandler>();
        A2AAgentServer.Run(card, handler, args, builder =>
        {
            Configure(builder);
            builder.Services.AddSingleton(new NativeRegistration(handler, nativeServices.GetRequiredService<ITaskStore>()));
        });
        break;
    }
    case 8:
    case 11:
    {
        var builder = WebApplication.CreateBuilder(args);
        builder.WebHost.UseUrls($"http://0.0.0.0:{FoundryEnvironment.Port}");
        builder.Services.AddSingleton(new SuiteIdentity(scenario, Environment.GetEnvironmentVariable("A2A_SUITE_SOURCE_SHA") ?? "local"));
        builder.Services.AddHostedService<ConfigurationVerifier>();
        if (scenario == 8)
        {
            builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
            builder.Services.AddA2AAgent<EchoAgent>(card);
            builder.Services.AddFoundryA2A();
        }
        else
        {
            builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
            builder.Services.AddFoundryA2A<EchoAgent>(card);
        }
        await using var app = builder.Build();
        if (scenario == 11) { app.MapGet("/", () => "My application"); }
        app.MapFoundryA2A();
        await app.RunAsync();
        break;
    }
    case 9:
        A2AAgentServer.Run<GreetingAgent>(card, args, builder =>
        {
            Configure(builder);
            Tier1.ConfigureHost(builder);
        });
        break;
    case 10:
    {
        var builder = AgentHost.CreateBuilder(args);
        Configure(builder);
        Tier2.ConfigureHost(builder);
        builder.Build().Run();
        break;
    }
    case 12:
    {
        var builder = AgentHost.CreateBuilder(args);
        Configure(builder);
        builder.Services.AddSingleton<ITaskStore>(_ => new FoundryTaskStore("a2a/scenario-suite/12", itemTtlSeconds: 3600));
        builder.AddA2A<TaskAgent>(card);
        builder.Build().Run();
        break;
    }
}

namespace ScenarioSuite
{
    public sealed record SuiteIdentity(int Scenario, string SourceSha);
    public sealed record NativeRegistration(IA2ARequestHandler Handler, ITaskStore Store);

    public sealed class ConfigurationVerifier(IServiceProvider services, SuiteIdentity identity, ILogger<ConfigurationVerifier> logger) : IHostedService
    {
        public async Task StartAsync(CancellationToken cancellationToken)
        {
            ITaskStore? store = services.GetService<ITaskStore>();
            bool valid = identity.Scenario switch
            {
                7 => store is null,
                12 => store is FoundryTaskStore,
                _ => store is InMemoryTaskStore,
            };
            if (identity.Scenario == 6) { valid &= !services.GetRequiredService<A2AServerOptions>().AutoAppendHistory; }
            if (identity.Scenario == 7)
            {
                var native = services.GetRequiredService<NativeRegistration>();
                valid &= ReferenceEquals(native.Handler, services.GetRequiredService<IA2ARequestHandler>());
            }
            if (identity.Scenario == 9)
            {
                valid &= services.GetRequiredService<IOptions<AgentHostOptions>>().Value.ShutdownTimeout == TimeSpan.FromSeconds(15);
                var health = await services.GetRequiredService<HealthCheckService>().CheckHealthAsync(cancellationToken);
                valid &= health.Entries.TryGetValue("application", out var entry) && entry.Status == HealthStatus.Healthy;
            }
            if (!valid) { throw new InvalidOperationException($"Scenario {identity.Scenario} registration did not match its contract."); }
            logger.LogInformation("A2A_SUITE_CONFIG_VERIFIED scenario={Scenario} source_sha={SourceSha} store={Store}",
                identity.Scenario, identity.SourceSha, store?.GetType().Name);
        }

        public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
    }
}
