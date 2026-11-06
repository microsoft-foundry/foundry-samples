// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text;
using System.Text.Json;
using Azure.AI.AgentServer.Invocations;
using Microsoft.AspNetCore.Http;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class SseBoundaryTests
{
    private const int FrameBytes = 512 * 1024;
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(5);

    [TestCase("\n", false)]
    [TestCase("\r", false)]
    [TestCase("\r\n", false)]
    [TestCase("\n", true)]
    [TestCase("\r", true)]
    [TestCase("\r\n", true)]
    public async Task EverySplit_PreservesUtf8LinesAndOneLeadingBom(string ending, bool bom)
    {
        var raw = Encoding.UTF8.GetBytes(((bom ? "\uFEFF" : "") +
            ": comment\nunknown: ignored\ndata: {\"type\":\"token\",\n" +
            "data: \"content\":\" 你好 👋 \"}\n\n" + Event("done", " 你好 👋 "))
            .Replace("\n", ending, StringComparison.Ordinal));
        for (var split = -1; split <= raw.Length; split++)
        {
            using var stream = new FragmentedStream(raw, split);
            var events = await Parse(stream);
            Assert.That(events, Has.Count.EqualTo(2), $"split={split}");
            Assert.That(events[0].GetProperty("content").GetString(), Is.EqualTo(" 你好 👋 "));
        }
        Assert.That(await Collect(Encoding.UTF8.GetString(raw)), Is.EqualTo(" 你好 👋 "));
    }

    [TestCase("text/event-stream", true)]
    [TestCase("Text/Event-Stream; charset=utf-8", true)]
    [TestCase("TEXT/EVENT-STREAM; x=y", true)]
    [TestCase("text/event-stream-invalid", false)]
    [TestCase("text/event-stream+json", false)]
    [TestCase("application/json", false)]
    [TestCase("", false)]
    public async Task MediaType_UsesExactCaseInsensitiveToken(string mediaType, bool valid)
    {
        var body = Event("token", "x") + Event("done", "x");
        if (valid)
        {
            Assert.That(await Collect(body, mediaType), Is.EqualTo("x"));
        }
        else
        {
            Assert.ThrowsAsync<InvalidOperationException>(async () => await Collect(body, mediaType));
        }
        Assert.That(await Collect(body), Is.EqualTo("x"));
    }

    [TestCase(0, false)]
    [TestCase(1, false)]
    [TestCase(0, true)]
    [TestCase(1, true)]
    public async Task NormalizedUtf8EventBudget_IncludesComments(int extra, bool bom)
    {
        var body = (bom ? "\uFEFF" : "") + ":" + new string('x', FrameBytes - 3 + extra) +
            "\r\n\r\n" + Event("token", "x") + Event("done", "x");
        if (extra == 0)
        {
            Assert.That(await Collect(body), Is.EqualTo("x"));
        }
        else
        {
            Assert.ThrowsAsync<InvalidOperationException>(async () => await Collect(body));
        }
        Assert.That(await Collect(Event("token", "ok") + Event("done", "ok")), Is.EqualTo("ok"));
    }

    [Test]
    public async Task EightThousandTokenEvents_WorkInOneHandlerWrite()
    {
        var body = string.Concat(Enumerable.Repeat(Event("token", "x"), 8_000)) +
            Event("done", new string('x', 8_000));
        Assert.That(await Collect(body), Is.EqualTo(new string('x', 8_000)));
    }

    [Test]
    public async Task TrailingComment_DoesNotRequireAClosingBlankLine()
    {
        Assert.That(await Collect(Event("token", "x") + Event("done", "x") + ": trailing comment"),
            Is.EqualTo("x"));
        Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await Collect(Event("token", "x") + "data: {\"type\":\"done\",\"full_text\":\"x\"}"));
    }

    [TestCase("NaN")]
    [TestCase("Infinity")]
    public async Task NonFiniteJson_IsRejectedAndNextInvocationWorks(string number)
    {
        Assert.CatchAsync(async () => await Collect(
            "data: {\"type\":\"token\",\"content\":\"x\",\"extra\":" + number + "}\n\n" +
            Event("done", "x")));
        Assert.That(await Collect(Event("token", "ok") + Event("done", "ok")), Is.EqualTo("ok"));
    }

    [Test]
    public async Task InvalidAndTruncatedUtf8_AreRejected()
    {
        foreach (var tail in new[] { new byte[] { 0xFF }, new byte[] { 0xF0, 0x9F } })
        {
            using var stream = new MemoryStream(Encoding.UTF8.GetBytes("data: ").Concat(tail).ToArray());
            Assert.CatchAsync(async () => await Parse(stream));
        }
        Assert.That(await Collect(Event("token", "ok") + Event("done", "ok")), Is.EqualTo("ok"));
    }

    [Test]
    public void ReadyCommentStream_YieldsToControlBeforeOutput()
    {
        var previous = SynchronizationContext.Current;
        var context = new ManualContext();
        SynchronizationContext.SetSynchronizationContext(context);
        try
        {
            var controlRan = false;
            context.Post(_ => controlRan = true, null);
            using var stream = new MemoryStream(Encoding.UTF8.GetBytes(
                string.Concat(Enumerable.Repeat(": heartbeat\n\n", 4_096)) + Event("token", "x")));
            var parsing = Parse(stream, () => Assert.That(controlRan, Is.True));
            Assert.That(parsing.IsCompleted, Is.False);
            context.Drain();
            Assert.That(parsing.IsCompletedSuccessfully, Is.True);
            Assert.That(parsing.GetAwaiter().GetResult(), Has.Count.EqualTo(1));
        }
        finally
        {
            SynchronizationContext.SetSynchronizationContext(previous);
        }
    }

    private static async Task<List<JsonElement>> Parse(Stream stream, Action? onEvent = null)
    {
        var result = new List<JsonElement>();
        await foreach (var message in InvocationAdapter.ReadEventsAsync(stream, CancellationToken.None))
        {
            onEvent?.Invoke();
            result.Add(message);
        }
        return result;
    }

    private static string Event(string type, string text) => "data: " + (type == "token"
        ? JsonSerializer.Serialize(new { type, content = text })
        : JsonSerializer.Serialize(new { type, full_text = text })) + "\n\n";

    private static async Task<string> Collect(string body, string mediaType = "text/event-stream")
    {
        var handler = new RawHandler(body, mediaType);
        var result = new StringBuilder();
        using var timeout = new CancellationTokenSource(Timeout);
        await foreach (var chunk in new InvocationAdapter(handler)
            .Stream(new CapturingVoiceSession(), "in_sse", "input", timeout.Token))
        {
            result.Append(chunk);
        }
        return result.ToString();
    }

    private sealed class RawHandler(string body, string mediaType) : InvocationHandler
    {
        public override Task HandleAsync(HttpRequest request, HttpResponse response,
            InvocationContext context, CancellationToken cancellationToken)
        {
            response.ContentType = mediaType;
            return response.WriteAsync(body, cancellationToken);
        }
    }

    private sealed class FragmentedStream(byte[] bytes, int split) : MemoryStream(bytes)
    {
        public override ValueTask<int> ReadAsync(Memory<byte> buffer,
            CancellationToken cancellationToken = default)
        {
            var count = split == -1 ? 1 : Position < split ? split - Position : Length - Position;
            return base.ReadAsync(buffer[..(int)Math.Min(buffer.Length, count)], cancellationToken);
        }
    }

    private sealed class ManualContext : SynchronizationContext
    {
        private readonly Queue<Action> _callbacks = new();
        public override void Post(SendOrPostCallback callback, object? state) =>
            _callbacks.Enqueue(() => callback(state));
        internal void Drain()
        {
            while (_callbacks.TryDequeue(out var callback))
            {
                callback();
            }
        }
    }
}
