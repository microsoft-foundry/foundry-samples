// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class SelfCancellationTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [TestCase("cancelled")]
    [TestCase("barge_in")]
    [TestCase("timeout")]
    public async Task MoreThanEightSelfCancels_ReleaseCapacityOnlyAfterTerminalOutcome(string terminal)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new CapturingVoiceSession();
        try
        {
            for (var index = 0; index < 24; index++)
            {
                var inputId = $"in_cancel_{index}";
                coordinator.StartSelfCancellingResponse(session, state, inputId, "text", Stopwatch.GetTimestamp());
                Assert.That(state.TryGetResponseForInput(inputId, out var responseId), Is.True);
                Assert.That(state.TryGetOperation(responseId, out var operation), Is.True);
                await operation.Work!.WaitAsync(Limit);
                Assert.That(session.Messages.OfType<VoiceResponseCancelMessage>()
                    .Any(message => message.ResponseId == responseId), Is.True);
                // A successfully sent cancel is a request, not the terminal playback outcome.
                Assert.That(state.TryGetOperation(responseId, out _), Is.True);
                Assert.That(state.TryGetResponseForInput(inputId, out _), Is.True);

                if (terminal != "timeout") { state.RecordHeardText(responseId, "heard"); }
                coordinator.CancelOperation(state, responseId,
                    terminal == "timeout" ? ResponseOutcome.Timeout : ResponseOutcome.Cancelled);
                using var timeout = new CancellationTokenSource(Limit);
                while (state.TryGetOperation(responseId, out _))
                {
                    await Task.Delay(1, timeout.Token);
                }
                Assert.That(state.TryGetResponseForInput(inputId, out _), Is.False);
                // A duplicate terminal event must be harmless.
                coordinator.CancelOperation(state, responseId, ResponseOutcome.Cancelled);
                Assert.That(state.Lifetime.IsCancellationRequested, Is.False);
            }
            Assert.That(session.Messages.OfType<VoiceResponseNoneMessage>(), Is.Empty);
            Assert.That(session.Messages.OfType<VoiceResponseCancelMessage>().Count(), Is.EqualTo(24));
            for (var index = 0; index < VoiceConnectionState.MaximumActiveResponses; index++)
            {
                Assert.That(state.TryReserveOperation(new ResponseOperation($"r_reuse_{index}", $"in_reuse_{index}")), Is.True);
            }
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(Limit);
        }
    }
}
