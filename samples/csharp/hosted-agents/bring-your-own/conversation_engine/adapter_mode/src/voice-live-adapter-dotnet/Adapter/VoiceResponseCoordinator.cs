// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text;
using System.Runtime.ExceptionServices;
using Azure.AI.AgentServer.Invocations.Voice;

namespace VoiceHostedAgent;

/// <summary>Coordinates bounded response execution and its Voice wire lifecycle.</summary>
internal sealed class VoiceResponseCoordinator
{
    private readonly ILogger<VoiceAgent> _logger;
    private readonly HashSet<Task> _observed = new();
    private readonly CancellationTokenSource _shutdown = new();

    internal VoiceResponseCoordinator(ILogger<VoiceAgent> logger)
    {
        _logger = logger;
    }

    /// <summary>Schedule a cancellable echo without blocking incoming control events.</summary>
    internal void SendEcho(
        VoiceSession session,
        VoiceConnectionState state,
        string inputItemId,
        IAsyncEnumerable<string> chunks,
        long receivedAt) =>
        StartResponse(session, state, inputItemId, new ResponsePlan(chunks, true, null),
            userMessageReceivedTimestamp: receivedAt);

    internal void StartResponse(
        VoiceSession session,
        VoiceConnectionState state,
        string? inputItemId,
        ResponsePlan plan,
        string? responseId = null,
        long? userMessageReceivedTimestamp = null)
    {
        responseId ??= VoiceIds.CreateResponseId();
        var operation = new ResponseOperation(
            responseId,
            inputItemId,
            userMessageReceivedTimestamp);

        if (!state.TryReserveOperation(operation))
        {
            operation.Dispose();
            if (inputItemId is not null)
            {
                Observe(SendNoneAsync(session, state, inputItemId, "capacity_exceeded"));
            }
            return;
        }

        StartReservedResponse(session, state, operation, plan);
    }

    internal void StartSelfCancellingResponse(
        VoiceSession session,
        VoiceConnectionState state,
        string inputItemId,
        string text,
        long userMessageReceivedTimestamp)
    {
        var responseId = VoiceIds.CreateResponseId();
        var operation = new ResponseOperation(responseId, inputItemId, userMessageReceivedTimestamp);
        if (!state.TryReserveOperation(operation))
        {
            operation.Dispose();
            Observe(SendNoneAsync(session, state, inputItemId, "capacity_exceeded"));
            return;
        }

        operation.TryStart(() => RunSelfCancellingResponseAsync(session, state, operation, text));
        if (operation.Work is { } work) { Observe(work); }
    }

    internal Task SendNoneAsync(
        VoiceSession session, VoiceConnectionState state, string inputItemId, string reason)
    {
        var operation = new ResponseOperation(VoiceIds.CreateResponseId(), inputItemId);
        if (!state.TryReserveOperation(operation, terminalOnly: true))
        {
            operation.Dispose();
            return state.IsActive
                ? TerminateAndEndCallAsync(session, state, VoiceEndCallMode.Drain,
                    CancellationToken.None, "capacity_exceeded")
                : Task.CompletedTask;
        }
        operation.TryStart(() => DeclineAsync());
        var work = operation.Work ?? Task.CompletedTask;
        Observe(work);
        return work;

        async Task DeclineAsync()
        {
            using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(
                state.Lifetime.Token, operation.Cancellation.Token);
            try
            {
                await state.EnqueueInputResolution(async () =>
                {
                    ThrowIfStopped(state, operation, cancellation.Token);
                    await session.SendAsync(new VoiceResponseNoneMessage(new[] { inputItemId }, reason),
                        cancellation.Token);
                    operation.Commit(ResponseOutcome.None);
                }, operation.Cancellation.Token);
            }
            catch (OperationCanceledException) when (
                operation.IsCancellationRequested || !state.IsActive)
            { }
            finally
            {
                if (operation.TryFinish()) { RemoveOperation(state, operation.ResponseId); }
            }
        }
    }

