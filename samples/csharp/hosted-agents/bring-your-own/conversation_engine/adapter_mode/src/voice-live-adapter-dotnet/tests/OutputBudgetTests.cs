// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Runtime.CompilerServices;
using System.Text;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class OutputBudgetTests
{
    private const int MaxBytes = 512 * 1024;
    private const int MaxChunks = 4096;
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(5);

    private static VoiceConnectionState ActiveState()
    {
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        return state;
    }

    private static async Task<(IReadOnlyList<VoiceOutboundMessage> Frames, int Consumed)> RunSource(
        string[] chunks, bool streaming)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new CapturingVoiceSession();
        var closed = false;
        var consumed = 0;
        async IAsyncEnumerable<string> Source([EnumeratorCancellation] CancellationToken token = default)
        {
            try
            {
                foreach (var chunk in chunks)
                {
                    token.ThrowIfCancellationRequested();
                    consumed++;
                    yield return chunk;
                    await Task.Yield();
                }
            }
            finally { closed = true; }
        }
        coordinator.StartResponse(session, state, "in_budget", new ResponsePlan(Source(), streaming, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(closed, Is.True);
        Assert.That(state.TryGetResponseForInput("in_budget", out _), Is.False);
        var frames = session.Messages;
        coordinator.StartResponse(session, state, "in_retry", ResponsePlan.Fixed("retry"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
        Assert.That(state.TryGetResponseForInput("in_retry", out _), Is.False);
        return (frames, consumed);
    }

    [TestCase(0, false)]
    [TestCase(0, true)]
    [TestCase(1, false)]
    [TestCase(1, true)]
    [TestCase(2, false)]
    [TestCase(2, true)]
    public async Task EmptyOutput_IsFailure(int emptyCount, bool streaming)
    {
        var (frames, _) = await RunSource(Enumerable.Repeat("", emptyCount).ToArray(), streaming);
        Assert.That(frames.Select(frame => frame.GetType()), Is.EqualTo(new[]
        {
            typeof(VoiceResponseCreatedMessage), typeof(VoiceErrorMessage),
        }));
        Assert.That(((VoiceErrorMessage)frames.Last()).Code, Is.EqualTo("generation_failed"));
    }

    [TestCase("x", false)]
    [TestCase("x", true)]
    [TestCase("💡", false)]
    [TestCase("💡", true)]
    public async Task SelfCancel_UsesTheSameTextBudget(string unit, bool over)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new CapturingVoiceSession();
        var maxUnits = 8000;
        var text = string.Concat(Enumerable.Repeat(unit, maxUnits + (over ? 1 : 0)));
        coordinator.StartSelfCancellingResponse(session, state, "in_self", text, 0);
        Assert.That(state.TryGetResponseForInput("in_self", out var responseId), Is.True);
        using var timeout = new CancellationTokenSource(Timeout);
        while (!session.Messages.Any(frame => frame is VoiceErrorMessage or VoiceResponseCancelMessage))
        {
            await Task.Delay(1, timeout.Token);
        }
        if (session.Messages.OfType<VoiceResponseCancelMessage>().Any())
        {
            coordinator.CancelOperation(state, responseId, ResponseOutcome.Cancelled);
        }
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseOutputTextDeltaMessage>().Select(frame => frame.Delta),
            Is.EqualTo(over ? Array.Empty<string>() : new[] { text }));
        Assert.That(session.Messages.OfType<VoiceErrorMessage>().Count(), Is.EqualTo(over ? 1 : 0));
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
        Assert.That(state.TryGetResponseForInput("in_self", out _), Is.False);
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("retry"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
    }

    [TestCase("answer", false)]
    [TestCase("answer", true)]
    [TestCase(" \t\n", false)]
    [TestCase(" \t\n", true)]
    public async Task EmptyChunks_DoNotCreateOutput_WhitespaceIsPreserved(string text, bool streaming)
    {
        var (frames, _) = await RunSource(new[] { "", text, "" }, streaming);
        Assert.That(frames.OfType<VoiceResponseOutputTextDoneMessage>().Single().Text, Is.EqualTo(text));
        Assert.That(frames.OfType<VoiceResponseOutputTextDeltaMessage>().Select(frame => frame.Delta),
            Is.EqualTo(streaming ? new[] { text } : Array.Empty<string>()));
        Assert.That(frames.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
        Assert.That(frames.OfType<VoiceErrorMessage>(), Is.Empty);
    }

    [Test]
    public async Task Adapter_StillAcceptsEightThousandSmallChunks()
    {
        var (frames, consumed) = await RunSource(Enumerable.Repeat("x", 8000).ToArray(), true);
        Assert.That(consumed, Is.EqualTo(8000));
        Assert.That(frames.OfType<VoiceErrorMessage>(), Is.Empty);
        Assert.That(frames.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
    }

    [Test]
    public async Task EmptySseDone_IsNotASuccessfulVoiceResponse()
    {
        var handler = new EmptySseHandler();
        var adapter = new InvocationAdapter(handler);
        var session = new CapturingVoiceSession();
        var state = ActiveState();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        coordinator.StartResponse(session, state, "in_empty",
            new ResponsePlan(adapter.Stream(session, "in_empty", "input"), true, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(handler.Finished, Is.True);
        Assert.That(session.Messages.Select(frame => frame.GetType()), Is.EqualTo(new[]
        {
            typeof(VoiceResponseCreatedMessage), typeof(VoiceErrorMessage),
        }));
        coordinator.StartResponse(session, state, "in_next",
            new ResponsePlan(new InvocationAdapter(new EchoHttpAgent()).Stream(session, "in_next", "retry"), true, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
    }

    private sealed class EmptySseHandler : Azure.AI.AgentServer.Invocations.InvocationHandler
    {
        internal bool Finished { get; private set; }
        public override async Task HandleAsync(
            Microsoft.AspNetCore.Http.HttpRequest request, Microsoft.AspNetCore.Http.HttpResponse response,
            Azure.AI.AgentServer.Invocations.InvocationContext context, CancellationToken cancellationToken)
        {
            response.ContentType = "text/event-stream";
            await response.Body.WriteAsync(
                Encoding.UTF8.GetBytes("data: {\"type\":\"done\",\"full_text\":\"\"}\n\n"), cancellationToken);
            Finished = true;
        }
    }
}
