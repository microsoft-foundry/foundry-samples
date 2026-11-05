// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class ErrorCancellationTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [TestCase("barge_in")]
    [TestCase("timeout")]
    public async Task BlockedGenerationError_RespondsToOperationCancellation(string control)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new BlockingErrorSession();
        try
        {
            coordinator.SendEcho(session, state, "in_error", FailingSource(), Stopwatch.GetTimestamp());
            await session.Started.Task.WaitAsync(Limit);
            Assert.That(state.TryGetResponseForInput("in_error", out var responseId), Is.True);
            Assert.That(state.TryGetOperation(responseId, out var operation), Is.True);
            Assert.That(operation.Work!.IsCompleted, Is.False);

            // These are the same cancellation paths used by barge-in and response.timeout.
            coordinator.CancelOperation(state, responseId,
                control == "timeout" ? ResponseOutcome.Timeout : ResponseOutcome.Cancelled);
            await session.Cancelled.Task.WaitAsync(Limit);
            await operation.Work.WaitAsync(Limit);
            Assert.Multiple(() =>
            {
                Assert.That(session.ErrorToken.IsCancellationRequested, Is.True);
                Assert.That(state.Lifetime.IsCancellationRequested, Is.False,
                    "Response cancellation must not require ending the session.");
                Assert.That(state.TryGetOperation(responseId, out _), Is.False);
                Assert.That(state.TryGetResponseForInput("in_error", out _), Is.False);
                Assert.That(session.Messages.OfType<VoiceErrorMessage>(), Is.Empty);
                Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
            });

            // All response slots must be reusable after error reporting is cancelled.
            for (var index = 0; index < VoiceConnectionState.MaximumActiveResponses; index++)
            {
                Assert.That(state.TryReserveOperation(
                    new ResponseOperation($"r_reuse_{index}", $"in_reuse_{index}")), Is.True);
            }
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }
    }

    [Test]
    public async Task GenerationError_StillReportsWhenOperationIsNotCancelled()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new CapturingVoiceSession();
        try
        {
            coordinator.SendEcho(session, state, "in_error", FailingSource(), Stopwatch.GetTimestamp());
            using var timeout = new CancellationTokenSource(Limit);
            while (state.TryGetResponseForInput("in_error", out _))
            {
                await Task.Delay(5, timeout.Token);
            }
            Assert.That(session.Messages.OfType<VoiceErrorMessage>().Count(), Is.EqualTo(1));
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }
    }

    private static async IAsyncEnumerable<string> FailingSource()
    {
        await Task.FromException(new InvalidOperationException("Controlled generation failure."));
        yield break;
    }

    private sealed class BlockingErrorSession : CapturingVoiceSession
    {
        internal TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource Cancelled { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal CancellationToken ErrorToken { get; private set; }

        public override async Task SendAsync(VoiceOutboundMessage message, CancellationToken cancellationToken = default)
        {
            if (message is VoiceErrorMessage)
            {
                ErrorToken = cancellationToken;
                Started.TrySetResult();
                try
                {
                    await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                }
                finally
                {
                    if (cancellationToken.IsCancellationRequested)
                    {
                        Cancelled.TrySetResult();
                    }
                }
            }
            await base.SendAsync(message, cancellationToken);
        }
    }
}
