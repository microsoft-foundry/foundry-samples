// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class GenerationSerializationTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [TestCase(false)]
    [TestCase(true)]
    public async Task Reply_WaitsForPreviousProtocolCompletion(bool proactive)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new WireSession();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        ResponseOperation first;
        if (proactive)
        {
            Assert.That(state.TryReserveProactive("r_proactive",
                new ResponsePlan(First(), true, null), out _), Is.True);
            session.ExternalOpen("r_proactive");
            await coordinator.AcceptProactiveAsync(session, state, "r_proactive");
            Assert.That(state.TryGetOperation("r_proactive", out first!), Is.True);
        }
        else
        {
            coordinator.SendEcho(session, state, "in_first", First(), Stopwatch.GetTimestamp());
            Assert.That(state.TryGetResponseForInput("in_first", out var id), Is.True);
            Assert.That(state.TryGetOperation(id, out first!), Is.True);
        }
        await started.Task.WaitAsync(Limit);
        coordinator.SendEcho(session, state, "in_second", Second(), Stopwatch.GetTimestamp());
        Assert.That(state.TryGetResponseForInput("in_second", out var secondId), Is.True);
        Assert.That(state.TryGetOperation(secondId, out var second), Is.True);
        try
        {
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>().Count(),
                Is.EqualTo(proactive ? 0 : 1));
            Assert.That(second.Work!.IsCompleted, Is.False);
        }
        finally
        {
            release.TrySetResult();
            await Task.WhenAll(first.Work!, second.Work!).WaitAsync(Limit);
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }
        Assert.That(session.Violations, Is.Empty);
        var decisions = session.Messages.Where(message =>
            message is VoiceResponseCreatedMessage or VoiceResponseDoneMessage).ToArray();
        Assert.That(decisions.Length, Is.EqualTo(proactive ? 3 : 4));
        Assert.That(decisions[proactive ? 0 : 1], Is.TypeOf<VoiceResponseDoneMessage>());

        async IAsyncEnumerable<string> First()
        {
            yield return "first";
            started.TrySetResult();
            await release.Task;
        }
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task WinningTerminal_ReleasesGenerationBeforeSlowProducerCleanup(bool timeout)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new WireSession();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanupStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseCleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        coordinator.SendEcho(session, state, "in_first", First(), Stopwatch.GetTimestamp());
        await started.Task.WaitAsync(Limit);
        Assert.That(state.TryGetResponseForInput("in_first", out var firstId), Is.True);
        Assert.That(state.TryGetOperation(firstId, out var first), Is.True);
        coordinator.SendEcho(session, state, "in_second", Second(), Stopwatch.GetTimestamp());
        Assert.That(state.TryGetResponseForInput("in_second", out var secondId), Is.True);
        Assert.That(state.TryGetOperation(secondId, out var second), Is.True);
        try
        {
            session.ExternalTerminal();
            coordinator.CancelOperation(state, firstId,
                timeout ? ResponseOutcome.Timeout : ResponseOutcome.Cancelled);
            await cleanupStarted.Task.WaitAsync(Limit);
            await second.Work!.WaitAsync(Limit);
            Assert.That(first.Work!.IsCompleted, Is.False);
            Assert.That(state.TryGetOperation(firstId, out _), Is.True);
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Single().ResponseId,
                Is.EqualTo(secondId));
            Assert.That(session.Violations, Is.Empty);
        }
        finally
        {
            releaseCleanup.TrySetResult();
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }

        async IAsyncEnumerable<string> First([EnumeratorCancellation] CancellationToken token = default)
        {
            try
            {
                yield return "first";
                started.TrySetResult();
                await Task.Delay(Timeout.Infinite, token);
            }
            finally
            {
                cleanupStarted.TrySetResult();
                await releaseCleanup.Task;
            }
        }
    }

    [Test]
    public async Task SelfCancel_HoldsGenerationUntilWinningAcknowledgment()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new WireSession();
        coordinator.StartSelfCancellingResponse(session, state, "in_self", "first", Stopwatch.GetTimestamp());
        Assert.That(state.TryGetResponseForInput("in_self", out var firstId), Is.True);
        Assert.That(state.TryGetOperation(firstId, out var first), Is.True);
        await first.Work!.WaitAsync(Limit); // Sending the request is not its terminal acknowledgment.
        coordinator.SendEcho(session, state, "in_second", Second(), Stopwatch.GetTimestamp());
        Assert.That(state.TryGetResponseForInput("in_second", out var secondId), Is.True);
        Assert.That(state.TryGetOperation(secondId, out var second), Is.True);
        try
        {
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>().Count(), Is.EqualTo(1));
            session.ExternalTerminal();
            coordinator.CancelOperation(state, firstId, ResponseOutcome.Cancelled);
            await second.Work!.WaitAsync(Limit);
            Assert.That(session.Violations, Is.Empty);
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Single().ResponseId,
                Is.EqualTo(secondId));
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task ProducerCancellation_FailsBeforeTheNextGeneration(bool afterOutput)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new WireSession();
        var closed = false;
        coordinator.SendEcho(session, state, "in_first", First(), Stopwatch.GetTimestamp());
        Assert.That(state.TryGetResponseForInput("in_first", out var firstId), Is.True);
        Assert.That(state.TryGetOperation(firstId, out var first), Is.True);
        coordinator.SendEcho(session, state, "in_second", Second(), Stopwatch.GetTimestamp());
        Assert.That(state.TryGetResponseForInput("in_second", out var secondId), Is.True);
        Assert.That(state.TryGetOperation(secondId, out var second), Is.True);
        try
        {
            await Task.WhenAll(first.Work!, second.Work!).WaitAsync(Limit);
            Assert.That(closed, Is.True);
            Assert.That(session.Violations, Is.Empty);
            var decisions = session.Messages.Where(message =>
                message is VoiceResponseCreatedMessage or VoiceErrorMessage or VoiceResponseDoneMessage);
            Assert.That(decisions.Select(message => message.GetType()), Is.EqualTo(new[]
            {
                typeof(VoiceResponseCreatedMessage), typeof(VoiceErrorMessage),
                typeof(VoiceResponseCreatedMessage), typeof(VoiceResponseDoneMessage),
            }));
            var error = session.Messages.OfType<VoiceErrorMessage>().Single();
            Assert.That(error.ResponseId, Is.EqualTo(firstId));
            Assert.That(error.Code, Is.EqualTo("generation_failed"));
            Assert.That(error.Message, Is.EqualTo("The response could not be generated."));
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Single().ResponseId,
                Is.EqualTo(secondId));
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }

        async IAsyncEnumerable<string> First()
        {
            try
            {
                if (afterOutput) { yield return "first"; }
                await Task.FromCanceled(new CancellationToken(canceled: true));
            }
            finally
            {
                closed = true;
            }
        }
    }

    private static VoiceConnectionState ActiveState()
    {
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        return state;
    }

    private static async IAsyncEnumerable<string> Second()
    {
        await Task.Yield();
        yield return "second";
    }

    private sealed class WireSession : CapturingVoiceSession
    {
        private readonly object _sync = new();
        private string? _open;
        internal List<string> Violations { get; } = [];

        internal void ExternalOpen(string responseId) { lock (_sync) { _open = responseId; } }
        internal void ExternalTerminal() { lock (_sync) { _open = null; } }

        public override Task SendAsync(VoiceOutboundMessage message, CancellationToken token = default)
        {
            token.ThrowIfCancellationRequested();
            lock (_sync)
            {
                if (message is VoiceResponseCreatedMessage created)
                {
                    if (_open is not null) { Violations.Add("response_created_while_open"); }
                    _open = created.ResponseId;
                }
                else if (message is VoiceResponseDoneMessage done)
                {
                    if (_open != done.ResponseId) { Violations.Add("unbound_terminal"); }
                    _open = null;
                }
                else if (message is VoiceErrorMessage error)
                {
                    if (_open != error.ResponseId) { Violations.Add("unbound_terminal"); }
                    _open = null;
                }
                return base.SendAsync(message, token);
            }
        }
    }
}
