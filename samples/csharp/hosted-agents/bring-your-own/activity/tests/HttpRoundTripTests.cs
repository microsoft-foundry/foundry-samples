// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Channels;
using Azure.AI.AgentServer.Activity;
using CopilotSample;
using EchoSample;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;

namespace ActivitySamples.Tests;

[TestFixture]
public sealed class HttpRoundTripTests
{
    [Test]
    public async Task EchoRepliesThroughTheHttpConnectorAcrossTurns()
    {
        await using var host = await RoundTripHost.StartAsync(copilot: false);
        Assert.That(await host.SendAsync("  first HTTP turn  "), Is.EqualTo("Echo: first HTTP turn"));
        Assert.That(await host.SendAsync("second HTTP turn"), Is.EqualTo("Echo: second HTTP turn"));
    }

    [Test]
    [Category("Live")]
    public async Task CopilotUsesTheRealModelAndToolsThroughTheHttpConnector()
    {
        Assert.That(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT"), Is.Not.Null.And.Not.Empty);
        Assert.That(Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"), Is.Not.Null.And.Not.Empty);
        await using var host = await RoundTripHost.StartAsync(copilot: true);
        var reply = await host.SendAsync("Add a task titled HTTP-round-trip-check using add_task.");
        Assert.That(reply, Is.Not.Empty);
        var task = host.Store.List(host.ConversationId).Single();
        Assert.That(task.Title, Is.EqualTo("HTTP-round-trip-check"));

        var listing = await host.SendAsync("Show my tasks using list_tasks.");
        Assert.That(listing, Does.Contain("HTTP-round-trip-check").And.Contain("[ ]"));

        await host.SendAsync($"Mark task {task.Id} as done using complete_task.");
        Assert.That(host.Store.List(host.ConversationId).Single().Done, Is.True);
        var completed = await host.SendAsync("Show my tasks using list_tasks.");
        Assert.That(completed, Does.Contain("HTTP-round-trip-check").And.Contain("[x]"));
        TestContext.Progress.WriteLine("LIVE HTTP: Activity endpoint, M365 adapter, real Copilot model, resumed tools and outbound connector replies passed.");
    }

    private sealed class RoundTripHost : IAsyncDisposable
    {
        private readonly Channel<JsonElement> _replies = Channel.CreateUnbounded<JsonElement>();
        private readonly string _root = Path.Combine(Path.GetTempPath(), "activity-http-tests", Guid.NewGuid().ToString("N"));
        private readonly HttpClient _client = new() { Timeout = TimeSpan.FromMinutes(3) };
        private WebApplication? _connector;
        private WebApplication? _agent;

        public string ConversationId { get; } = "http-" + Guid.NewGuid().ToString("N");
        public TaskStore Store { get; private set; } = null!;

        public static async Task<RoundTripHost> StartAsync(bool copilot)
        {
            var host = new RoundTripHost();
            try
            {
                var connectorBuilder = WebApplication.CreateBuilder();
                connectorBuilder.WebHost.UseUrls("http://127.0.0.1:0");
                host._connector = connectorBuilder.Build();
                host._connector.MapPost("/v3/conversations/{conversationId}/activities/{activityId?}", async (HttpRequest request) =>
                {
                    var activity = await request.ReadFromJsonAsync<JsonElement>();
                    await host._replies.Writer.WriteAsync(activity);
                    return Results.Json(new { id = Guid.NewGuid().ToString("N") });
                });
                await host._connector.StartAsync();

                var builder = WebApplication.CreateBuilder();
                builder.WebHost.UseUrls("http://127.0.0.1:0");
                host.Store = new TaskStore(host._root);
                if (copilot)
                {
                    builder.Services.AddSingleton(host.Store);
                    builder.Services.AddHttpClient<FileTransfers>()
                        .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false });
                    builder.Services.AddSingleton<CopilotAssistant>();
                    builder.Services.AddSingleton<IAssistant>(services => services.GetRequiredService<CopilotAssistant>());
                    builder.Services.AddHostedService(services => services.GetRequiredService<CopilotAssistant>());
                    builder.AddAgent<CopilotAgent>();
                }
                else
                {
                    builder.AddAgent<EchoAgent>();
                }
                builder.AddFoundryActivity();
                host._agent = builder.Build();
                host._agent.MapFoundryActivity();
                await host._agent.StartAsync();
                host._client.BaseAddress = new Uri(host._agent.Urls.Single());
                using var ready = await host._client.GetAsync("/readiness");
                Assert.That(ready.StatusCode, Is.EqualTo(HttpStatusCode.OK));
                return host;
            }
            catch
            {
                await host.DisposeAsync();
                throw;
            }
        }

        public async Task<string> SendAsync(string text)
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
            using var response = await _client.PostAsJsonAsync("/activity/messages", new
            {
                type = "message",
                id = Guid.NewGuid().ToString("N"),
                text,
                from = new { id = "http-test-user" },
                recipient = new { id = "http-test-bot" },
                conversation = new { id = ConversationId },
                channelId = "emulator",
                serviceUrl = _connector!.Urls.Single() + "/"
            }, timeout.Token);
            Assert.That(response.StatusCode, Is.EqualTo(HttpStatusCode.Accepted),
                await response.Content.ReadAsStringAsync(timeout.Token));
            var reply = await _replies.Reader.ReadAsync(timeout.Token);
            Assert.That(reply.GetProperty("type").GetString(), Is.EqualTo("message"));
            return reply.GetProperty("text").GetString() ?? "";
        }

        public async ValueTask DisposeAsync()
        {
            _client.Dispose();
            if (_agent is not null)
            {
                await _agent.StopAsync();
                await _agent.DisposeAsync();
            }
            if (_connector is not null)
            {
                await _connector.StopAsync();
                await _connector.DisposeAsync();
            }
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
