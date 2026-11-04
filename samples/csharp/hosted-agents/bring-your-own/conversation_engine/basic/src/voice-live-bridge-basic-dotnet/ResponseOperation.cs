// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;

namespace VoiceHostedAgent;

internal sealed class ResponseOperation : IDisposable
{
    private readonly object _sync = new();
    private Task? _work;
    private int _disposed;
    private readonly Activity? _activity;
    private readonly Activity? _parentActivity;
    private readonly long? _userMessageReceivedTimestamp;
    private ResponseOutcome? _outcome;
    private bool _telemetryCompleted;

    internal ResponseOperation(
        string responseId,
        string? inputItemId,
        long? userMessageReceivedTimestamp = null)
    {
        ResponseId = responseId;
        InputItemId = inputItemId;
        Cancellation = new CancellationTokenSource();
        _parentActivity = Activity.Current;
        _userMessageReceivedTimestamp = userMessageReceivedTimestamp;
        _activity = inputItemId is not null && userMessageReceivedTimestamp.HasValue
            ? ResponseTelemetry.Start(responseId, inputItemId)
            : null;
    }

    internal string ResponseId { get; }

    internal string? InputItemId { get; }

    internal CancellationTokenSource Cancellation { get; }

    internal Task? Work
    {
        get => Volatile.Read(ref _work);
        set => Volatile.Write(ref _work, value);
    }

    internal bool TryStart(Func<Task> work)
    {
        lock (_sync)
        {
            if (_disposed != 0)
            {
                return false;
            }

            try
            {
                Work = work();
                return true;
            }
            finally
            {
                if (_activity is not null)
                {
                    Activity.Current = _parentActivity;
                }
            }
        }
    }

    internal void SelectOutcome(ResponseOutcome outcome)
    {
        lock (_sync)
        {
            _outcome ??= outcome;
        }
    }

    internal void RecordCompleted() => CompleteTelemetry(ResponseOutcome.Response);

    internal void RecordFailure(Exception exception)
    {
        ResponseTelemetry.RecordErrorType(_activity, exception);
        CompleteTelemetry(ResponseOutcome.Error);
    }

    public void Dispose()
    {
        lock (_sync)
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            if (_activity is not null && Activity.Current == _activity)
            {
                Activity.Current = _parentActivity;
            }
            CompleteTelemetryCore(ResponseOutcome.Abandoned);
            _activity?.Dispose();
            Cancellation.Dispose();
        }
    }

    private void CompleteTelemetry(ResponseOutcome fallback)
    {
        lock (_sync)
        {
            CompleteTelemetryCore(fallback);
        }
    }

    private void CompleteTelemetryCore(ResponseOutcome fallback)
    {
        _outcome ??= fallback;
        if (_telemetryCompleted || !_userMessageReceivedTimestamp.HasValue)
        {
            return;
        }

        _telemetryCompleted = true;
        ResponseTelemetry.RecordOutcome(
            _activity,
            Stopwatch.GetElapsedTime(_userMessageReceivedTimestamp.Value),
            _outcome.Value);
    }
}
