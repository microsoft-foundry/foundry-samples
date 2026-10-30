// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text;
using System.Text.Json;
using Azure.AI.AgentServer.Invocations;
using Microsoft.AspNetCore.Http;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class InvocationAdapterTests
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(3);

    [TestCase("Hello world")]
    [TestCase("  你好 👋\n")]
    [TestCase("/end")]
    [TestCase(" \t ")]
    public async Task OriginalHttpHandler_EchoesVerbatimInProcess(string text)
    {
        var adapter = new InvocationAdapter(new EchoHttpAgent());
        Assert.That(await Collect(adapter, text).WaitAsync(Timeout), Is.EqualTo(text));
    }

    [TestCase("cjk")]
    [TestCase("emoji")]
    [TestCase("split-emoji")]
    public async Task UnicodeAtUtf16Budget_EchoesThroughBoundedSse(string scenario)
    {
        // .NET's 8,000-character budget counts UTF-16 code units, not Unicode scalars.
        var text = scenario switch
        {
            "cjk" => new string('界', 8_000),
            "emoji" => string.Concat(Enumerable.Repeat("👋", 4_000)),
            _ => string.Concat(Enumerable.Repeat("👋", 1_999)) + " " +
                string.Concat(Enumerable.Repeat("👋", 2_000)) + " ",
        };
        Assert.That(text.Length, Is.EqualTo(8_000));
        var adapter = new InvocationAdapter(new EchoHttpAgent());
        Assert.That(await Collect(adapter, text).WaitAsync(Timeout), Is.EqualTo(text));
    }

    [Test]
    public async Task FirstChunk_IsAvailableBeforeTheHandlerFinishes()
    {
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var handler = new CallbackHandler(async (request, response, context, token) =>
        {
            Assert.Multiple(() =>
            {
                Assert.That(request.Path.Value, Is.EqualTo("/invocations"));
                Assert.That(request.Method, Is.EqualTo("POST"));
                Assert.That(context.InvocationId, Is.EqualTo("in_test"));
                Assert.That(request.Headers.ContainsKey("Authorization"), Is.False);
            });
            response.ContentType = "text/event-stream";
            await Write(response, "token", "first", token);
            await release.Task.WaitAsync(token);
            await Write(response, "token", " second", token);
            await Write(response, "done", "first second", token);
        });
        await using var iterator = new InvocationAdapter(handler)
            .Stream(new CapturingVoiceSession(), "in_test", "input").GetAsyncEnumerator();
        Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.True);
        Assert.That(iterator.Current, Is.EqualTo("first"));
        Assert.That(release.Task.IsCompleted, Is.False);
        release.SetResult();
        Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.True);
        Assert.That(iterator.Current, Is.EqualTo(" second"));
        Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.False);
    }

    [Test]
    public async Task SplitUtf8CrlfAndMultilineSse_AreDecoded()
    {
        var raw = Encoding.UTF8.GetBytes(
            "data: {\"type\":\"token\",\r\ndata: \"content\":\"你好 👋\"}\r\n\r\n" +
            "data: {\"type\":\"done\",\"full_text\":\"你好 👋\"}\r\n\r\n");
        var handler = new CallbackHandler(async (_, response, _, token) =>
        {
            response.ContentType = "text/event-stream";
            foreach (var value in raw)
            {
                await response.Body.WriteAsync(new[] { value }, token);
                await response.Body.FlushAsync(token);
            }
        });
        Assert.That(await Collect(new InvocationAdapter(handler)).WaitAsync(Timeout), Is.EqualTo("你好 👋"));
    }

    [TestCase("data: {\"type\":\"token\",\"content\":\"hello\"}\n\n", typeof(InvalidOperationException))]
    [TestCase("data: not-json\n\n", typeof(JsonException))]
    [TestCase("data: {\"type\":\"token\"}", typeof(InvalidOperationException))]
    [TestCase("data: {\"type\":\"token\",\"content\":1}\n\n", typeof(InvalidOperationException))]
    [TestCase("data: {\"type\":\"token\",\"content\":\"\"}\n\n", typeof(InvalidOperationException))]
    [TestCase("data: {\"type\":\"done\",\"full_text\":\"wrong\"}\n\n", typeof(InvalidOperationException))]
    [TestCase("data: {\"type\":\"done\",\"full_text\":\"\"}\n\ndata: {}\n\n", typeof(InvalidOperationException))]
    [TestCase("data: {\"type\":\"unknown\"}\n\n", typeof(InvalidOperationException))]
    public void InvalidOrIncompleteSse_IsNotSuccess(string raw, Type exceptionType)
    {
        var handler = new CallbackHandler(async (_, response, _, token) =>
        {
            response.ContentType = "text/event-stream";
            await response.WriteAsync(raw, token);
        });
        var exception = Assert.CatchAsync(async () => await Collect(new InvocationAdapter(handler)).WaitAsync(Timeout));
        Assert.That(exception, Is.InstanceOf(exceptionType));
    }

    [TestCase(500, "text/event-stream")]
    [TestCase(200, "application/json")]
    public void FailedHttpResponse_IsNotSuccess(int status, string contentType)
    {
        var handler = new CallbackHandler((_, response, _, _) =>
        {
            response.StatusCode = status;
            response.ContentType = contentType;
            return Task.CompletedTask;
        });
        Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await Collect(new InvocationAdapter(handler)).WaitAsync(Timeout));
    }

    [Test]
    public async Task Completion_WaitsForTheHandlersFinalization()
    {
        var atDone = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finalized = false;
        var handler = new CallbackHandler(async (_, response, _, token) =>
        {
            response.ContentType = "text/event-stream";
            await Write(response, "token", "hello", token);
            await Write(response, "done", "hello", token);
            atDone.SetResult();
            await release.Task.WaitAsync(token);
            finalized = true;
        });
        var collecting = Collect(new InvocationAdapter(handler));
        await atDone.Task.WaitAsync(Timeout);
        Assert.That(collecting.IsCompleted, Is.False);
        release.SetResult();
        Assert.That(await collecting.WaitAsync(Timeout), Is.EqualTo("hello"));
        Assert.That(finalized, Is.True);
    }

    [Test]
    public void FinalSaveFailureAfterDone_IsNotSuccess()
    {
        var finalized = false;
        var handler = new CallbackHandler(async (_, response, _, token) =>
        {
            try
            {
                response.ContentType = "text/event-stream";
                await Write(response, "token", "hello", token);
                await Write(response, "done", "hello", token);
                throw new InvalidOperationException("Controlled finalization failure.");
            }
            finally
            {
                finalized = true;
            }
        });
        Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await Collect(new InvocationAdapter(handler)).WaitAsync(Timeout));
        Assert.That(finalized, Is.True);
    }

    [Test]
    public async Task DisposingTheStream_CancelsAndDrainsTheOriginalHandler()
    {
        var finalized = false;
        var handler = new CallbackHandler(async (request, response, _, token) =>
        {
            try
            {
                response.ContentType = "text/event-stream";
                await Write(response, "token", "first", token);
                await Task.Delay(System.Threading.Timeout.InfiniteTimeSpan, token);
            }
            finally
            {
                finalized = request.HttpContext.RequestAborted.IsCancellationRequested;
            }
        });
        var iterator = new InvocationAdapter(handler)
            .Stream(new CapturingVoiceSession(), "in_dispose", "input").GetAsyncEnumerator();
        Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.True);
        await iterator.DisposeAsync().AsTask().WaitAsync(Timeout);
        Assert.That(finalized, Is.True);
    }

    [TestCase(true)]
    [TestCase(false)]
    public void FrameAndOutputBudgets_AreBounded(bool oversizedFrame)
    {
        var handler = new CallbackHandler(async (_, response, _, token) =>
        {
            response.ContentType = "text/event-stream";
            if (oversizedFrame)
            {
                await response.WriteAsync("data: " + new string('x', 65_537), token);
            }
            else
            {
                await Write(response, "token", new string('x', 8_001), token);
            }
        });
        Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await Collect(new InvocationAdapter(handler)).WaitAsync(Timeout));
    }

    [Test]
    public async Task ConcurrentInvocations_DoNotShareEchoContent()
    {
        var adapter = new InvocationAdapter(new EchoHttpAgent());
        var results = await Task.WhenAll(Collect(adapter, "first customer"), Collect(adapter, "second customer"));
        Assert.That(results, Is.EqualTo(new[] { "first customer", "second customer" }));
    }

    private static async Task<string> Collect(InvocationAdapter adapter, string text = "input")
    {
        var output = new StringBuilder();
        await foreach (var chunk in adapter.Stream(new CapturingVoiceSession(), "in_test", text))
        {
            output.Append(chunk);
        }
        return output.ToString();
    }

    private static async Task Write(HttpResponse response, string type, string text, CancellationToken token)
    {
        var payload = type == "token"
            ? JsonSerializer.Serialize(new { type, content = text })
            : JsonSerializer.Serialize(new { type, full_text = text });
        await response.WriteAsync("data: " + payload + "\n\n", token);
        await response.Body.FlushAsync(token);
    }

    private sealed class CallbackHandler(
        Func<HttpRequest, HttpResponse, InvocationContext, CancellationToken, Task> callback) : InvocationHandler
    {
        public override Task HandleAsync(HttpRequest request, HttpResponse response,
            InvocationContext context, CancellationToken cancellationToken) =>
            callback(request, response, context, cancellationToken);
    }
}
