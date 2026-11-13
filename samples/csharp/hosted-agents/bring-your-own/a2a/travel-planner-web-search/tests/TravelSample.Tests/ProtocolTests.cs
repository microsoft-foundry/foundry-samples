// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using A2A;
using Azure.AI.AgentServer.A2A;
using Azure.AI.AgentServer.Core;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;
using TravelAgents;

namespace TravelSample.Tests;

[NonParallelizable]
public class ProtocolTests
{
    private readonly Dictionary<string, string?> _previous = [];
    private string _root = null!;

    [SetUp]
    public void SetUp()
    {
        foreach (string name in new[] { "AGENT_ROLE", "FOUNDRY_HOSTING_ENVIRONMENT", "FOUNDRY_PROJECT_ENDPOINT",
            "AGENTSERVER_STATE_ROOT", "FLIGHT_AGENT_ENDPOINT", "HOTEL_AGENT_ENDPOINT" })
            _previous[name] = Environment.GetEnvironmentVariable(name);
        _root = Path.Combine(Path.GetTempPath(), "travel-http-tests-" + Guid.NewGuid().ToString("N"));
        Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", _root);
        Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", "https://test.services.ai.azure.com/api/projects/test");
    }

    [TearDown]
    public void TearDown()
    {
        foreach (var pair in _previous) Environment.SetEnvironmentVariable(pair.Key, pair.Value);
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }

    [Test]
    public async Task PlannerDiscoversAndDelegatesToTwoNativeSpecialistsThenSaves()
    {
        await using var flights = await Host.StartAsync("flights", new OfflineRuntime());
        await using var hotels = await Host.StartAsync("hotels", new OfflineRuntime());
        Environment.SetEnvironmentVariable("FLIGHT_AGENT_ENDPOINT", flights.Endpoint);
        Environment.SetEnvironmentVariable("HOTEL_AGENT_ENDPOINT", hotels.Endpoint);
        await using var planner = await Host.StartAsync("planner", new OfflineRuntime());
        using var native = new A2AClient(new Uri(planner.Endpoint));
        var result = await native.SendMessageAsync(Request("research a trip"));
        Assert.That(result.Task, Is.Not.Null);
        Assert.That(result.Task!.Status.State, Is.EqualTo(TaskState.Completed));
        string answer = Text(result.Task, "answer");
        Assert.That(answer, Does.Contain("Flight Agent").And.Contain("Hotel Agent")
            .And.Contain("Verified saved plan").And.Contain("unverified"));
        using var calls = JsonDocument.Parse(Text(result.Task, "specialist-calls"));
        Assert.That(calls.RootElement.GetArrayLength(), Is.EqualTo(2));
        Assert.That(calls.RootElement.EnumerateArray().All(call => call.GetProperty("TaskId").GetString()!.Length > 0), Is.True);
        using var operations = JsonDocument.Parse(Text(result.Task, "trip-state"));
        Assert.That(operations.RootElement.EnumerateArray().Last().GetProperty("action").GetString(), Is.EqualTo("save"));
        var retrieved = await native.GetTaskAsync(new GetTaskRequest { Id = result.Task.Id });
        Assert.That(Text(retrieved, "answer"), Is.EqualTo(answer));
    }

    [Test]
    public async Task FailedSpecialistLeavesPlanPendingAndRetainsFailureReceipts()
    {
        await using var flights = await Host.StartAsync("flights", new OfflineRuntime(failSearch: true));
        await using var hotels = await Host.StartAsync("hotels", new OfflineRuntime());
        Environment.SetEnvironmentVariable("FLIGHT_AGENT_ENDPOINT", flights.Endpoint);
        Environment.SetEnvironmentVariable("HOTEL_AGENT_ENDPOINT", hotels.Endpoint);
        await using var planner = await Host.StartAsync("planner", new OfflineRuntime());
        using var native = new A2AClient(new Uri(planner.Endpoint));
        var response = await native.SendMessageAsync(Request("research a trip"));
        Assert.That(response.Task!.Status.State, Is.EqualTo(TaskState.Failed));
        using var operations = JsonDocument.Parse(Text(response.Task, "trip-state"));
        var receipts = operations.RootElement.EnumerateArray().ToArray();
        Assert.That(receipts[0].GetProperty("Status").GetString(), Is.EqualTo("needs-research"));
        Assert.That(receipts.Last().GetProperty("action").GetString(), Is.EqualTo("failed"));
        Assert.That(receipts.Any(receipt => receipt.GetProperty("action").GetString() == "save"), Is.False);
        Assert.That(response.Task.Artifacts!.Any(artifact => artifact.Name == "answer"), Is.False);
    }

