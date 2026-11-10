// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Net.Http.Json;
using Azure.AI.AgentServer.Activity;
using Azure.AI.AgentServer.Core;
using CopilotSample;
using EchoSample;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;

namespace ActivitySamples.Tests;

[TestFixture]
public sealed class HostingTests
{
    [TestCase(false)]
    [TestCase(true)]
    public async Task ActualAgentsExposeReadinessAndAcceptActivities(bool copilot)
    {
        var root = Path.Combine(Path.GetTempPath(), "activity-host-tests", Guid.NewGuid().ToString("N"));
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        if (copilot)
        {
            builder.Services.AddSingleton(new TaskStore(root));
            builder.Services.AddSingleton<IAssistant, NoReplyAssistant>();
            builder.Services.AddHttpClient<FileTransfers>();
            builder.AddAgent<CopilotAgent>();
        }
        else
        {
            builder.AddAgent<EchoAgent>();
        }
        builder.AddFoundryActivity();
        await using var app = builder.Build();
        app.MapFoundryActivity();
        await app.StartAsync();
        try
        {
            var http = app.GetTestClient();
            using var readiness = await http.GetAsync("/readiness");
            Assert.That(readiness.StatusCode, Is.EqualTo(HttpStatusCode.OK));
            using var accepted = await http.PostAsJsonAsync("/activity/messages", new
            {
                type = "message", id = "test-activity", text = " ",
                from = new { id = "user" }, recipient = new { id = "bot" },
                conversation = new { id = "conversation" }, channelId = "test",
                serviceUrl = "http://localhost:1"
            });
            Assert.That(accepted.StatusCode, Is.EqualTo(HttpStatusCode.Accepted));
            Assert.That(accepted.Headers.Contains(PlatformHeaders.SessionId), Is.True);
            using var legacy = await http.PostAsJsonAsync("/api/messages", new { type = "message" });
            Assert.That(legacy.StatusCode, Is.EqualTo(HttpStatusCode.NotFound));
        }
        finally
        {
            await app.StopAsync();
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    private sealed class NoReplyAssistant : IAssistant
    {
        public Task<AssistantResult> ReplyAsync(string conversationId, string prompt, IList<GitHub.Copilot.Attachment> attachments,
            Action<string> onText, Action<string> onProgress, CancellationToken cancellationToken) =>
            throw new AssertionException("An empty message must not invoke the model.");
    }
}
