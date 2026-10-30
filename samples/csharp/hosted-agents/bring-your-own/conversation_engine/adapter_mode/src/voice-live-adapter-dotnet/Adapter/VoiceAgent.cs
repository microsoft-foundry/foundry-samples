// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Invocations.Voice;

namespace VoiceHostedAgent;

/// <summary>Sample-maintained CE lifecycle around an in-process invocation handler.</summary>
public class VoiceAgent : VoiceHandler
{
    private const int MaximumInputCharacters = 8_000;

    private readonly ConditionalWeakTable<VoiceSession, VoiceConnectionState> _connections = new();
    private readonly VoiceResponseCoordinator _responses;
    private readonly InvocationAdapter _backend;
    private readonly ILogger<VoiceAgent> _logger;

    public VoiceAgent(ILogger<VoiceAgent> logger, InvocationAdapter backend)
    {
        _responses = new VoiceResponseCoordinator(logger);
        _backend = backend;
        _logger = logger;
    }

    protected override async Task OnSessionStartAsync(
        VoiceSession session,
        VoiceSessionStartEvent start,
        CancellationToken cancellationToken)
    {
        var state = _connections.GetValue(session, static _ => new VoiceConnectionState());
        if (!state.TryBeginStart())
        {
            _logger.LogWarning("Ignored duplicate or late session.start");
            return;
        }

        if (!string.Equals(start.ProtocolVersion, "1.0", StringComparison.Ordinal))
        {
            state.Reject();
            await session.SendAsync(
                new VoiceSessionRejectedMessage("protocol_mismatch", retriable: false),
                cancellationToken);
            return;
        }

        if (string.Equals(Environment.GetEnvironmentVariable("VOICE_SAMPLE_REJECT_START"),
            "true", StringComparison.OrdinalIgnoreCase))
        {
            state.Reject();
            await session.SendAsync(
                new VoiceSessionRejectedMessage("startup_failed", retriable: true),
                cancellationToken);
            return;
        }

        _logger.LogInformation(
            "Voice session {SessionId} started; reconnect={Reconnect}",
            session.InvocationContext.SessionId,
            start.Reconnect);
        try
        {
            await session.SendAsync(new VoiceSessionReadyMessage(), cancellationToken);
            state.Activate();
        }
        catch
        {
            await _responses.TerminateSessionAsync(state, ResponseOutcome.TransportError);
            throw;
        }
    }

    protected override async Task OnUserMessageAsync(
        VoiceSession session,
        VoiceUserMessageEvent message,
        CancellationToken cancellationToken)
    {
        if (!TryTrackInput(session, message.ItemId, out var state, out var rejectionReason))
        {
            await TryDeclineInputAsync(
                session,
                state,
                message.ItemId,
                rejectionReason,
                cancellationToken);
            return;
        }

        var userMessageReceivedTimestamp = Stopwatch.GetTimestamp();
        var text = string.Concat(message.Content.Select(part => part.Text));
        if (text.Length == 0 || text.Length > MaximumInputCharacters)
        {
            _responses.Observe(_responses.SendNoneAsync(session, state, message.ItemId,
                text.Length == 0 ? "empty_input" : "input_too_large"));
            return;
        }

        _responses.SendEcho(session, state, message.ItemId,
            _backend.Stream(session, message.ItemId, text), userMessageReceivedTimestamp);
    }

    protected override Task OnUserNoInputAsync(
        VoiceSession session,
        VoiceUserNoInputEvent noInput,
        CancellationToken cancellationToken)
    {
        if (!TryTrackInput(session, noInput.ItemId, out var state, out var rejectionReason))
        {
            return TryDeclineInputAsync(
                session,
                state,
                noInput.ItemId,
                rejectionReason,
                cancellationToken);
        }

        if (noInput.Count >= 3)
        {
            return _responses.TerminateAndEndCallAsync(
                session,
                state,
                VoiceEndCallMode.Drain,
                cancellationToken);
        }

        _responses.StartResponse(
            session,
            state,
            noInput.ItemId,
            ResponsePlan.Fixed("Are you still there?"));
        return Task.CompletedTask;
    }

    protected override Task OnUserSpeechStartedAsync(
        VoiceSession session,
        VoiceUserSpeechStartedEvent speechStarted,
        CancellationToken cancellationToken)
    {
        _logger.LogDebug("Caller speech started");
        return Task.CompletedTask;
    }

