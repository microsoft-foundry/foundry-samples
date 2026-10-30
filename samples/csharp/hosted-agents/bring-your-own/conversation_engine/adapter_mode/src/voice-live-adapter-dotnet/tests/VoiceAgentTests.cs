// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Azure.AI.AgentServer.Invocations.Voice;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.RegularExpressions;
using System.Runtime.CompilerServices;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class VoiceAgentTests
{
    private static readonly TimeSpan TestTimeout = TimeSpan.FromSeconds(2);
    private static int s_inputSequence;

    [TestCase("")]
    [TestCase("second")]
    public async Task InputResolutions_KeepDispatchOrderWhenWorkersRunInReverse(string secondText)
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        await agent.SessionStartAsync(session, SessionStart("1.0"));
        var previousContext = SynchronizationContext.Current;
        var paused = new PausedResponseContext();
        try
        {
            SynchronizationContext.SetSynchronizationContext(paused);
            Assert.That(agent.RawUserMessageAsync(session, UserMessage("first", "in_first")).IsCompleted,
                Is.True, "The receive callback must not await response output.");
            Assert.That(agent.RawUserMessageAsync(session, UserMessage(secondText, "in_second")).IsCompleted,
                Is.True, "Even declines must leave the receive loop free for control events.");
        }
        finally
        {
            SynchronizationContext.SetSynchronizationContext(previousContext);
            paused.RunInReverseOrder();
        }

        await WaitUntilAsync(() => ResolutionInputs(session).Length == 2);
        Assert.That(ResolutionInputs(session), Is.EqualTo(new[] { "in_first", "in_second" }));
        await agent.SessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete"));
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task BlockedInputResolution_DoesNotLetDeclineOvertakeOrBlockTimeout(bool cancelFirst)
    {
        var agent = CreateAgent();
        var session = new BlockingCreatedVoiceSession();
        await agent.UserMessageAsync(session, UserMessage("first", "in_first"));
        await session.CreatedSendStarted.Task.WaitAsync(TestTimeout);

        var decline = agent.RawUserMessageAsync(session, UserMessage("", "in_second"));
        Assert.Multiple(() =>
        {
            Assert.That(decline.IsCompleted, Is.True);
            Assert.That(ResolutionInputs(session), Is.Empty);
        });
        if (cancelFirst)
        {
            await agent.ResponseTimeoutAsync(session,
                new VoiceResponseTimeoutEvent("m_timeout", DateTimeOffset.UtcNow, "first_output",
                    null, new[] { "in_first" }));
        }
        else
        {
            session.ReleaseCreatedSend.TrySetResult();
        }

        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseNoneMessage>().Any());
        Assert.That(ResolutionInputs(session), Is.EqualTo(cancelFirst
            ? new[] { "in_second" }
            : new[] { "in_first", "in_second" }));
        await agent.SessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete"));
    }

    [Test]
    public async Task InputTimeout_DuringResponseDoneSend_CancelsAndRecordsTimeout()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new BlockingResponseDoneVoiceSession();
        var input = UserMessage("echo");
        await agent.UserMessageAsync(session, input);
        await session.ResponseDoneSendStarted.Task.WaitAsync(TestTimeout);

        await agent.ResponseTimeoutAsync(session,
            new VoiceResponseTimeoutEvent("m_timeout", DateTimeOffset.UtcNow, "first_output",
                null, new[] { input.ItemId }));
        await session.ResponseDoneSendCancelled.Task.WaitAsync(TestTimeout);
        AssertResponseActivity(capture, await capture.WaitForSingleAsync(), "timeout", ActivityStatusCode.Error);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
    }

    [TestCase(false, "end_call")]
    [TestCase(true, "transport_error")]
    public async Task Termination_SelectsOutcomeBeforeInlineCancellationCleanup(
        bool transportError, string expectedOutcome)
    {
        using var capture = new ResponseActivityCapture();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        Assert.That(state.TryBeginStart(), Is.True);
        state.Activate();
        using var operation = new ResponseOperation("r_inline", "in_inline", Stopwatch.GetTimestamp());
        Assert.That(state.TryReserveOperation(operation), Is.True);
        // Model a send completing synchronously from Lifetime's cancellation callback.
        using var registration = state.Lifetime.Token.Register(() =>
        {
            if (state.TryRemoveOperation(operation.ResponseId, out var removed))
            {
                removed.Dispose();
            }
        });

        await coordinator.TerminateSessionAsync(state,
            transportError ? ResponseOutcome.TransportError : ResponseOutcome.EndCall).WaitAsync(TestTimeout);

        var activity = await capture.WaitForSingleAsync();
        Assert.That(activity.GetTagItem(ResponseTelemetry.OutcomeTag), Is.EqualTo(expectedOutcome));
        Assert.That(capture.Activities, Has.Count.EqualTo(1));
        Assert.That(state.Lifetime.IsCancellationRequested, Is.True);
    }

    private static string[] ResolutionInputs(CapturingVoiceSession session) =>
        session.Messages.SelectMany(message => message switch
        {
            VoiceResponseCreatedMessage created => created.InReplyTo ?? Array.Empty<string>(),
            VoiceResponseNoneMessage none => none.InReplyTo,
            _ => Array.Empty<string>(),
        }).ToArray();

    [Test]
    public async Task CancelledQueuedResponse_DoesNotReleaseLaterResolutionAheadOfPredecessor()
    {
        var agent = CreateAgent();
        var session = new BlockingCreatedVoiceSession();
        await agent.UserMessageAsync(session, UserMessage("first", "in_first"));
        await session.CreatedSendStarted.Task.WaitAsync(TestTimeout);
        await agent.UserMessageAsync(session, UserMessage("second", "in_second"));
        await agent.ResponseTimeoutAsync(session,
            new VoiceResponseTimeoutEvent("m_timeout", DateTimeOffset.UtcNow, "first_output",
                null, new[] { "in_second" }));
        await agent.UserMessageAsync(session, UserMessage("third", "in_third"));

        Assert.That(ResolutionInputs(session), Is.Empty);
        session.ReleaseCreatedSend.TrySetResult();
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 2);
        Assert.That(ResolutionInputs(session), Is.EqualTo(new[] { "in_first", "in_third" }));
        await agent.SessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete"));
    }

    [Test]
    public async Task Termination_CancelsBlockedAndQueuedInputResolutions()
    {
        var agent = CreateAgent();
        var session = new BlockingCreatedVoiceSession();
        await agent.UserMessageAsync(session, UserMessage("first", "in_first"));
        await session.CreatedSendStarted.Task.WaitAsync(TestTimeout);
        await agent.UserMessageAsync(session, UserMessage("second", "in_second"));
        await agent.UserMessageAsync(session, UserMessage("", "in_third"));

        await agent.SessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete")).WaitAsync(TestTimeout);

        Assert.That(session.Messages, Is.Empty);
    }

    [TestCase("no_input")]
    [TestCase("self_cancel")]
    [TestCase("error")]
    [TestCase("capacity")]
    public async Task AllInputResolutionPaths_UseTheSameQueue(string path)
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new BlockingCreatedVoiceSession();
        coordinator.SendEcho(session, state, "in_first", TestChunks("first"), Stopwatch.GetTimestamp());
        await session.CreatedSendStarted.Task.WaitAsync(TestTimeout);
        var pending = Task.CompletedTask;
        var expectedInputs = new List<string> { "in_first", "in_second" };

        switch (path)
        {
            case "no_input":
                coordinator.StartResponse(session, state, "in_second", ResponsePlan.Fixed("Are you still there?"));
                break;
            case "self_cancel":
                coordinator.StartSelfCancellingResponse(session, state, "in_second", "text", Stopwatch.GetTimestamp());
                break;
            case "error":
                pending = coordinator.SendErrorAsync(session, state, "in_second");
                break;
            default:
                for (var index = 1; index < VoiceConnectionState.MaximumActiveResponses; index++)
                {
                    var inputId = $"in_filler_{index}";
                    expectedInputs.Insert(expectedInputs.Count - 1, inputId);
                    coordinator.SendEcho(session, state, inputId, TestChunks("text"), Stopwatch.GetTimestamp());
                }
                coordinator.SendEcho(session, state, "in_second", TestChunks("declined"), Stopwatch.GetTimestamp());
                break;
        }

        Assert.That(ResolutionInputs(session), Is.Empty);
        session.ReleaseCreatedSend.TrySetResult();
        await pending.WaitAsync(TestTimeout);
        await WaitUntilAsync(() => ResolutionInputs(session).Length == expectedInputs.Count);
        Assert.That(ResolutionInputs(session), Is.EqualTo(expectedInputs));
        if (path == "capacity")
        {
            Assert.That(session.Messages.OfType<VoiceResponseNoneMessage>().Single().Reason,
                Is.EqualTo("capacity_exceeded"));
        }
        await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(TestTimeout);
    }

    [Test]
    public async Task SessionStart_AcceptsProtocol10()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.SessionStartAsync(session, SessionStart("1.0"));

        Assert.That(session.Messages, Has.Count.EqualTo(1));
        Assert.That(session.Messages.Single(), Is.TypeOf<VoiceSessionReadyMessage>());
    }

    [Test]
    public async Task SessionStart_RejectsUnsupportedProtocol()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.SessionStartAsync(session, SessionStart("2.0"));

        var rejected = session.Messages.OfType<VoiceSessionRejectedMessage>().Single();
        Assert.Multiple(() =>
        {
            Assert.That(rejected.Code, Is.EqualTo("protocol_mismatch"));
            Assert.That(rejected.Retriable, Is.False);
        });
    }

    [Test]
    public async Task ConcurrentInvalidSessionStart_DoesNotRejectClaimedValidStart()
    {
        var agent = CreateAgent();
        var session = new BlockingReadyVoiceSession();

        var validStart = agent.SessionStartAsync(session, SessionStart("1.0"));
        await session.ReadySendStarted.Task.WaitAsync(TestTimeout);
        await agent.SessionStartAsync(session, SessionStart("2.0"));

        Assert.That(session.Messages.OfType<VoiceSessionRejectedMessage>(), Is.Empty);
        session.ReleaseReadySend.TrySetResult();
        await validStart;
        Assert.That(session.Messages.OfType<VoiceSessionReadyMessage>().Count(), Is.EqualTo(1));
    }

    [Test]
    public async Task InputBeforeSessionStart_IsIgnored()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.RawUserMessageAsync(session, UserMessage("too early"));

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages, Is.Empty);
        });
    }

    [Test]
    public async Task InputAfterRejectedSession_IsIgnored()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        await agent.SessionStartAsync(session, SessionStart("2.0"));
        session.ClearMessages();

        await agent.RawUserMessageAsync(session, UserMessage("after rejection"));

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages, Is.Empty);
        });
    }

    [Test]
    public async Task InputAfterSessionEnd_IsIgnored()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        await agent.SessionStartAsync(session, SessionStart("1.0"));
        await agent.SessionEndAsync(
            session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "caller_hangup"));
        session.ClearMessages();

        await agent.RawUserMessageAsync(session, UserMessage("after end"));

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages, Is.Empty);
        });
    }

    [Test]
    public async Task DuplicateInputItemId_DoesNotEchoAgain()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();
        var duplicate = UserMessage("same input", "in_duplicate");

        await agent.UserMessageAsync(session, duplicate);
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        await agent.UserMessageAsync(session, duplicate);

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>().Count(), Is.EqualTo(1));
            Assert.That(session.Messages.OfType<VoiceResponseNoneMessage>(), Is.Empty);
        });
        await agent.SessionEndAsync(
            session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete"));
    }

    [Test]
    public async Task NinthActiveResponse_IsDeclinedAtCapacity()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        for (var index = 0; index < 9; index++)
        {
            await agent.UserMessageAsync(session, UserMessage($"request {index}"));
        }
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseCreatedMessage>().Count() == 8);

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>().Count(), Is.EqualTo(8));
            Assert.That(
                session.Messages.OfType<VoiceResponseNoneMessage>().Single().Reason,
                Is.EqualTo("capacity_exceeded"));
        });
        await agent.SessionEndAsync(
            session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete"));
    }

    [Test]
    public async Task NinthResponse_IsDeclinedWhileEightResponseDoneSendsAreBlocked()
    {
        var agent = CreateAgent();
        var session = new BlockingResponseDoneVoiceSession();

        for (var index = 0; index < VoiceConnectionState.MaximumTerminalSends; index++)
        {
            await agent.UserMessageAsync(session, UserMessage("hello"));
        }
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Count() ==
                VoiceConnectionState.MaximumTerminalSends);

        await agent.UserMessageAsync(session, UserMessage("hello"));

        Assert.That(
            session.Messages.OfType<VoiceResponseNoneMessage>().Single().Reason,
            Is.EqualTo("capacity_exceeded"));
        session.ReleaseResponseDoneSend.TrySetResult();
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() ==
                VoiceConnectionState.MaximumTerminalSends);
    }

    [Test]
    public async Task InputBeyondConnectionLimit_EndsCallOnce()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        for (var index = 0; index <= VoiceConnectionState.MaximumTrackedInputItems; index++)
        {
            await agent.UserMessageAsync(
                session,
                UserMessage("echo", $"in_limit_{index}"));
        }

        var end = session.Messages.OfType<VoiceEndCallMessage>().Single();
        Assert.Multiple(() =>
        {
            Assert.That(end.Reason, Is.EqualTo("session_input_limit"));
            Assert.That(end.Mode, Is.EqualTo(VoiceEndCallMode.Drain));
        });
    }

    [Test]
    public async Task OversizedMultipartInput_IsDeclined()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        var message = new VoiceUserMessageEvent(
            "m_oversized",
            DateTimeOffset.UtcNow,
            "in_oversized",
            new[]
            {
                new VoiceInputTextPart(new string('a', 4_001)),
                new VoiceInputTextPart(new string('b', 4_000)),
            });

        await agent.UserMessageAsync(session, message);

        Assert.Multiple(() =>
        {
            Assert.That(
                session.Messages.OfType<VoiceResponseNoneMessage>().Single().Reason,
                Is.EqualTo("input_too_large"));
        });
    }

    [Test]
    public async Task ConcurrentTermination_WaitsForSharedWorkAndSendsOneEndCall()
    {
        var coordinator = new VoiceResponseCoordinator(
            NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        Assert.That(state.TryBeginStart(), Is.True);
        state.Activate();
        var operation = new ResponseOperation("resp_termination", "in_termination");
        Assert.That(state.TryReserveOperation(operation), Is.True);
        var cancellationObserved = new TaskCompletionSource(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseCancellation = new TaskCompletionSource(
            TaskCreationOptions.RunContinuationsAsynchronously);
        operation.Work = Task.Run(async () =>
        {
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, operation.Cancellation.Token);
            }
            catch (OperationCanceledException)
            {
                cancellationObserved.TrySetResult();
                await releaseCancellation.Task;
            }
        });
        var session = new CapturingVoiceSession();

        var first = coordinator.TerminateAndEndCallAsync(
            session,
            state,
            VoiceEndCallMode.Drain,
            CancellationToken.None);
        await cancellationObserved.Task.WaitAsync(TestTimeout);
        var second = coordinator.TerminateAndEndCallAsync(
            session,
            state,
            VoiceEndCallMode.Immediate,
            CancellationToken.None);

        Assert.Multiple(() =>
        {
            Assert.That(second.IsCompleted, Is.False);
            Assert.That(session.Messages.OfType<VoiceEndCallMessage>(), Is.Empty);
        });
        releaseCancellation.TrySetResult();
        await Task.WhenAll(first, second).WaitAsync(TestTimeout);
        Assert.That(session.Messages.OfType<VoiceEndCallMessage>().Count(), Is.EqualTo(1));
    }

    [TestCase("/stream hello")]
    [TestCase("/done hello")]
    [TestCase("/voice hello")]
    [TestCase("/none")]
    [TestCase("/proactive hello")]
    [TestCase("/cancel hello")]
    [TestCase("/error")]
    [TestCase("/session-error")]
    [TestCase("/end")]
    [TestCase("/end-now")]
    [TestCase("/help")]
    [TestCase("How are you?")]
    [TestCase("  你好 👋\n")]
    public async Task UserMessage_StreamsExactEcho(string text)
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage(text));
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);

        var created = session.Messages.OfType<VoiceResponseCreatedMessage>().Single();
        var deltas = session.Messages.OfType<VoiceResponseOutputTextDeltaMessage>().ToArray();
        var completed = session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Single();
        Assert.Multiple(() =>
        {
            Assert.That(created.InReplyTo?.Single(), Does.StartWith("in_test_"));
            Assert.That(session.Messages.Select(message => message.MessageType), Is.EqualTo(
                new[] { "response.created" }
                    .Concat(Enumerable.Repeat("response.output_text.delta", Regex.Matches(text, @"\s*\S+|\s+$").Count))
                    .Concat(new[] { "response.output_text.done", "response.done" })));
            Assert.That(deltas, Has.Length.EqualTo(Regex.Matches(text, @"\s*\S+|\s+$").Count));
            Assert.That(string.Concat(deltas.Select(delta => delta.Delta)), Is.EqualTo(text));
            Assert.That(deltas.All(delta => delta.ResponseId == created.ResponseId && delta.ItemId == completed.ItemId), Is.True);
            Assert.That(completed.Text, Is.EqualTo(text));
        });
    }

    [TestCase("界", 8_000)]
    [TestCase("👋", 4_000)]
    public async Task UserMessage_StreamsUnicodeAtUtf16Budget(string symbol, int count)
    {
        var text = string.Concat(Enumerable.Repeat(symbol, count));
        Assert.That(text.Length, Is.EqualTo(8_000));
        await UserMessage_StreamsExactEcho(text);
    }

    [TestCase(4_001)]
    [TestCase(6_000)]
    public async Task UserMessage_DeclinesUnicodeBeyondUtf16Budget(int emojiCount)
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        var text = string.Concat(Enumerable.Repeat("👋", emojiCount));
        Assert.That(text.Length, Is.GreaterThan(8_000));

        await agent.UserMessageAsync(session, UserMessage(text));

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages.OfType<VoiceResponseNoneMessage>().Single().Reason,
                Is.EqualTo("input_too_large"));
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>(), Is.Empty);
        });
    }

    [Test]
    public async Task MultipartInput_EchoesAllParts()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        var message = new VoiceUserMessageEvent(
            "m_multipart",
            DateTimeOffset.UtcNow,
            "in_multipart",
            new[] { new VoiceInputTextPart("Hello, "), new VoiceInputTextPart("世界!") });

        await agent.UserMessageAsync(session, message);
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Any());

        Assert.That(session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Single().Text,
            Is.EqualTo("Hello, 世界!"));
    }

    [Test]
    public async Task NoInput_UsesBridgeInputAndFixedReminder()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.NoInputAsync(
            session,
            new VoiceUserNoInputEvent("m_no_input", DateTimeOffset.UtcNow, "in_silence", 1));
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);

        Assert.Multiple(() =>
        {
            Assert.That(
                session.Messages.OfType<VoiceResponseCreatedMessage>().Single().InReplyTo,
                Is.EqualTo(new[] { "in_silence" }));
            Assert.That(
                session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Single().Text,
                Is.EqualTo("Are you still there?"));
        });
    }

    [Test]
    public async Task ThirdNoInput_EndsCall()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.NoInputAsync(
            session,
            new VoiceUserNoInputEvent("m_no_input", DateTimeOffset.UtcNow, "in_silence", 3));

        var end = session.Messages.OfType<VoiceEndCallMessage>().Single();
        Assert.That(end.Mode, Is.EqualTo(VoiceEndCallMode.Drain));
    }

    [Test]
    public async Task BargeIn_CancelsInFlightEchoOutput()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("Long answer"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;

        await agent.BargeInAsync(
            session,
            new VoiceUserBargeInEvent(
                "m_barge",
                DateTimeOffset.UtcNow,
                responseId,
                heardText: string.Empty));
        await session.OutputCancelled.Task.WaitAsync(TestTimeout);

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
            Assert.That(session.Messages.OfType<VoiceErrorMessage>(), Is.Empty);
        });
    }

    [Test]
    public async Task BargeIn_DoesNotChangeNextEcho()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("interrupted question"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.BargeInAsync(
            session,
            new VoiceUserBargeInEvent(
                "m_barge",
                DateTimeOffset.UtcNow,
                responseId,
                heardText: "heard prefix"));
        await session.OutputCancelled.Task.WaitAsync(TestTimeout);

        session.BlockOutput = false;
        await agent.UserMessageAsync(session, UserMessage("next question"));
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);

        Assert.That(
            session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("next question"));
    }

    [Test]
    public async Task EmptyBargeIn_DoesNotChangeNextEcho()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("interrupted question"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.BargeInAsync(
            session,
            new VoiceUserBargeInEvent(
                "m_empty_barge",
                DateTimeOffset.UtcNow,
                responseId,
                heardText: string.Empty));
        await session.OutputCancelled.Task.WaitAsync(TestTimeout);

        session.BlockOutput = false;
        await agent.UserMessageAsync(session, UserMessage("next question"));
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);

        Assert.That(
            session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("next question"));
    }

    [Test]
    public async Task BargeInAfterResponseDone_DoesNotChangeNextEcho()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("first question"));
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.BargeInAsync(
            session,
            new VoiceUserBargeInEvent(
                "m_barge_after_done",
                DateTimeOffset.UtcNow,
                responseId,
                heardText: "heard prefix"));

        await agent.UserMessageAsync(session, UserMessage("second question"));
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 2);

        Assert.That(
            session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("second question"));
    }

    [Test]
    public async Task ResponseCancelledAfterDone_DoesNotChangeNextEcho()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("first question"));
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.ResponseCancelledAsync(
            session,
            new VoiceResponseCancelledEvent(
                "m_cancelled_after_done",
                DateTimeOffset.UtcNow,
                responseId,
                "heard prefix"));

        await agent.UserMessageAsync(session, UserMessage("second question"));
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 2);

        Assert.That(
            session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("second question"));
    }

    [Test]
    public async Task ResponseTimeout_CancelsInFlightEchoOutput()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("Long answer"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.ResponseTimeoutAsync(
            session,
            new VoiceResponseTimeoutEvent(
                "m_timeout",
                DateTimeOffset.UtcNow,
                "idle",
                responseId));
        await session.OutputCancelled.Task.WaitAsync(TestTimeout);

        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
    }

    [Test]
    public async Task CompletedEchoTurns_AreIndependent()
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("first question"));
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);
        await agent.UserMessageAsync(session, UserMessage("second question"));
        await WaitUntilAsync(
            () => session.Messages.OfType<VoiceResponseDoneMessage>().Count() == 2);

        Assert.That(
            session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("second question"));
    }

    [Test]
    public async Task SessionEnd_CancelsEchoOutput()
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("before end"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        await agent.SessionEndAsync(
            session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "caller_hangup"));
        await session.OutputCancelled.Task.WaitAsync(TestTimeout);

        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
    }

    [Test]
    public async Task SessionEnd_DoesNotAffectAnotherSessionsEcho()
    {
        var agent = CreateAgent();
        var endedSession = new CapturingVoiceSession();
        var activeSession = new CapturingVoiceSession();

        await agent.UserMessageAsync(endedSession, UserMessage("ended question"));
        await WaitUntilAsync(
            () => endedSession.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);
        await agent.UserMessageAsync(activeSession, UserMessage("active question"));
        await WaitUntilAsync(
            () => activeSession.Messages.OfType<VoiceResponseDoneMessage>().Count() == 1);
        var activeResponseId = activeSession.Messages
            .OfType<VoiceResponseCreatedMessage>()
            .Single()
            .ResponseId;

        await agent.SessionEndAsync(
            endedSession,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "caller_hangup"));
        await agent.BargeInAsync(
            activeSession,
            new VoiceUserBargeInEvent(
                "m_barge_after_other_end",
                DateTimeOffset.UtcNow,
                activeResponseId,
                heardText: "heard prefix"));
        await agent.UserMessageAsync(activeSession, UserMessage("next question"));
        await WaitUntilAsync(() => activeSession.Messages.OfType<VoiceResponseDoneMessage>().Count() == 2);

        Assert.That(
            activeSession.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("next question"));
    }

    [Test]
    public async Task ResponseSpan_RecordsUserMessageToResponseDoneSendCompletionDuration()
    {
        var activities = new ConcurrentQueue<Activity>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == ResponseTelemetry.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activities.Enqueue,
        };
        ActivitySource.AddActivityListener(listener);
        using var parent = new Activity("voice-callback").Start();
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await WaitUntilAsync(() => activities.Count == 1);

        var activity = activities.Single();
        var responseDurationMs = (double)activity.GetTagItem(ResponseTelemetry.ResponseDurationTag)!;
        var responseId = session.Messages.OfType<VoiceResponseDoneMessage>().Single().ResponseId;
        Assert.Multiple(() =>
        {
            Assert.That(activity.ParentSpanId, Is.EqualTo(parent.SpanId));
            Assert.That(activity.GetTagItem(ResponseTelemetry.ResponseIdTag), Is.EqualTo(responseId));
            Assert.That(
                activity.GetTagItem(ResponseTelemetry.InputItemIdTag),
                Is.EqualTo(session.Messages.OfType<VoiceResponseCreatedMessage>().Single().InReplyTo!.Single()));
            Assert.That(responseDurationMs, Is.GreaterThanOrEqualTo(0));
            Assert.That(activity.Status, Is.EqualTo(ActivityStatusCode.Ok));
            Assert.That(
                activity.GetTagItem(ResponseTelemetry.OutcomeTag),
                Is.EqualTo("response"));
        });
    }

    [Test]
    public async Task ResponseSpan_RecordsTimeoutOutcome()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.ResponseTimeoutAsync(
            session,
            new VoiceResponseTimeoutEvent(
                "m_timeout",
                DateTimeOffset.UtcNow,
                "first_output",
                responseId));
        var activity = await capture.WaitForSingleAsync();

        AssertResponseActivity(capture, activity, "timeout", ActivityStatusCode.Error);
    }

    [Test]
    public async Task ResponseSpan_RecordsCancelledOutcome()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;
        await agent.BargeInAsync(
            session,
            new VoiceUserBargeInEvent(
                "m_barge",
                DateTimeOffset.UtcNow,
                responseId,
                heardText: string.Empty));
        var activity = await capture.WaitForSingleAsync();

        AssertResponseActivity(capture, activity, "cancelled", ActivityStatusCode.Ok);
    }

    [Test]
    public async Task ResponseSpan_RecordsErrorOutcome()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new FailingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("generate too much"));
        var activity = await capture.WaitForSingleAsync();

        AssertResponseActivity(capture, activity, "error", ActivityStatusCode.Error);
    }

    [Test]
    public async Task ResponseSpan_RecordsEndCallOutcome()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        await agent.SessionEndAsync(
            session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "caller_hangup"));
        var activity = await capture.WaitForSingleAsync();

        AssertResponseActivity(capture, activity, "end_call", ActivityStatusCode.Ok);
    }

    [Test]
    public async Task ResponseSpan_RecordsTransportErrorOutcome()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        agent.ConnectionTerminating(session);
        var activity = await capture.WaitForSingleAsync();

        AssertResponseActivity(capture, activity, "transport_error", ActivityStatusCode.Error);
    }

    [Test]
    public async Task ResponseSpan_RecordsAbandonedOutcomeOnDispose()
    {
        using var capture = new ResponseActivityCapture();

        using (var operation = new ResponseOperation(
            "resp_abandoned",
            "in_abandoned",
            Stopwatch.GetTimestamp()))
        {
        }
        var activity = await capture.WaitForSingleAsync();

        AssertResponseActivity(capture, activity, "abandoned", ActivityStatusCode.Error);
    }

    [Test]
    public async Task RejectedInput_DoesNotCreateResponseActivity()
    {
        using var capture = new ResponseActivityCapture();
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage(new string('x', 8_001)));

        Assert.Multiple(() =>
        {
            Assert.That(session.Messages.OfType<VoiceResponseNoneMessage>().Count(), Is.EqualTo(1));
            Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>(), Is.Empty);
            Assert.That(capture.Activities, Is.Empty);
        });
    }

    [Test]
    public async Task FixedResponseSpan_RecordsResponseDuration()
    {
        var activities = new ConcurrentQueue<Activity>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == ResponseTelemetry.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activities.Enqueue,
        };
        ActivitySource.AddActivityListener(listener);
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await WaitUntilAsync(() => activities.Count == 1);

        var activity = activities.Single();
        Assert.Multiple(() =>
        {
            Assert.That(
                (double)activity.GetTagItem(ResponseTelemetry.ResponseDurationTag)!,
                Is.GreaterThanOrEqualTo(0));
            Assert.That(activity.Status, Is.EqualTo(ActivityStatusCode.Ok));
        });
    }

    [Test]
    public async Task ResponseSpan_CompletesAfterResponseDoneSendCompletes()
    {
        var activities = new ConcurrentQueue<Activity>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == ResponseTelemetry.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activities.Enqueue,
        };
        ActivitySource.AddActivityListener(listener);
        var agent = CreateAgent();
        var session = new BlockingResponseDoneVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await session.ResponseDoneSendStarted.Task.WaitAsync(TestTimeout);

        Assert.That(activities, Is.Empty);

        session.ReleaseResponseDoneSend.TrySetResult();
        await WaitUntilAsync(() => activities.Count == 1);

        var activity = activities.Single();
        Assert.Multiple(() =>
        {
            Assert.That(
                (double)activity.GetTagItem(ResponseTelemetry.ResponseDurationTag)!,
                Is.GreaterThanOrEqualTo(0));
            Assert.That(activity.Status, Is.EqualTo(ActivityStatusCode.Ok));
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Count(), Is.EqualTo(1));
        });
    }

    [Test]
    public async Task ResponseSpan_DoesNotReplaceCallbackAmbientActivity()
    {
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == ResponseTelemetry.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                ActivitySamplingResult.AllDataAndRecorded,
        };
        ActivitySource.AddActivityListener(listener);
        using var parent = new Activity("voice-callback").Start();
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession();

        await agent.UserMessageAsync(session, UserMessage("hello"));
        await session.OutputStarted.Task.WaitAsync(TestTimeout);

        Assert.That(Activity.Current, Is.SameAs(parent));

        await agent.SessionEndAsync(
            session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "caller_hangup"));
        await session.OutputCancelled.Task.WaitAsync(TestTimeout);
    }

    [TestCase("barge_in")]
    [TestCase("response.cancelled")]
    public async Task CompletedResponse_StillSynchronizesHeardText(string eventType)
    {
        var agent = CreateAgent();
        var session = new CapturingVoiceSession();
        await agent.UserMessageAsync(session, UserMessage("complete echo"));
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Any());
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;

        if (eventType == "barge_in")
        {
            await agent.BargeInAsync(session,
                new VoiceUserBargeInEvent("m_barge", DateTimeOffset.UtcNow, responseId, "complete"));
        }
        else
        {
            await agent.ResponseCancelledAsync(session,
                new VoiceResponseCancelledEvent("m_cancelled", DateTimeOffset.UtcNow, responseId, "complete"));
        }

        Assert.That(agent.TryGetHeardText(session, responseId, out var heard), Is.True);
        Assert.That(heard, Is.EqualTo("complete"));
        await agent.SessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "caller_hangup"));
        Assert.That(agent.TryGetHeardText(session, responseId, out _), Is.False);
    }

    [TestCase("barge_in")]
    [TestCase("response.cancelled")]
    [TestCase("response.timeout")]
    [TestCase("input_timeout")]
    public async Task PartialEcho_IsCancelledAndInputCorrelationIsReleased(string eventType)
    {
        var agent = CreateAgent();
        var session = new BlockingOutputVoiceSession { AllowedDeltaCount = 1 };
        var message = UserMessage("pending echo");
        await agent.UserMessageAsync(session, message);
        await session.OutputStarted.Task.WaitAsync(TestTimeout);
        Assert.That(session.Messages.OfType<VoiceResponseOutputTextDeltaMessage>().Single().Delta,
            Is.EqualTo("pending"));
        var responseId = session.Messages.OfType<VoiceResponseCreatedMessage>().Single().ResponseId;

        switch (eventType)
        {
            case "barge_in":
                await agent.BargeInAsync(session,
                    new VoiceUserBargeInEvent("m_barge", DateTimeOffset.UtcNow, responseId, "heard"));
                break;
            case "response.cancelled":
                await agent.ResponseCancelledAsync(session,
                    new VoiceResponseCancelledEvent("m_cancel", DateTimeOffset.UtcNow, responseId, "heard"));
                break;
            case "input_timeout":
                await agent.ResponseTimeoutAsync(session,
                    new VoiceResponseTimeoutEvent("m_timeout", DateTimeOffset.UtcNow, "first_output",
                        null, new[] { message.ItemId }));
                break;
            default:
                await agent.ResponseTimeoutAsync(session,
                    new VoiceResponseTimeoutEvent("m_timeout", DateTimeOffset.UtcNow, "idle", responseId));
                break;
        }

        await session.OutputCancelled.Task.WaitAsync(TestTimeout);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
        if (eventType is "barge_in" or "response.cancelled")
        {
            Assert.That(agent.TryGetHeardText(session, responseId, out var heard), Is.True);
            Assert.That(heard, Is.EqualTo("heard"));
        }

        session.BlockOutput = false;
        await agent.UserMessageAsync(session, UserMessage("next"));
        await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Any());
        Assert.That(session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Last().Text,
            Is.EqualTo("next"));
    }

    [Test]
    public void PlaybackState_IsBoundedAndIgnoresUnknownResponses()
    {
        var state = new VoiceConnectionState();
        Assert.That(state.TryBeginStart(), Is.True);
        state.Activate();
        for (var index = 0; index <= VoiceConnectionState.MaximumTrackedPlaybackResponses; index++)
        {
            using var operation = new ResponseOperation($"r_{index}", $"in_{index}");
            Assert.That(state.TryReserveOperation(operation), Is.True);
            Assert.That(state.TryRemoveOperation(operation.ResponseId, out _), Is.True);
        }

        state.RecordHeardText("r_unknown", "ignore");
        state.RecordHeardText("r_64", "heard");
        Assert.That(state.TryGetHeardText("r_0", out _), Is.False);
        Assert.That(state.TryGetHeardText("r_unknown", out _), Is.False);
        Assert.That(state.TryGetHeardText("r_64", out var heard), Is.True);
        Assert.That(heard, Is.EqualTo("heard"));
    }

    [Test]
    public async Task AsyncSource_SendsFirstChunkBeforeRemainderIsAvailable()
    {
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        var session = new CapturingVoiceSession();
        var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var closed = false;
        async IAsyncEnumerable<string> Source([EnumeratorCancellation] CancellationToken token = default)
        {
            try
            {
                yield return "first";
                waiting.TrySetResult();
                await release.Task.WaitAsync(token);
                yield return " second";
            }
            finally
            {
                closed = true;
            }
        }

        coordinator.SendEcho(session, state, "in_async", Source(), Stopwatch.GetTimestamp());
        try
        {
            await waiting.Task.WaitAsync(TestTimeout);
            Assert.That(session.Messages.OfType<VoiceResponseOutputTextDeltaMessage>().Single().Delta,
                Is.EqualTo("first"));
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
            release.TrySetResult();
            await WaitUntilAsync(() => session.Messages.OfType<VoiceResponseDoneMessage>().Any());
            Assert.That(session.Messages.OfType<VoiceResponseOutputTextDoneMessage>().Single().Text,
                Is.EqualTo("first second"));
            Assert.That(closed, Is.True);
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.Cancelled).WaitAsync(TestTimeout);
        }
    }

    [TestCase("timeout")]
    [TestCase("end_call")]
    [TestCase("source_error")]
    [TestCase("send_error")]
    public async Task AsyncSource_IsDisposedOnCancellationAndFailure(string action)
    {
        using var capture = new ResponseActivityCapture();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        CapturingVoiceSession session = action == "send_error"
            ? new FailingOutputVoiceSession() : new CapturingVoiceSession();
        var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var closed = false;
        async IAsyncEnumerable<string> Source([EnumeratorCancellation] CancellationToken token = default)
        {
            try
            {
                yield return "first";
                waiting.TrySetResult();
                if (action == "source_error")
                {
                    throw new InvalidOperationException("Test source failure.");
                }
                await Task.Delay(Timeout.InfiniteTimeSpan, token);
            }
            finally
            {
                closed = true;
            }
        }

        coordinator.SendEcho(session, state, "in_async", Source(), Stopwatch.GetTimestamp());
        try
        {
            if (action is "timeout" or "end_call")
            {
                await waiting.Task.WaitAsync(TestTimeout);
                if (action == "timeout")
                {
                    Assert.That(state.TryGetResponseForInput("in_async", out var responseId), Is.True);
                    coordinator.CancelOperation(state, responseId, ResponseOutcome.Timeout);
                }
                else
                {
                    await coordinator.TerminateSessionAsync(state, ResponseOutcome.EndCall).WaitAsync(TestTimeout);
                }
            }
            var activity = await capture.WaitForSingleAsync();
            Assert.That(activity.GetTagItem(ResponseTelemetry.OutcomeTag),
                Is.EqualTo(action is "timeout" or "end_call" ? action : "error"));
            Assert.That(closed, Is.True);
            Assert.That(state.TryGetResponseForInput("in_async", out _), Is.False);
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
            if (action is "source_error" or "send_error")
            {
                Assert.That(session.Messages.OfType<VoiceErrorMessage>().Single().Code,
                    Is.EqualTo("generation_failed"));
            }
        }
        finally
        {
            await coordinator.TerminateSessionAsync(state, ResponseOutcome.Cancelled).WaitAsync(TestTimeout);
        }
    }

    private static async IAsyncEnumerable<string> TestChunks(string text)
    {
        await Task.Yield();
        yield return text;
    }

    private static TestableVoiceAgent CreateAgent() =>
        new(NullLogger<VoiceAgent>.Instance);

    private static VoiceSessionStartEvent SessionStart(string protocolVersion) =>
        new(
            "m_start",
            DateTimeOffset.UtcNow,
            protocolVersion,
            reconnect: false,
            new VoiceResponseTimeouts(1000, 1000, 30000),
            greeting: null,
            noInputTimeoutMs: null,
            caller: null);

    private static VoiceUserMessageEvent UserMessage(string text, string? itemId = null) =>
        new(
            "m_user",
            DateTimeOffset.UtcNow,
            itemId ?? $"in_test_{Interlocked.Increment(ref s_inputSequence)}",
            new[] { new VoiceInputTextPart(text) });

    private static async Task WaitUntilAsync(Func<bool> predicate)
    {
        using var timeout = new CancellationTokenSource(TestTimeout);
        while (!predicate())
        {
            await Task.Delay(TimeSpan.FromMilliseconds(10), timeout.Token);
        }
    }

    private static void AssertResponseActivity(
        ResponseActivityCapture capture,
        Activity activity,
        string outcome,
        ActivityStatusCode status)
    {
        Assert.Multiple(() =>
        {
            Assert.That(capture.Activities, Has.Count.EqualTo(1));
            Assert.That(activity.Status, Is.EqualTo(status));
            Assert.That(activity.GetTagItem(ResponseTelemetry.OutcomeTag), Is.EqualTo(outcome));
            Assert.That(
                (double)activity.GetTagItem(ResponseTelemetry.ResponseDurationTag)!,
                Is.GreaterThanOrEqualTo(0));
        });
    }

    private sealed class TestableVoiceAgent : VoiceAgent
    {
        private readonly object _sessionSync = new();
        private readonly HashSet<VoiceSession> _startedSessions = new();

        internal TestableVoiceAgent(
            Microsoft.Extensions.Logging.ILogger<VoiceAgent> logger)
            : base(logger, new InvocationAdapter(new EchoHttpAgent()))
        {
        }

        internal Task SessionStartAsync(VoiceSession session, VoiceSessionStartEvent start) =>
            OnSessionStartAsync(session, start, CancellationToken.None);

        internal async Task UserMessageAsync(VoiceSession session, VoiceUserMessageEvent message)
        {
            await EnsureStartedAsync(session);
            await OnUserMessageAsync(session, message, CancellationToken.None);
        }

        internal Task RawUserMessageAsync(VoiceSession session, VoiceUserMessageEvent message) =>
            OnUserMessageAsync(session, message, CancellationToken.None);

        internal async Task NoInputAsync(VoiceSession session, VoiceUserNoInputEvent noInput)
        {
            await EnsureStartedAsync(session);
            await OnUserNoInputAsync(session, noInput, CancellationToken.None);
        }

        internal Task BargeInAsync(VoiceSession session, VoiceUserBargeInEvent bargeIn) =>
            OnUserBargeInAsync(session, bargeIn, CancellationToken.None);

        internal Task ResponseAcceptedAsync(
            VoiceSession session,
            VoiceResponseAcceptedEvent accepted) =>
            OnResponseAcceptedAsync(session, accepted, CancellationToken.None);

        internal Task ResponseDroppedAsync(
            VoiceSession session,
            VoiceResponseDroppedEvent dropped) =>
            OnResponseDroppedAsync(session, dropped, CancellationToken.None);

        internal Task ResponseCancelledAsync(
            VoiceSession session,
            VoiceResponseCancelledEvent cancelled) =>
            OnResponseCancelledAsync(session, cancelled, CancellationToken.None);

        internal Task ResponseTimeoutAsync(
            VoiceSession session,
            VoiceResponseTimeoutEvent timeout) =>
            OnResponseTimeoutAsync(session, timeout, CancellationToken.None);

        internal Task SessionEndAsync(VoiceSession session, VoiceSessionEndEvent end) =>
            OnSessionEndAsync(session, end, CancellationToken.None);

        internal void ConnectionTerminating(VoiceSession session) =>
            OnConnectionTerminating(session);

        private async Task EnsureStartedAsync(VoiceSession session)
        {
            lock (_sessionSync)
            {
                if (!_startedSessions.Add(session))
                {
                    return;
                }
            }

            await OnSessionStartAsync(session, SessionStart("1.0"), CancellationToken.None);
            switch (session)
            {
                case CapturingVoiceSession capturing:
                    capturing.ClearMessages();
                    break;
                case BlockingResponseDoneVoiceSession blocking:
                    blocking.ClearMessages();
                    break;
            }
        }
    }

    private sealed class ResponseActivityCapture : IDisposable
    {
        private readonly ConcurrentQueue<Activity> _activities = new();
        private readonly ActivityListener _listener;

        internal ResponseActivityCapture()
        {
            _listener = new ActivityListener
            {
                ShouldListenTo = source => source.Name == ResponseTelemetry.SourceName,
                Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                    ActivitySamplingResult.AllDataAndRecorded,
                ActivityStopped = _activities.Enqueue,
            };
            ActivitySource.AddActivityListener(_listener);
        }

        internal IReadOnlyCollection<Activity> Activities => _activities.ToArray();

        internal async Task<Activity> WaitForSingleAsync()
        {
            await WaitUntilAsync(() => _activities.Count == 1);
            return _activities.Single();
        }

        public void Dispose() => _listener.Dispose();
    }
}
