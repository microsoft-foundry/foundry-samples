// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class TerminalLifecycleTests
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(3);

    private static VoiceConnectionState ActiveState()
    {
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        return state;
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task CallbackFaults_DoNotReleaseAnUndrainedOperation(bool sessionEnd)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var operation = new ResponseOperation("r_owned", "in_owned");
        state.TryReserveOperation(operation);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var notified = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        operation.Work = release.Task;
        using var registration = operation.Cancellation.Token.Register(() =>
        {
            notified.TrySetResult();
            throw new InvalidOperationException("controlled callback failure");
        });
        using var lifetimeRegistration = state.Lifetime.Token.Register(() =>
            throw new InvalidOperationException("controlled lifetime callback failure"));

        Task? terminating = null;
        try
        {
            if (sessionEnd) { terminating = coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall); }
            else { coordinator.CancelOperation(state, operation.ResponseId, ResponseOutcome.Cancelled); }
            await notified.Task.WaitAsync(Timeout);
            Assert.That(state.TryGetOperation(operation.ResponseId, out var retained), Is.True);
            Assert.That(retained, Is.SameAs(operation));
            Assert.That(operation.Work.IsCompleted, Is.False);
            // The token source must still be usable while the producer drains.
            Assert.That(operation.Cancellation.Token.IsCancellationRequested, Is.True);
        }
        finally
        {
            release.TrySetResult();
            if (terminating is not null) { await terminating.WaitAsync(Timeout); }
            await coordinator.DrainAsync().WaitAsync(Timeout);
        }
        Assert.That(state.TryGetOperation(operation.ResponseId, out _), Is.False);
        Assert.Throws<ObjectDisposedException>(() => _ = operation.Cancellation.Token);
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task CancelledProducer_CannotSendAfterAReplacement(bool cleanupError)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new CapturingVoiceSession();
        var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var closing = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        async IAsyncEnumerable<string> First([EnumeratorCancellation] CancellationToken token = default)
        {
            try
            {
                yield return "first";
                waiting.TrySetResult();
                try { await Task.Delay(System.Threading.Timeout.InfiniteTimeSpan, token); }
                catch (OperationCanceledException) { }
                if (!cleanupError) { yield return "STALE"; }
            }
            finally
            {
                closing.TrySetResult();
                await release.Task;
                if (cleanupError) { throw new InvalidOperationException("controlled cleanup failure"); }
            }
        }

        coordinator.StartResponse(session, state, "in_first", new ResponsePlan(First(), true, null));
        await waiting.Task.WaitAsync(Timeout);
        var oldId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        try
        {
            coordinator.CancelOperation(state, oldId, ResponseOutcome.Cancelled);
            await closing.Task.WaitAsync(Timeout);
            Assert.That(state.TryGetOperation(oldId, out _), Is.True);
            coordinator.StartResponse(session, state, "in_second", ResponsePlan.Fixed("second"));
            await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Any());
        }
        finally
        {
            release.TrySetResult();
            await coordinator.DrainAsync().WaitAsync(Timeout);
        }
        Assert.Multiple(() =>
        {
            Assert.That(session.Messages.OfType<VoiceResponseOutputTextDeltaMessage>()
                .Where(message => message.ResponseId == oldId).Select(message => message.Delta),
                Is.EqualTo(new[] { "first" }));
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>()
                .Any(message => message.ResponseId == oldId), Is.False);
            Assert.That(session.Messages.OfType<VoiceErrorMessage>(), Is.Empty);
            Assert.That(state.TryGetOperation(oldId, out _), Is.False);
        });
    }

    [Test]
    [TestCase(false)]
    [TestCase(true)]
    public async Task IteratorSetupFailure_IsOrderedAndAllowsNextInput(bool ownCancellation)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new CapturingVoiceSession();
        coordinator.StartResponse(session, state, "in_setup",
            new ResponsePlan(new FailingInitialization(ownCancellation), true, null));
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("retry"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.Select(message => message.GetType()), Is.EqualTo(new[]
        {
            typeof(VoiceResponseCreatedMessage), typeof(VoiceErrorMessage),
            typeof(VoiceResponseCreatedMessage), typeof(VoiceResponseOutputTextDoneMessage),
            typeof(VoiceResponseDoneMessage),
        }));
        Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>()
            .SelectMany(message => message.InReplyTo!), Is.EqualTo(new[] { "in_setup", "in_next" }));
    }

    private sealed class FailingInitialization(bool ownCancellation) : IAsyncEnumerable<string>
    {
        public IAsyncEnumerator<string> GetAsyncEnumerator(CancellationToken cancellationToken = default) =>
            throw (ownCancellation ? new OperationCanceledException() :
                new InvalidOperationException("controlled iterator setup failure"));
    }

    [Test]
    public async Task ProducerOwnCancellation_IsAnError_NotProtocolCancellation()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new CapturingVoiceSession();
        async IAsyncEnumerable<string> Source()
        {
            await Task.Yield();
            throw new OperationCanceledException("producer-local cancellation");
#pragma warning disable CS0162
            yield break;
#pragma warning restore CS0162
        }
        coordinator.StartResponse(session, state, "in_failure", new ResponsePlan(Source(), true, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceErrorMessage>().Single().Code, Is.EqualTo("generation_failed"));
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
        coordinator.StartResponse(session, state, "in_retry", ResponsePlan.Fixed("retry"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Count(), Is.EqualTo(1));
    }

    [Test]
    public async Task SessionBecomingInactive_PreventsQueuedCreatedEvenBeforeTokenCancellation()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        foreach (var selfCancel in new[] { false, true })
        {
            var state = ActiveState();
            var session = new CapturingVoiceSession();
            await state.GenerationGate.WaitAsync();
            if (selfCancel)
            {
                coordinator.StartSelfCancellingResponse(session, state, "in_queued", "queued", 0);
            }
            else
            {
                coordinator.StartResponse(session, state, "in_queued", ResponsePlan.Fixed("queued"));
            }
            // Deliberately keep cancellation notifications pending after marking the state inactive.
            state.TryBeginTermination(out _, out _);
            Assert.That(state.Lifetime.IsCancellationRequested, Is.False);
            state.GenerationGate.Release();
            await coordinator.DrainAsync().WaitAsync(Timeout);
            Assert.That(session.Messages, Is.Empty);
        }
    }

    [Test]
    public void PlaybackCache_EvictsInFifoOrderAcrossRepeatedOverflows()
    {
        var state = ActiveState();
        for (var index = 0; index < 80; index++)
        {
            var operation = new ResponseOperation($"r_{index}", $"in_{index}");
            Assert.That(state.TryReserveOperation(operation), Is.True);
            state.TryRemoveOperation(operation.ResponseId, out _);
            operation.Dispose();
        }
        for (var index = 0; index < 80; index++)
        {
            state.RecordHeardText($"r_{index}", "heard");
            Assert.That(state.TryGetHeardText($"r_{index}", out var heard), Is.EqualTo(index >= 16));
            if (index >= 16) { Assert.That(heard, Is.EqualTo("heard")); }
        }
    }

    [Test]
    public async Task DiScopeDisposal_JoinsCleanupAfterSessionEndReturned()
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton(new InvocationAdapter(new EchoHttpAgent()));
        services.AddVoice<ScopedAgent>();
        await using var provider = services.BuildServiceProvider();
        var scope = provider.CreateAsyncScope();
        var agent = (ScopedAgent)scope.ServiceProvider
            .GetRequiredService<Azure.AI.AgentServer.Invocations.InvocationWebSocketHandler>();
        var session = new CleanupSession();
        await agent.StartAsync(session);
        await agent.MessageAsync(session);
        await session.Started.Task.WaitAsync(Timeout);
        await agent.EndAsync(session).WaitAsync(Timeout);
        await session.Closing.Task.WaitAsync(Timeout);
        var disposal = scope.DisposeAsync().AsTask();
        try { Assert.That(disposal.IsCompleted, Is.False); }
        finally { session.Release.TrySetResult(); }
        await disposal.WaitAsync(Timeout);
        Assert.That(session.Finished, Is.True);
    }

    public sealed class ScopedAgent : VoiceAgent
    {
        public ScopedAgent(Microsoft.Extensions.Logging.ILogger<VoiceAgent> logger, InvocationAdapter backend)
            : base(logger, backend) { }

        public Task StartAsync(VoiceSession session) => OnSessionStartAsync(session,
            new VoiceSessionStartEvent("m_start", DateTimeOffset.UtcNow, "1.0", false,
                new VoiceResponseTimeouts(1000, 1000, 30000), null, null, null), CancellationToken.None);
        public Task MessageAsync(VoiceSession session) => OnUserMessageAsync(session,
            new VoiceUserMessageEvent("m_user", DateTimeOffset.UtcNow, "in_scope",
                new[] { new VoiceInputTextPart("hello") }), CancellationToken.None);
        public Task EndAsync(VoiceSession session) => OnSessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test"), CancellationToken.None);
    }

    private sealed class CleanupSession : CapturingVoiceSession
    {
        internal TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource Closing { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal bool Finished { get; private set; }
        public override async Task SendAsync(VoiceOutboundMessage message, CancellationToken cancellationToken = default)
        {
            if (message is VoiceResponseOutputTextDeltaMessage)
            {
                Started.TrySetResult();
                try { await Task.Delay(System.Threading.Timeout.InfiniteTimeSpan, cancellationToken); }
                finally
                {
                    Closing.TrySetResult();
                    await Release.Task;
                    Finished = true;
                }
            }
            await base.SendAsync(message, cancellationToken);
        }
    }

    [Test]
    public async Task BlockedEndCall_DoesNotDelayStopNotificationOrShutdown()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new BlockedEndCallSession();
        var operation = new ResponseOperation("r_worker", "in_worker");
        state.TryReserveOperation(operation);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        operation.Work = release.Task;
        var terminating = coordinator.TerminateAndEndCallAsync(
            session, state, VoiceEndCallMode.Drain, CancellationToken.None);
        coordinator.Observe(terminating);
        try
        {
            await session.Started.Task.WaitAsync(Timeout);
            Assert.That(state.IsActive, Is.False);
            Assert.That(operation.Cancellation.IsCancellationRequested, Is.True);
            Assert.That(terminating.IsCompleted, Is.False);
            await coordinator.StopAsync().WaitAsync(Timeout);
        }
        finally { release.TrySetResult(); }
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(terminating.IsCanceled, Is.True);
    }

    private sealed class BlockedEndCallSession : CapturingVoiceSession
    {
        internal TaskCompletionSource Started { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        public override async Task SendAsync(VoiceOutboundMessage message, CancellationToken cancellationToken = default)
        {
            if (message is VoiceEndCallMessage)
            {
                Started.TrySetResult();
                await Task.Delay(System.Threading.Timeout.InfiniteTimeSpan, cancellationToken);
            }
            await base.SendAsync(message, cancellationToken);
        }
    }


    [Test]
    public async Task CancelledQueuedCleanup_DoesNotBlockTheSuccessor_AndRetainsCapacity()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        var session = new CapturingVoiceSession();
        var source = new QueuedSource();
        await state.GenerationGate.WaitAsync();
        coordinator.StartResponse(session, state, "in_old", new ResponsePlan(source, true, null));
        state.TryGetResponseForInput("in_old", out var oldId);
        coordinator.CancelOperation(state, oldId, ResponseOutcome.Timeout);
        await source.Closing.Task.WaitAsync(Timeout);
        state.GenerationGate.Release();
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("next"));
        try
        {
            await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1 &&
                !state.TryGetResponseForInput("in_next", out _));
            Assert.That(state.TryGetOperation(oldId, out _), Is.True);
            Assert.That(source.Closed, Is.False);
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>()
                .SelectMany(message => message.InReplyTo!), Is.EqualTo(new[] { "in_next" }));
            // The old iterator still consumes a resource slot while cleanup is pending.
            var probes = Enumerable.Range(0, VoiceConnectionState.MaximumActiveResponses)
                .Select(index => new ResponseOperation($"r_probe_{index}", null)).ToArray();
            var admitted = probes.Count(operation => state.TryReserveOperation(operation));
            foreach (var probe in probes)
            {
                state.TryRemoveOperation(probe.ResponseId, out _);
                probe.Dispose();
            }
            Assert.That(admitted, Is.EqualTo(VoiceConnectionState.MaximumActiveResponses - 1));
        }
        finally
        {
            source.Release.TrySetResult();
            await coordinator.DrainAsync().WaitAsync(Timeout);
        }
        Assert.That(source.Closed, Is.True);
        Assert.That(state.TryGetResponseForInput("in_old", out _), Is.False);
        coordinator.StartResponse(session, state, "in_followup", ResponsePlan.Fixed("followup"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Count(), Is.EqualTo(2));
    }

    private sealed class QueuedSource : IAsyncEnumerable<string>, IAsyncEnumerator<string>
    {
        internal TaskCompletionSource Closing { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal bool Closed { get; private set; }
        public string Current => "unused";
        public IAsyncEnumerator<string> GetAsyncEnumerator(CancellationToken cancellationToken = default) => this;
        public ValueTask<bool> MoveNextAsync() => ValueTask.FromResult(false);
        public async ValueTask DisposeAsync()
        {
            Closing.TrySetResult();
            await Release.Task;
            Closed = true;
        }
    }

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        using var timeout = new CancellationTokenSource(Timeout);
        while (!condition()) { await Task.Delay(1, timeout.Token); }
    }
}