    internal async Task SendErrorAsync(
        VoiceSession session,
        VoiceConnectionState state,
        string inputItemId)
    {
        var responseId = VoiceIds.CreateResponseId();
        await TrySendAsync(state, async () =>
        {
            await state.EnqueueInputResolution(() => session.SendAsync(
                new VoiceResponseCreatedMessage(responseId, new[] { inputItemId }),
                state.Lifetime.Token));
            await session.SendAsync(
                new VoiceErrorMessage(
                    "sample_error",
                    "The sample emitted the requested error.",
                    responseId),
                state.Lifetime.Token);
        });
    }

    internal async Task SendProactiveRequestAsync(
        VoiceSession session,
        VoiceConnectionState state,
        string responseId)
    {
        try
        {
            await session.SendAsync(
                new VoiceResponseCreatedMessage(
                    responseId,
                    admissionTimeoutMs: 5000,
                    supersedeKey: "voice-live-adapter-dotnet"),
                state.Lifetime.Token);
        }
        catch (OperationCanceledException) when (state.Lifetime.IsCancellationRequested)
        {
            state.RemoveProactive(responseId);
        }
        catch (Exception exception)
        {
            state.RemoveProactive(responseId);
            _logger.LogWarning(
                exception,
                "Could not request proactive response {ResponseId}",
                responseId);
        }
    }

