// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class CancellationNotificationTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [TestCase(false)]
    [TestCase(true)]
    public async Task ThrowingNotification_DoesNotReleaseWorkerBeforeItsCleanup(bool sessionLifetime)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var cleanupStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseCleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var workerStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var operation = new ResponseOperation("r_notification", "in_notification");
        var token = sessionLifetime ? state.Lifetime.Token : operation.Cancellation.Token;
        operation.Work = Work();
        Assert.That(state.TryReserveOperation(operation), Is.True);
        await workerStarted.Task.WaitAsync(Limit);
        Task termination;
        if (sessionLifetime)
        {
            termination = coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall);
        }
        else
        {
            coordinator.CancelOperation(state, operation.ResponseId, ResponseOutcome.Timeout);
            // Shutdown must still find and join an operation already being cancelled.
            termination = coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall);
        }
        try
        {
            await cleanupStarted.Task.WaitAsync(Limit);
            Assert.ThrowsAsync<TimeoutException>(async () =>
                await termination.WaitAsync(TimeSpan.FromMilliseconds(100)));
            Assert.That(operation.Work.IsCompleted, Is.False);
            Assert.DoesNotThrow(() => _ = operation.Cancellation.Token);
        }
        finally
        {
            releaseCleanup.TrySetResult();
            await termination.WaitAsync(Limit);
            try { await operation.Work.WaitAsync(Limit); }
            catch (OperationCanceledException) { }
            operation.Dispose();
        }

        async Task Work()
        {
            using var registration = token.Register(() =>
                throw new InvalidOperationException("Synthetic notification failure."));
            workerStarted.TrySetResult();
            try
            {
                await Task.Delay(Timeout.Infinite, token);
            }
            finally
            {
                cleanupStarted.TrySetResult();
                await releaseCleanup.Task;
            }
        }
    }
}

