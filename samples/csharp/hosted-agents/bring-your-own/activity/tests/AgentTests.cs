// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text;
using System.Text.Json;
using CopilotSample;
using EchoSample;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Builder.Testing;
using Microsoft.Agents.Core.Models;
using Microsoft.Agents.Storage;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace ActivitySamples.Tests;

[TestFixture]
public sealed class AgentTests
{
    private string _root = null!;
    private TaskStore _store = null!;
    private HttpClient _http = null!;

    [SetUp]
    public void SetUp()
    {
        _root = Path.Combine(Path.GetTempPath(), "activity-agent-tests", Guid.NewGuid().ToString("N"));
        _store = new TaskStore(_root);
        _http = new HttpClient(new StubHttpHandler());
    }

    [TearDown]
    public void TearDown()
    {
        _http.Dispose();
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [Test]
    public async Task EchoUsesActualSampleHandlerAndPreservesTurnOrder()
    {
        await using var host = AgentTestHost.Create(builder =>
        {
            builder.Services.AddTransient<IAgent>(_ =>
                new EchoAgent(new AgentApplicationOptions(new MemoryStorage()), NullLogger<EchoAgent>.Instance));
        });
        await host.CreateTestFlow()
            .Send("  hello  ").AssertReply("Echo: hello")
            .Send("second turn").AssertReply("Echo: second turn")
            .StartTestAsync();
    }

    [Test]
    public async Task EchoWelcomesMemberButNotTheBot()
    {
        await using var host = AgentTestHost.Create(builder =>
        {
            builder.Services.AddTransient<IAgent>(_ =>
                new EchoAgent(new AgentApplicationOptions(new MemoryStorage()), NullLogger<EchoAgent>.Instance));
        });
        await host.CreateTestFlow()
            .Send(new Activity
            {
                Type = ActivityTypes.ConversationUpdate,
                Recipient = new ChannelAccount { Id = "bot" },
                MembersAdded = [new ChannelAccount { Id = "user" }, new ChannelAccount { Id = "bot" }]
            })
            .AssertReply("Welcome! Send a message and I'll echo it back.")
            .StartTestAsync();
        Assert.That(host.Adapter.GetNextReply(), Is.Null, "The bot itself must not receive a welcome.");
    }

    [Test]
    public async Task CopilotDeliversAccumulatedTextOnNonStreamingChannels()
    {
        await using var host = CopilotHost(new StubAssistant());
        await host.CreateTestFlow()
            .Send("hello").AssertReply("Hello from Copilot.")
            .StartTestAsync();
    }

    [Test]
    public async Task CopilotProvidesTextTaskListOutsideTeams()
    {
        await using var host = CopilotHost(new StubAssistant(_store));
        await host.CreateTestFlow().Send("show tasks")
            .AssertReply(activity =>
            {
                Assert.That(activity.Text, Does.Contain("Buy milk"));
                Assert.That(activity.Attachments ?? [], Is.Empty);
            }).StartTestAsync();
    }

    [Test]
    public async Task CopilotReportsModelErrorsWithoutLeakingDetails()
    {
        await using var host = CopilotHost(new FailingAssistant());
        Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await host.CreateTestFlow().Send("hello").StartTestAsync());
        var reply = await host.Adapter.GetNextReplyAsync();
        Assert.That(reply.Text, Is.EqualTo("Sorry, I couldn't complete that request. Please try again."));
    }

    [Test]
    public async Task TeamsReplyIncludesTaskCardAndFinishesStream()
    {
        await using var host = CopilotHost(new StubAssistant(_store));
        await host.CreateTestFlow().Send(new Activity
        {
            Type = ActivityTypes.Message, Text = "show tasks", ChannelId = "msteams",
            Conversation = new ConversationAccount { Id = "teams-conversation", ConversationType = "personal" }
        }).StartTestAsync();
        var replies = new List<IActivity>();
        IActivity? reply;
        while ((reply = host.Adapter.GetNextReply()) is not null)
        {
            replies.Add(reply);
        }
        Assert.That(replies.Any(activity => activity.Text?.Contains("Hello from Copilot.") == true), Is.True);
        Assert.That(replies.SelectMany(activity => activity.Attachments ?? [])
            .Any(attachment => attachment.ContentType == TaskCards.ContentType), Is.True);
    }

    [Test]
    public async Task CardActionsUpdateTheActualStoreAndReturnRefreshedCard()
    {
        await using var host = CopilotHost(new StubAssistant());
        await host.CreateTestFlow().Send(new Activity
        {
            Type = ActivityTypes.Invoke, Name = "adaptiveCard/action",
            Value = new { action = new { verb = "add_task", data = new { newTask = "Test card task" } } }
        }).AssertReply(activity =>
        {
            Assert.That(activity.Type, Is.EqualTo(ActivityTypes.InvokeResponse));
            var response = JsonSerializer.SerializeToElement(activity.Value);
            Assert.That(response.GetProperty("Status").GetInt32(), Is.EqualTo(200));
            Assert.That(response.ToString(), Does.Contain("Test card task").And.Contain("AdaptiveCard"));
        }).StartTestAsync();
    }

    [TestCase("")]
    [TestCase(" \t\r\n")]
    [TestCase(null)]
    public async Task EmptyCardTaskTitlesReturnBadRequestWithoutChangingTasks(string? title)
    {
        await AssertInvalidCardTaskAsync(new { newTask = title });
    }