    protected override Task OnUserBargeInAsync(
        VoiceSession session,
        VoiceUserBargeInEvent bargeIn,
        CancellationToken cancellationToken)
    {
        if (_connections.TryGetValue(session, out var state))
        {
            state.RecordHeardText(bargeIn.ResponseId, bargeIn.HeardText);
            _responses.CancelOperation(state, bargeIn.ResponseId, ResponseOutcome.Cancelled);
        }
        return Task.CompletedTask;
    }

    protected override Task OnResponseAcceptedAsync(
        VoiceSession session,
        VoiceResponseAcceptedEvent accepted,
        CancellationToken cancellationToken) =>
        _connections.TryGetValue(session, out var state)
            ? _responses.AcceptProactiveAsync(session, state, accepted.ResponseId)
            : Task.CompletedTask;

    protected override Task OnResponseDroppedAsync(
        VoiceSession session,
        VoiceResponseDroppedEvent dropped,
        CancellationToken cancellationToken)
    {
        if (_connections.TryGetValue(session, out var state))
        {
            state.RemoveProactive(dropped.ResponseId);
        }
        _logger.LogInformation(
            "Proactive response {ResponseId} was dropped: {Reason}",
            dropped.ResponseId,
            dropped.Reason);
        return Task.CompletedTask;
    }

    protected override Task OnResponseCancelledAsync(
        VoiceSession session,
        VoiceResponseCancelledEvent cancelled,
        CancellationToken cancellationToken)
    {
        if (_connections.TryGetValue(session, out var state))
        {
            state.RecordHeardText(cancelled.ResponseId, cancelled.HeardText);
            _responses.CancelOperation(state, cancelled.ResponseId, ResponseOutcome.Cancelled);
        }
        return Task.CompletedTask;
    }

    protected override Task OnResponseTimeoutAsync(
        VoiceSession session,
        VoiceResponseTimeoutEvent timeout,
        CancellationToken cancellationToken)
    {
        if (!_connections.TryGetValue(session, out var state))
        {
            return Task.CompletedTask;
        }

        if (timeout.ResponseId is not null)
        {
            state.RemoveProactive(timeout.ResponseId);
            _responses.CancelOperation(state, timeout.ResponseId, ResponseOutcome.Timeout);
        }
        else if (timeout.ItemIds is not null)
        {
            foreach (var itemId in timeout.ItemIds)
            {
                if (state.TryGetResponseForInput(itemId, out var responseId))
                {
                    _responses.CancelOperation(state, responseId, ResponseOutcome.Timeout);
                }
            }
        }
        return Task.CompletedTask;
    }

    protected override async Task OnSessionEndAsync(
        VoiceSession session,
        VoiceSessionEndEvent end,
        CancellationToken cancellationToken)
    {
        if (_connections.TryGetValue(session, out var state))
        {
            await _responses.TerminateSessionAsync(state, ResponseOutcome.EndCall);
        }
    }

    protected override void OnConnectionTerminating(VoiceSession session)
    {
        if (_connections.TryGetValue(session, out var state))
        {
            _responses.Observe(
                _responses.TerminateSessionAsync(
                    state,
                    ResponseOutcome.TransportError));
        }
    }

    internal bool TryGetHeardText(VoiceSession session, string responseId, out string heardText)
    {
        heardText = string.Empty;
        return _connections.TryGetValue(session, out var state) &&
            state.TryGetHeardText(responseId, out heardText);
    }

    private bool TryTrackInput(
        VoiceSession session,
        string inputItemId,
        out VoiceConnectionState state,
        out string? rejectionReason)
    {
        state = _connections.GetValue(session, static _ => new VoiceConnectionState());
        switch (state.TryTrackInput(inputItemId))
        {
            case InputAdmission.Accepted:
                rejectionReason = null;
                return true;
            case InputAdmission.Duplicate:
                rejectionReason = null;
                _logger.LogWarning("Ignored duplicate Voice input item");
                return false;
            case InputAdmission.CapacityExceeded:
                rejectionReason = "session_input_limit";
                return false;
            default:
                rejectionReason = null;
                _logger.LogDebug("Ignored input outside an active Voice session");
                return false;
        }
    }

    private Task TryDeclineInputAsync(
        VoiceSession session,
        VoiceConnectionState state,
        string inputItemId,
        string? reason,
        CancellationToken cancellationToken) =>
        reason switch
        {
            null => Task.CompletedTask,
            "session_input_limit" => _responses.TerminateAndEndCallAsync(
                session,
                state,
                VoiceEndCallMode.Drain,
                cancellationToken,
                reason),
            _ => _responses.SendNoneAsync(session, state, inputItemId, reason),
        };
}
