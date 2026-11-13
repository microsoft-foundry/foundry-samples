// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Azure.AI.AgentServer.A2A;
using EchoA2A;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;

namespace EchoSample.Tests;

public class HttpTests
{
    [Test]
    public async Task NativeAlphaHostCompletesAndRetrievesExactEchoTask()
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
        builder.Services.AddFoundryA2A<EchoAgent>(EchoAgent.CreateCard("http://localhost/a2a"));
        await using var app = builder.Build();
        app.MapFoundryA2A();
        await app.StartAsync();
        using var http = app.GetTestClient();
        using var native = new A2AClient(new Uri("http://localhost/a2a"), http);
        var response = await native.SendMessageAsync(new SendMessageRequest
        {
            Message = new Message { Role = Role.User, MessageId = Guid.NewGuid().ToString(), Parts = [Part.FromText("hello")] },
            Configuration = new SendMessageConfiguration { ReturnImmediately = false }
        });
        Assert.That(response.Task!.Status.State, Is.EqualTo(TaskState.Completed));
        Assert.That(response.Task.Artifacts!.Single().Parts.Single().Text, Is.EqualTo("Echo: hello"));
        var stored = await native.GetTaskAsync(new GetTaskRequest { Id = response.Task.Id });
        Assert.That(stored.Artifacts!.Single().Parts.Single().Text, Is.EqualTo("Echo: hello"));
        await app.StopAsync();
    }
}
