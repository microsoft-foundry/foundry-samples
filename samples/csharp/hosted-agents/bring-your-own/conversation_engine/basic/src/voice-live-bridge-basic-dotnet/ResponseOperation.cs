// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;

namespace VoiceHostedAgent;

internal sealed class ResponseOperation : IDisposable
{
    private readonly object _sync = new();
    private Task? _work;
    private Task? _notification;
    private SemaphoreSlim? _generation;
    private int _disposed;
    private bool _cancellationRequested;
    private bool _finished;
    private readonly Activity? _activity;
    private readonly Activity? _parentActivity;
    private readonly long? _userMessageReceivedTimestamp;
    private ResponseOutcome? _outcome;
    private bool _telemetryCompleted;

    internal ResponseOperation(string responseId, string? inputItemId,
        long? userMessageReceivedTimestamp = null)
    {
        ResponseId = responseId;
        InputItemId = inputItemId;
        Cancellation = new CancellationTokenSource();
        _parentActivity = Activity.Current;
        _userMessageReceivedTimestamp = userMessageReceivedTimestamp;
        _activity = inputItemId is not null && userMessageReceivedTimestamp.HasValue
            ? ResponseTelemetry.Start(responseId, inputItemId) : null;
    }

    internal string ResponseId { get; }
    internal string? InputItemId { get; }
    internal bool ResponseStarted { get; set; }
    internal CancellationTokenSource Cancellation { get; }
    internal bool IsCancellationRequested { get { lock (_sync) { return _cancellationRequested; } } }
    internal Task? Work
    {
        get { lock (_sync) { return _work; } }
        set { lock (_sync) { _work = value; } }
    }

    internal bool TryStart(Func<Task> work)
    {
        lock (_sync)
        {
            if (_disposed != 0 || _cancellationRequested)
            {
                return false;
            }
            try
            {
                _work = work();
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

    internal bool TryRequestCancellation(ResponseOutcome outcome)
    {
        lock (_sync)
        {
            if (_finished || _disposed != 0 || _cancellationRequested)
            {
                return false;
            }
            _cancellationRequested = true;
            _outcome ??= outcome;
        }
        ReleaseGeneration();
        return true;
    }

    internal Task NotifyCancellationAsync()
    {
        lock (_sync)
        {
            // CancelAsync queues callbacks; retain that original task, including its faults.
            return _notification ??= Cancellation.CancelAsync();
        }
    }

    internal bool TryOwnGeneration(SemaphoreSlim gate)
    {
        lock (_sync)
        {
            if (_cancellationRequested || _disposed != 0)
            {
                return false;
            }
            _generation = gate;
            return true;
        }
    }

    internal void ReleaseGeneration()
    {
        SemaphoreSlim? gate;
        lock (_sync)
        {
            gate = _generation;
            _generation = null;
        }
        gate?.Release();
    }

    internal void SelectOutcome(ResponseOutcome outcome)
    {
        lock (_sync) { _outcome ??= outcome; }
    }

    internal void RecordCompleted() => Commit(ResponseOutcome.Response);

    internal void Commit(ResponseOutcome outcome)
    {
        lock (_sync)
        {
            if (!_cancellationRequested)
            {
                _outcome ??= outcome;
                _finished = true;
            }
        }
    }

    internal bool TryFinish()
    {
        lock (_sync)
        {
            if (_cancellationRequested)
            {
                return false; // The cancellation owner joins notification and work before disposal.
            }
            _finished = true;
            return true;
        }
    }

    internal void RecordFailure(Exception exception) =>
        ResponseTelemetry.RecordErrorType(_activity, exception);

    public void Dispose()
    {
        lock (_sync)
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }
            try
            {
                if (_activity is not null && Activity.Current == _activity)
                {
                    Activity.Current = _parentActivity;
                }
                CompleteTelemetryCore(ResponseOutcome.Abandoned);
            }
            finally
            {
                try { _activity?.Dispose(); }
                finally { Cancellation.Dispose(); }
            }
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
        ResponseTelemetry.RecordOutcome(_activity,
            Stopwatch.GetElapsedTime(_userMessageReceivedTimestamp.Value), _outcome.Value);
    }
}
