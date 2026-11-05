// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class QueuedCancellationTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [Test]
    public async Task QueuedCancellation_DoesNotOpenProducerResources()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new CapturingVoiceSession();
        var predecessor = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var first = state.EnqueueInputResolution(() => predecessor.Task);
        var started = false;
        async IAsyncEnumerable<string> Producer()
        {
            started = true;
            await Task.Yield();
            yield return "output";
        }
        try
        {
            coordinator.SendEcho(session, state, "in_cancel", Producer(),
                System.Diagnostics.Stopwatch.GetTimestamp());
            Assert.That(state.TryGetResponseForInput("in_cancel", out var responseId), Is.True);
            Assert.That(state.TryGetOperation(responseId, out var operation), Is.True);
            coordinator.CancelOperation(state, responseId, ResponseOutcome.Timeout);
            await Task.Yield();
            Assert.That(started, Is.False);
            predecessor.TrySetResult();
            await operation.Work!.WaitAsync(Limit);
            Assert.That(started, Is.False,
                "The .NET producer acquires resources only when enumerated, after creation.");
            Assert.That(session.Messages, Is.Empty);
        }
        finally
        {
            predecessor.TrySetResult();
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
            await first.WaitAsync(Limit);
        }
    }


    [TestCase("decline")]
    [TestCase("reply")]
    [TestCase("self_cancel")]
    [Repeat(5)]
    public async Task QueuedResolution_DoesNotSendBeforeDelayedCancellationCallbacksFinish(string kind)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new CapturingVoiceSession();
        var predecessor = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var callbackEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var releaseCallback = new ManualResetEventSlim();
        var first = state.EnqueueInputResolution(() => predecessor.Task);
        CancellationTokenRegistration registration = default;
        try
        {
            switch (kind)
            {
                case "decline":
                    coordinator.Observe(coordinator.SendNoneAsync(session, state, "in_cancel", "empty_input"));
                    break;
                case "reply":
                    coordinator.SendEcho(session, state, "in_cancel", Text(), System.Diagnostics.Stopwatch.GetTimestamp());
                    break;
                default:
                    coordinator.StartSelfCancellingResponse(session, state, "in_cancel", "text",
                        System.Diagnostics.Stopwatch.GetTimestamp());
                    break;
            }
            Assert.That(state.TryGetResponseForInput("in_cancel", out var responseId), Is.True);
            Assert.That(state.TryGetOperation(responseId, out var operation), Is.True);
            // Registered last, this callback runs before linked-token propagation.
            registration = operation.Cancellation.Token.Register(() =>
            {
                callbackEntered.TrySetResult();
                if (!releaseCallback.Wait(Limit))
                {
                    throw new TimeoutException("Controlled cancellation callback was not released.");
                }
            });
            var successor = state.EnqueueInputResolution(() => Task.CompletedTask);
            coordinator.CancelOperation(state, responseId, ResponseOutcome.Timeout);
            await callbackEntered.Task.WaitAsync(Limit);
            Assert.That(operation.Cancellation.IsCancellationRequested, Is.True);

            predecessor.TrySetResult();
            await successor.WaitAsync(Limit);
            Assert.That(session.Messages, Is.Empty,
                "A queued operation must not send while its linked cancellation token lags.");
        }
        finally
        {
            predecessor.TrySetResult();
            releaseCallback.Set();
            await registration.DisposeAsync();
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
            await first.WaitAsync(Limit);
        }
    }

    private static async IAsyncEnumerable<string> Text()
    {
        await Task.Yield();
        yield return "text";
    }
}