    [Test]
    public async Task SourceLessSpecialistFailsTaskAndPreservesReceipt()
    {
        await using var specialist = await Host.StartAsync("flights", new OfflineRuntime(failSearch: true));
        using var native = new A2AClient(new Uri(specialist.Endpoint));
        var response = await native.SendMessageAsync(Request(JsonSerializer.Serialize(StorageTests.Requirements)));
        Assert.That(response.Task!.Status.State, Is.EqualTo(TaskState.Failed));
        Assert.That(Text(response.Task, "web-search"), Does.Contain("\"Success\":false"));
        Assert.That(response.Task.Artifacts!.Any(artifact => artifact.Name == "answer"), Is.False);
    }

    private static SendMessageRequest Request(string text) => new()
    {
        Message = new Message { MessageId = Guid.NewGuid().ToString(), Role = Role.User, Parts = [Part.FromText(text)] },
        Configuration = new SendMessageConfiguration { ReturnImmediately = false }
    };

    private static string Text(AgentTask task, string name) => string.Join("\n",
        task.Artifacts!.Where(artifact => artifact.Name == name).SelectMany(artifact => artifact.Parts).Select(part => part.Text));

    private sealed class OfflineRuntime(bool failSearch = false) : ResearchRuntime(NullLogger<ResearchRuntime>.Instance)
    {
        public override Task<ResearchAnswer> SearchAsync(string instructions, string prompt, string? callId, Activity? activity, CancellationToken cancellationToken)
        {
            if (failSearch) throw new ResearchException("Injected missing sources.", [new("search-1", false, [])]);
            return Task.FromResult(new ResearchAnswer("Unverified research https://airline.example/ https://hotel.example/",
                [new("search-1", true, ["https://airline.example/", "https://hotel.example/"])]));
        }

        public override async Task<string> AskAsync(string instructions, string prompt, ICollection<AIFunctionDeclaration> tools,
            string? callId, Activity? activity, CancellationToken cancellationToken)
        {
            async Task<object?> Invoke(string name, Dictionary<string, object?> args)
            {
                var function = tools.OfType<AIFunction>().Single(tool => tool.Name == name);
                return await function.InvokeAsync(new AIFunctionArguments(args), cancellationToken);
            }
            await Invoke("create_plan", new() { ["requirements"] = JsonSerializer.SerializeToElement(StorageTests.Requirements) });
            await Invoke("consult_agent_1", []);
            await Invoke("consult_agent_2", []);
            await Invoke("save_research", new() { ["answer"] = "Unverified https://airline.example/ https://hotel.example/" });
            return "Unverified https://airline.example/ https://hotel.example/";
        }
    }

    private sealed class Host(WebApplication app, string endpoint) : IAsyncDisposable
    {
        public string Endpoint { get; } = endpoint;

        public static async Task<Host> StartAsync(string role, ResearchRuntime runtime)
        {
            Environment.SetEnvironmentVariable("AGENT_ROLE", role);
            var builder = WebApplication.CreateBuilder();
            builder.WebHost.UseUrls("http://127.0.0.1:0");
            var card = TravelAgent.CreateCard(role, "http://127.0.0.1:0/a2a");
            builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
            builder.Services.AddFoundryA2A<TravelAgent>(card);
            builder.Services.AddSingleton(runtime);
            var app = builder.Build();
            try
            {
                app.MapFoundryA2A();
                await app.StartAsync();
                string address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
                app.Services.GetRequiredService<AgentCard>().SupportedInterfaces[0].Url = address + "/a2a";
                return new(app, address + "/a2a");
            }
            catch
            {
                await app.DisposeAsync();
                throw;
            }
        }

        public async ValueTask DisposeAsync()
        {
            try { await app.StopAsync(); }
            finally { await app.DisposeAsync(); }
        }
    }
}