    [Test]
    public async Task MissingCardTaskTitleReturnsBadRequestWithoutChangingTasks()
    {
        await AssertInvalidCardTaskAsync(new { });
    }

    [TestCase("complete_task")]
    [TestCase("delete_task")]
    public async Task StaleTaskCardReturnsActionableErrorWithoutChangingTasks(string verb)
    {
        const string conversationId = "stale-card";
        var existing = _store.Add(conversationId, "Keep this task");
        var deleted = _store.Add(conversationId, "Deleted task");
        _store.Delete(conversationId, deleted.Id);
        await using var host = CopilotHost(new StubAssistant());
        await host.CreateTestFlow().Send(new Activity
        {
            Type = ActivityTypes.Invoke, Name = "adaptiveCard/action",
            Conversation = new ConversationAccount { Id = conversationId },
            Value = new { action = new { verb, data = new { taskId = deleted.Id } } }
        }).AssertReply(activity =>
        {
            Assert.That(activity.Type, Is.EqualTo(ActivityTypes.InvokeResponse));
            var response = JsonSerializer.SerializeToElement(activity.Value);
            Assert.That(response.GetProperty("Status").GetInt32(), Is.EqualTo(200));
            var body = response.GetProperty("Body");
            Assert.That(body.GetProperty("statusCode").GetInt32(), Is.EqualTo(400));
            Assert.That(body.GetProperty("value").GetProperty("message").GetString(),
                Is.EqualTo("This task is no longer available. Select Refresh to update the task board."));
        }).StartTestAsync();
        Assert.That(_store.List(conversationId), Is.EqualTo(new[] { existing }));
        Assert.That(host.Adapter.GetNextReply(), Is.Null);
    }

    private async Task AssertInvalidCardTaskAsync(object data)
    {
        const string conversationId = "card-validation";
        var existing = _store.Add(conversationId, "Keep this task");
        await using var host = CopilotHost(new StubAssistant());
        await host.CreateTestFlow().Send(new Activity
        {
            Type = ActivityTypes.Invoke, Name = "adaptiveCard/action",
            Conversation = new ConversationAccount { Id = conversationId },
            Value = new { action = new { verb = "add_task", data } }
        }).AssertReply(activity =>
        {
            Assert.That(activity.Type, Is.EqualTo(ActivityTypes.InvokeResponse));
            var response = JsonSerializer.SerializeToElement(activity.Value);
            Assert.That(response.GetProperty("Status").GetInt32(), Is.EqualTo(200));
            var body = response.GetProperty("Body");
            Assert.That(body.GetProperty("statusCode").GetInt32(), Is.EqualTo(400));
            Assert.That(body.GetProperty("type").GetString(), Is.EqualTo("application/vnd.microsoft.error"));
            Assert.That(body.GetProperty("value").GetProperty("code").GetString(), Is.EqualTo("BadRequest"));
            Assert.That(body.GetProperty("value").GetProperty("message").GetString(),
                Is.EqualTo("Enter a task title before selecting Add."));
        }).StartTestAsync();
        Assert.That(_store.List(conversationId), Is.EqualTo(new[] { existing }));
        Assert.That(host.Adapter.GetNextReply(), Is.Null, "Validation must not trigger the generic turn-error reply.");
    }

    [TestCase(null, "Main reply", true)]
    [TestCase("", "Main reply", true)]
    [TestCase("subagent-1", "Delegated reply", false)]
    [TestCase(null, "", false)]
    [TestCase(null, null, false)]
    public void OnlyRootAssistantDeltasAreForwarded(string? agentId, string? content, bool expected)
    {
        var ev = GitHub.Copilot.SessionEvent.FromJson(JsonSerializer.Serialize(new
        {
            type = "assistant.message_delta",
            id = Guid.NewGuid().ToString(),
            timestamp = DateTimeOffset.UtcNow,
            parentId = (string?)null,
            agentId,
            data = new { messageId = "test-message", deltaContent = content }
        }));
        var chunks = new List<string>();
        var streamed = CopilotAssistant.TryForwardRootAssistantDelta(ev, chunks.Add);
        Assert.That(streamed, Is.EqualTo(expected));
        Assert.That(chunks, Is.EqualTo(expected ? new[] { content } : Array.Empty<string>()));
    }

    private AgentTestHost CopilotHost(IAssistant assistant) => AgentTestHost.Create(builder =>
    {
        builder.Services.AddTransient<IAgent>(_ => new CopilotAgent(
            new AgentApplicationOptions(new MemoryStorage()), assistant, _store,
            new FileTransfers(_http, _store), NullLogger<CopilotAgent>.Instance));
    });

    private sealed class StubAssistant(TaskStore? store = null) : IAssistant
    {
        public Task<AssistantResult> ReplyAsync(string conversationId, string prompt, IList<GitHub.Copilot.Attachment> attachments,
            Action<string> onText, Action<string> onProgress, CancellationToken cancellationToken)
        {
            onProgress("Working...");
            onText("Hello from ");
            onText("Copilot.");
            store?.Add(conversationId, "Buy milk");
            return Task.FromResult(new AssistantResult(store is not null, []));
        }
    }

    private sealed class FailingAssistant : IAssistant
    {
        public Task<AssistantResult> ReplyAsync(string conversationId, string prompt, IList<GitHub.Copilot.Attachment> attachments,
            Action<string> onText, Action<string> onProgress, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("sensitive provider diagnostic");
    }

    private sealed class StubHttpHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("shared text") });
    }
}
