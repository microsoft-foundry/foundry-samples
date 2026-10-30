// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using EchoA2A;
using EchoClient;
using NUnit.Framework;

namespace EchoSample.Tests;

public class EchoTests
{
    [TestCase("Echo: hello")]
    [TestCase("Echo: first\nsecond\n")]
    [TestCase("Echo: first\r\nsecond\rlast")]
    [TestCase("Echo: caf\u00e9\n\u4e16\u754c\n\ud83d\ude80")]
    public void DemoChunksPreserveExactText(string text)
    {
        Assert.That(string.Concat(EchoAgent.BuildChunks(text)), Is.EqualTo(text));
    }

    [Test]
    public void DemoChunkCountIsBounded()
    {
        string text = "Echo: " + string.Join("\n", Enumerable.Range(0, 1000));
        var chunks = EchoAgent.BuildChunks(text);
        Assert.That(chunks.Count, Is.InRange(2, 16));
        Assert.That(string.Concat(chunks), Is.EqualTo(text));
    }

    [Test]
    public async Task ParserAcceptsMultilineSseAndComments()
    {
        using var reader = new StringReader(": keepalive\n\ndata: {\"jsonrpc\":\"2.0\",\ndata: \"result\":{\"ok\":true}}\n\n");
        var events = new List<JsonElement>();
        await foreach (var item in EchoValidation.ReadSseAsync(reader))
        {
            events.Add(item);
        }

        Assert.That(events, Has.Count.EqualTo(1));
        Assert.That(EchoValidation.Result(events[0]).GetProperty("ok").GetBoolean(), Is.True);
    }

    [Test]
    public void ParserRejectsTruncatedEvent()
    {
        Assert.ThrowsAsync<InvalidDataException>(async () =>
        {
            using var reader = new StringReader("data: {\"jsonrpc\":\"2.0\",\"result\":{}}\n");
            await foreach (var _ in EchoValidation.ReadSseAsync(reader)) { }
        });
    }

    [Test]
    public void ClientRejectsUnaryFallback() =>
        Assert.Throws<InvalidDataException>(() => EchoValidation.RequireSse("application/json"));

    [Test]
    public void ClientValidatesIncrementalArtifact()
    {
        var summary = EchoValidation.ValidateStream(Events(), "Echo: first\nsecond");
        Assert.That(summary.TaskId, Is.EqualTo("task-1"));
        Assert.That(summary.ArtifactId, Is.EqualTo("artifact-1"));
        Assert.That(summary.Chunks, Is.EqualTo(2));
    }

    [Test]
    public void ClientRejectsBufferedDelivery()
    {
        var events = Events().Select(item => item with { ReceivedMs = 1 }).ToArray();
        Assert.Throws<InvalidDataException>(() => EchoValidation.ValidateStream(events, "Echo: first\nsecond"));
    }

    [Test]
    public void ClientRejectsWrongAppendFlag()
    {
        var events = Events();
        events[1] = Artifact("second", append: false, last: true, milliseconds: 500);
        Assert.Throws<InvalidDataException>(() => EchoValidation.ValidateStream(events, "Echo: first\nsecond"));
    }

    [Test]
    public void ClientRejectsMissingCompletion()
    {
        Assert.Throws<InvalidDataException>(() => EchoValidation.ValidateStream(Events()[..2], "Echo: first\nsecond"));
    }

    [Test]
    public void ClientRejectsIncorrectOutput()
    {
        Assert.Throws<InvalidDataException>(() => EchoValidation.ValidateStream(Events(), "not the echo"));
    }

    [Test]
    public void ClientRejectsJsonRpcError()
    {
        var payload = JsonSerializer.SerializeToElement(new { jsonrpc = "2.0", error = new { code = -32603, message = "error" } });
        Assert.Throws<InvalidDataException>(() => EchoValidation.Result(payload));
    }

    [Test]
    public void ClientRejectsWrongResponseId()
    {
        var payload = JsonSerializer.SerializeToElement(new { jsonrpc = "2.0", id = "other", result = new { } });
        Assert.Throws<InvalidDataException>(() => EchoValidation.Result(payload, "request-1"));
    }

    [Test]
    public void ClientRejectsEventsAfterCompletion()
    {
        var events = Events().Concat(new[] { Artifact("extra", append: true, last: true, milliseconds: 600) }).ToArray();
        Assert.Throws<InvalidDataException>(() => EchoValidation.ValidateStream(events, "Echo: first\nsecond"));
    }

    private static ReceivedEvent[] Events() =>
    [
        Artifact("Echo: first\n", append: false, last: false, milliseconds: 0),
        Artifact("second", append: true, last: true, milliseconds: 500),
        new(501, JsonSerializer.SerializeToElement(new
        {
            jsonrpc = "2.0", result = new { statusUpdate = new { taskId = "task-1", status = new { state = "TASK_STATE_COMPLETED" } } },
        })),
    ];

    private static ReceivedEvent Artifact(string text, bool append, bool last, double milliseconds) => new(
        milliseconds, JsonSerializer.SerializeToElement(new
        {
            jsonrpc = "2.0", result = new
            {
                artifactUpdate = new
                {
                    taskId = "task-1", artifact = new { artifactId = "artifact-1", parts = new[] { new { text } } },
                    append, lastChunk = last,
                },
            },
        }));
}