    internal Task AcceptProactiveAsync(
        VoiceSession session,
        VoiceConnectionState state,
        string responseId)
    {
        var admission = state.TryAcceptProactive(responseId, out var operation, out var plan);
        if (admission == ProactiveAdmission.Accepted)
        {
            StartReservedResponse(session, state, operation!, plan!);
        }
        else if (admission == ProactiveAdmission.ActiveCapacityExceeded)
        {
            var declined = new ResponseOperation(responseId, inputItemId: null) { ResponseStarted = true };
            if (state.TryReserveOperation(declined, terminalOnly: true))
            {
                declined.TryStart(() => CancelAcceptedAsync(declined));
                if (declined.Work is { } work) { Observe(work); }
            }
            else
            {
                declined.Dispose();
                Observe(TerminateAndEndCallAsync(session, state, VoiceEndCallMode.Drain,
                    CancellationToken.None, "capacity_exceeded"));
            }
        }
        return Task.CompletedTask;

        async Task CancelAcceptedAsync(ResponseOperation declined)
        {
            using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(
                state.Lifetime.Token, declined.Cancellation.Token);
            try
            {
                await Task.Yield();
                await AcquireGenerationAsync(state, declined, cancellation.Token);
                await session.SendAsync(new VoiceResponseCancelMessage(responseId, "capacity_exceeded"),
                    cancellation.Token);
                // response.cancel is a request, not the winning terminal outcome.
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellation.Token);
            }
            catch (OperationCanceledException) when (declined.IsCancellationRequested || !state.IsActive) { }
            finally
            {
                declined.ReleaseGeneration();
                if (declined.TryFinish()) { RemoveOperation(state, responseId); }
            }
        }
    }

    internal void CancelOperation(
        VoiceConnectionState state,
        string responseId,
        ResponseOutcome outcome)
    {
        if (state.TryGetOperation(responseId, out var operation) &&
            operation.TryRequestCancellation(outcome))
        {
            Observe(DrainOperationAsync(state, operation, NotifyCancellationAsync(operation)));
        }
    }

    internal async Task TerminateAndEndCallAsync(
        VoiceSession session,
        VoiceConnectionState state,
        VoiceEndCallMode mode,
        CancellationToken cancellationToken,
        string reason = "sample_completed")
    {
        var termination = BeginTermination(state, ResponseOutcome.EndCall);
        try
        {
            if (termination.Owns)
            {
                await termination.Notification;
                using var sendCancellation = CancellationTokenSource.CreateLinkedTokenSource(
                    cancellationToken, _shutdown.Token);
                await session.SendAsync(new VoiceEndCallMessage(reason, mode), sendCancellation.Token);
            }
        }
        finally { await termination.Completion; }
    }

    internal Task TerminateSessionAsync(VoiceConnectionState state, ResponseOutcome outcome) =>
        BeginTermination(state, outcome).Completion;

    internal void Observe(Task task)
    {
        lock (_observed)
        {
            if (!_observed.Add(task)) { return; }
        }
        _ = ObserveAsync(task);
    }

    private void StartReservedResponse(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        ResponsePlan plan)
    {
        operation.ResponseStarted = operation.InputItemId is null;
        operation.TryStart(() => RunResponseAsync(session, state, operation, plan));
        if (operation.Work is { } work) { Observe(work); }
    }

    private async Task RunResponseAsync(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        ResponsePlan plan)
    {
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(
            operation.Cancellation.Token,
            state.Lifetime.Token);
        var cancellationToken = cancellation.Token;
        try
        {
            await SendOutputAsync(session, state, operation, plan, cancellationToken);
        }
        catch (OperationCanceledException) when (operation.IsCancellationRequested || cancellationToken.IsCancellationRequested || !state.IsActive)
        {
        }
        catch (Exception exception)
        {
            operation.RecordFailure(exception);
            _logger.LogWarning("Voice response failed; error_type={ErrorType}", exception.GetType().Name);
            await TrySendErrorAsync(session, state, operation, cancellationToken);
        }
        finally
        {
            operation.ReleaseGeneration();
            if (operation.TryFinish()) { RemoveOperation(state, operation.ResponseId); }
        }
    }

    private async Task SendOutputAsync(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        ResponsePlan plan,
        CancellationToken cancellationToken)
    {
        var itemId = VoiceIds.CreateItemId();
        var text = new StringBuilder();
        var outputCharacters = 0;
        IAsyncEnumerator<string>? iterator = null;
        Exception? primaryError = null;
        try
        {
            // Reserve input order before yielding; adopt the iterator before any send.
            var created = operation.InputItemId is not null
                ? state.EnqueueInputResolution(async () =>
                {
                    await AcquireGenerationAsync(state, operation, cancellationToken);
                    await session.SendAsync(new VoiceResponseCreatedMessage(
                        operation.ResponseId, new[] { operation.InputItemId }), cancellationToken);
                    operation.ResponseStarted = true;
                }, operation.Cancellation.Token)
                : AcquireGenerationAsync(state, operation, cancellationToken);
            Exception? initializationError = null;
            try { iterator = plan.Chunks.GetAsyncEnumerator(cancellationToken); }
            catch (Exception error) { initializationError = error; }
            await Task.Yield();
            await created;
            ThrowIfStopped(state, operation, cancellationToken);
            if (initializationError is not null) { ExceptionDispatchInfo.Throw(initializationError); }
            while (await iterator!.MoveNextAsync())
            {
                ThrowIfStopped(state, operation, cancellationToken);
                var chunk = iterator.Current;
                if (chunk.Length == 0)
                {
                    await Task.Yield();
                    continue;
                }
                if ((outputCharacters += chunk.EnumerateRunes().Count()) > 8_000)
                {
                    throw new InvalidOperationException("Response text exceeds its character budget.");
                }
                text.Append(chunk);
                if (plan.Streaming)
                {
                    await session.SendAsync(
                        new VoiceResponseOutputTextDeltaMessage(
                            operation.ResponseId, itemId, chunk, plan.Voice), cancellationToken);
                }
                // Ready/non-streaming producers must also allow control callbacks to progress.
                await Task.Yield();
            }
        }
        catch (Exception error)
        {
            primaryError = error;
            throw;
        }
        finally
        {
            try
            {
                if (iterator is not null) { await iterator.DisposeAsync(); }
            }
            catch (Exception error) when (primaryError is not null)
            {
                _logger.LogWarning("Producer close failed; error_type={ErrorType}",
                    error.GetType().Name);
            }
        }

        ThrowIfStopped(state, operation, cancellationToken);
        if (text.Length == 0)
        {
            throw new InvalidOperationException("Response ended without output.");
        }
        await session.SendAsync(
            new VoiceResponseOutputTextDoneMessage(
                operation.ResponseId,
                itemId,
                text.ToString(),
                plan.Voice),
            cancellationToken);
        ThrowIfStopped(state, operation, cancellationToken);
        await session.SendAsync(
            new VoiceResponseDoneMessage(operation.ResponseId),
            cancellationToken);
        operation.RecordCompleted();
        state.MarkTerminal(operation.ResponseId);
    }

    private async Task RunSelfCancellingResponseAsync(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        string text)
    {
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(
            operation.Cancellation.Token,
            state.Lifetime.Token);
        var cancellationToken = cancellation.Token;
        try
        {
            var itemId = VoiceIds.CreateItemId();
            var created = state.EnqueueInputResolution(async () =>
            {
                await AcquireGenerationAsync(state, operation, cancellationToken);
                await session.SendAsync(new VoiceResponseCreatedMessage(
                    operation.ResponseId, new[] { operation.InputItemId! }), cancellationToken);
                operation.ResponseStarted = true;
            }, operation.Cancellation.Token);
            await Task.Yield();
            await created;
            ThrowIfStopped(state, operation, cancellationToken);
            if (text.EnumerateRunes().Count() > 8_000)
            {
                throw new InvalidOperationException("Response text exceeds its output budget.");
            }
            await session.SendAsync(
                new VoiceResponseOutputTextDeltaMessage(
                    operation.ResponseId,
                    itemId,
                    text),
                cancellationToken);
            ThrowIfStopped(state, operation, cancellationToken);
            await session.SendAsync(
                new VoiceResponseCancelMessage(operation.ResponseId, "sample_self_correction"),
                cancellationToken);
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
        }
        catch (OperationCanceledException) when (operation.IsCancellationRequested || cancellationToken.IsCancellationRequested || !state.IsActive)
        {
        }
        catch (Exception exception)
        {
            _logger.LogWarning("Self-cancelling response failed; error_type={ErrorType}",
                exception.GetType().Name);
            await TrySendErrorAsync(session, state, operation, cancellationToken);
        }
        finally
        {
            operation.ReleaseGeneration();
            if (operation.TryFinish()) { RemoveOperation(state, operation.ResponseId); }
        }
    }

    private async Task TrySendErrorAsync(
        VoiceSession session, VoiceConnectionState state, ResponseOperation operation,
        CancellationToken cancellationToken)
    {
        if (operation.IsCancellationRequested || !state.IsActive) { return; }
        if (!operation.ResponseStarted)
        {
            operation.SelectOutcome(ResponseOutcome.Error);
            return;
        }
        try
        {
            ThrowIfStopped(state, operation, cancellationToken);
            await session.SendAsync(new VoiceErrorMessage(
                "generation_failed", "The response could not be generated.", operation.ResponseId),
                cancellationToken);
            operation.Commit(ResponseOutcome.Error);
        }
        catch (Exception error)
        {
            _logger.LogDebug("Could not report response failure; error_type={ErrorType}",
                error.GetType().Name);
        }
    }

    private (bool Owns, Task Completion, Task Notification) BeginTermination(
        VoiceConnectionState state, ResponseOutcome outcome)
    {
        var owns = state.TryBeginTermination(out var operations, out var completion);
        if (!owns) { return (false, completion, Task.CompletedTask); }
        foreach (var operation in operations)
        {
            operation.TryRequestCancellation(outcome);
        }
        // Start every operation's notification before waiting for any callback or worker.
        var notifications = operations.Select(NotifyCancellationAsync).ToArray();
        var notification = Task.WhenAll(notifications.Append(NotifyLifetimeAsync(state)));
        Observe(FinishTerminationAsync(state, operations, notification));
        return (true, completion, notification);
    }

    private async Task FinishTerminationAsync(
        VoiceConnectionState state, IReadOnlyList<ResponseOperation> operations, Task notification)
    {
        try
        {
            await notification;
            await Task.WhenAll(operations.Select(operation =>
                DrainOperationAsync(state, operation, Task.CompletedTask)));
            await state.WaitForInputResolutionsAsync();
        }
        finally { state.CompleteTermination(); }
    }

    private async Task NotifyLifetimeAsync(VoiceConnectionState state)
    {
        try { await state.Lifetime.CancelAsync(); }
        catch (Exception error)
        {
            _logger.LogWarning("Session cancellation callback failed; error_type={ErrorType}",
                error.GetType().Name);
        }
    }

    private async Task NotifyCancellationAsync(ResponseOperation operation)
    {
        try { await operation.NotifyCancellationAsync(); }
        catch (Exception error)
        {
            _logger.LogWarning("Response cancellation callback failed; error_type={ErrorType}",
                error.GetType().Name);
        }
    }

    private async Task DrainOperationAsync(
        VoiceConnectionState state, ResponseOperation operation, Task notification)
    {
        await notification;
        try
        {
            if (operation.Work is { } work) { await work; }
        }
        catch (Exception error)
        {
            _logger.LogDebug("Response cleanup failed; error_type={ErrorType}", error.GetType().Name);
        }
        finally { RemoveOperation(state, operation.ResponseId); }
    }

    private void RemoveOperation(VoiceConnectionState state, string responseId)
    {
        if (state.TryRemoveOperation(responseId, out var operation))
        {
            try { operation.Dispose(); }
            catch (Exception error)
            {
                _logger.LogWarning("Response disposal failed; error_type={ErrorType}",
                    error.GetType().Name);
            }
        }
    }

    private static void ThrowIfStopped(
        VoiceConnectionState state, ResponseOperation operation, CancellationToken token)
    {
        if (operation.IsCancellationRequested || !state.IsActive)
        {
            throw new OperationCanceledException(token);
        }
        token.ThrowIfCancellationRequested();
    }

    private static async Task AcquireGenerationAsync(
        VoiceConnectionState state, ResponseOperation operation, CancellationToken token)
    {
        await state.GenerationGate.WaitAsync(token);
        if (!operation.TryOwnGeneration(state.GenerationGate))
        {
            state.GenerationGate.Release();
            throw new OperationCanceledException(token);
        }
        ThrowIfStopped(state, operation, token);
    }

    internal async Task StopAsync()
    {
        try { await _shutdown.CancelAsync(); }
        catch (Exception error)
        {
            _logger.LogDebug("Terminal send cancellation failed; error_type={ErrorType}",
                error.GetType().Name);
        }
    }

    internal async Task DrainAsync()
    {
        while (true)
        {
            Task[] pending;
            lock (_observed) { pending = _observed.ToArray(); }
            if (pending.Length == 0) { return; }
            try { await Task.WhenAll(pending); }
            catch (Exception) { /* ObserveAsync records the diagnostic and releases ownership. */ }
            await Task.Yield();
        }
    }

    private async Task TrySendAsync(VoiceConnectionState state, Func<Task> send)
    {
        if (!state.IsActive)
        {
            return;
        }

        try
        {
            await send();
        }
        catch (OperationCanceledException) when (state.Lifetime.IsCancellationRequested)
        {
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Voice protocol message could not be sent");
        }
    }

    private async Task ObserveAsync(Task task)
    {
        try
        {
            await task;
        }
        catch (Exception exception)
        {
            _logger.LogDebug("Voice response cleanup failed; error_type={ErrorType}",
                exception.GetType().Name);
        }
        finally { lock (_observed) { _observed.Remove(task); } }
    }
}
