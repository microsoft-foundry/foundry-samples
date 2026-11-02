// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class AdversarialTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [Test]
    public async Task DeclinesAreBoundedAndDrainOnTermination()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new BlockingDeclineSession();
        var sends = new List<Task>();
        try
        {
            for (var index = 0; index < VoiceConnectionState.MaximumPendingDeclines; index++)
            {
                sends.Add(coordinator.SendNoneAsync(session, state, $"in_{index}", "empty_input"));
            }
            await session.Started.Task.WaitAsync(Limit);
            Assert.Throws<InvalidOperationException>(() =>
                coordinator.SendNoneAsync(session, state, "in_overflow", "empty_input"));
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
            await Task.WhenAll(sends).WaitAsync(Limit);
            Assert.That(session.Messages, Is.Empty);
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.Cancelled).WaitAsync(Limit);
        }
    }

    private sealed class BlockingDeclineSession : CapturingVoiceSession
    {
        internal TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public override async Task SendAsync(VoiceOutboundMessage message, CancellationToken cancellationToken = default)
        {
            if (message is VoiceResponseNoneMessage)
            {
                Started.TrySetResult();
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            }
            await base.SendAsync(message, cancellationToken);
        }
    }

    [Test]
    public async Task CustomerExceptionContentIsNotLogged()
    {
        const string marker = "SYNTHETIC_PRIVATE_INPUT_DO_NOT_LOG";
        var logger = new CaptureLogger();
        var coordinator = new VoiceResponseCoordinator(logger);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new CapturingVoiceSession();
        async IAsyncEnumerable<string> FailingSource()
        {
            await Task.FromException(new InvalidOperationException(marker));
            yield break;
        }
        try
        {
            coordinator.SendEcho(session, state, "in_log", FailingSource(), Stopwatch.GetTimestamp());
            using var timeout = new CancellationTokenSource(Limit);
            while (logger.Lines.IsEmpty) { await Task.Delay(5, timeout.Token); }
            Assert.That(string.Join("\n", logger.Lines), Does.Not.Contain(marker));
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.Cancelled).WaitAsync(Limit);
        }
    }

    private sealed class CaptureLogger : ILogger<VoiceAgent>
    {
        internal System.Collections.Concurrent.ConcurrentQueue<string> Lines { get; } = new();
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel level) => true;
        public void Log<TState>(LogLevel level, EventId eventId, TState state,
            Exception? exception, Func<TState, Exception?, string> formatter) =>
            Lines.Enqueue(formatter(state, exception) + "\n" + exception);
    }

    [Test]
    public async Task SessionTerminationWaitsForPreviouslyCancelledWork()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanupEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseCleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanupFinished = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        async IAsyncEnumerable<string> Source([EnumeratorCancellation] CancellationToken token = default)
        {
            try
            {
                yield return "first";
                started.TrySetResult();
                await Task.Delay(Timeout.InfiniteTimeSpan, token);
            }
            finally
            {
                cleanupEntered.TrySetResult();
                await releaseCleanup.Task;
                cleanupFinished.TrySetResult();
            }
        }
        coordinator.SendEcho(new CapturingVoiceSession(), state, "in_cancelled", Source(), Stopwatch.GetTimestamp());
        await started.Task.WaitAsync(Limit);
        Assert.That(state.TryGetResponseForInput("in_cancelled", out var responseId), Is.True);
        coordinator.CancelOperation(state, responseId, ResponseOutcome.Cancelled);
        await cleanupEntered.Task.WaitAsync(Limit);
        try
        {
            var termination = coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall);
            await Task.Delay(30);
            Assert.That(termination.IsCompleted, Is.False,
                "session end must await a previously cancelled handler's cleanup");
        }
        finally
        {
            releaseCleanup.TrySetResult();
            await cleanupFinished.Task.WaitAsync(Limit);
        }
    }

    [Test]
    public async Task CancelledWorkRetainsCapacityUntilCleanupFinishes()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var releaseCleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var work = new List<Task>();
        var ninth = new ResponseOperation("resp_ninth", "in_ninth");
        try
        {
            for (var index = 0; index < VoiceConnectionState.MaximumActiveResponses; index++)
            {
                var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                var cleanupEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                var operation = new ResponseOperation($"resp_{index}", $"in_{index}");
                Assert.That(state.TryReserveOperation(operation), Is.True);
                operation.Work = Task.Run(async () =>
                {
                    started.TrySetResult();
                    try { await Task.Delay(Timeout.InfiniteTimeSpan, operation.Cancellation.Token); }
                    finally
                    {
                        cleanupEntered.TrySetResult();
                        await releaseCleanup.Task;
                    }
                });
                work.Add(operation.Work);
                await started.Task.WaitAsync(Limit);
                coordinator.CancelOperation(state, operation.ResponseId, ResponseOutcome.Cancelled);
                await cleanupEntered.Task.WaitAsync(Limit);
            }
            Assert.That(state.TryReserveOperation(ninth), Is.False,
                "eight still-running cleanup tasks must continue to consume capacity");
        }
        finally
        {
            releaseCleanup.TrySetResult();
            try { await Task.WhenAll(work).WaitAsync(Limit); }
            catch (OperationCanceledException) { }
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.Cancelled).WaitAsync(Limit);
            ninth.Dispose();
        }
    }
}
