// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text;
using Azure.AI.AgentServer.Invocations.Voice;

namespace VoiceHostedAgent;

/// <summary>Coordinates bounded response execution and its Voice wire lifecycle.</summary>
internal sealed class VoiceResponseCoordinator
{
    private static readonly AsyncLocal<ResponseOperation?> s_currentOperation = new();
    private readonly ILogger<VoiceAgent> _logger;

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

        operation.TryStart(() => RunAsCurrentOperationAsync(
            operation,
            () => RunSelfCancellingResponseAsync(session, state, operation, text)));
    }

    internal Task SendNoneAsync(
        VoiceSession session,
        VoiceConnectionState state,
        string inputItemId,
        string reason)
    {
        if (!state.IsActive)
        {
            return Task.CompletedTask;
        }
        var operation = new ResponseOperation(VoiceIds.CreateResponseId(), inputItemId);
        if (!state.TryReserveOperation(operation, declineOnly: true))
        {
            operation.Dispose();
            if (!state.IsActive)
            {
                return Task.CompletedTask;
            }
            throw new InvalidOperationException("Connection terminal-send capacity exceeded.");
        }
        operation.TryStart(() => RunAsCurrentOperationAsync(operation, async () =>
        {
            using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(
                operation.Cancellation.Token, state.Lifetime.Token);
            try
            {
                var send = state.EnqueueInputResolution(() => session.SendAsync(
                    new VoiceResponseNoneMessage(new[] { inputItemId }, reason), cancellation.Token),
                    operation.Cancellation.Token);
                await Task.Yield();
                await send;
                operation.SelectOutcome(ResponseOutcome.None);
            }
            catch (OperationCanceledException) when (
                operation.IsCancellationRequested || cancellation.IsCancellationRequested || !state.IsActive)
            {
            }
            catch (Exception exception)
            {
                _logger.LogWarning("Voice decline failed; error_type={ErrorType}", exception.GetType().FullName);
            }
            finally
            {
                RemoveOperation(state, operation.ResponseId);
            }
        }));
        return operation.Work ?? Task.CompletedTask;
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
                "Could not request proactive response {ResponseId}; error_type={ErrorType}",
                responseId, exception.GetType().FullName);
        }
    }

    internal async Task AcceptProactiveAsync(
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
            await TrySendAsync(
                state,
                () => session.SendAsync(
                    new VoiceResponseCancelMessage(responseId, "capacity_exceeded"),
                    state.Lifetime.Token));
        }
    }

    internal void CancelOperation(
        VoiceConnectionState state,
        string responseId,
        ResponseOutcome outcome)
    {
        if (state.TryGetOperation(responseId, out var operation) && operation.TryRequestCancellation(outcome))
        {
            // The inbound terminal event has already closed the Bridge generation.
            operation.ReleaseGeneration();
            Observe(CancelTrackedOperationAsync(state, operation));
        }
    }

    private async Task CancelTrackedOperationAsync(VoiceConnectionState state, ResponseOperation operation)
    {
        await CancelAndDisposeAsync(operation);
        RemoveOperation(state, operation.ResponseId);
    }

    internal async Task TerminateAndEndCallAsync(
        VoiceSession session,
        VoiceConnectionState state,
        VoiceEndCallMode mode,
        CancellationToken cancellationToken,
        string reason = "sample_completed")
    {
        if (await TerminateAsync(state, ResponseOutcome.EndCall))
        {
            await session.SendAsync(
                new VoiceEndCallMessage(reason, mode),
                cancellationToken);
        }
    }

    internal Task TerminateSessionAsync(
        VoiceConnectionState state,
        ResponseOutcome outcome) =>
        TerminateAsync(state, outcome);

    internal void Observe(Task task) => _ = ObserveAsync(task);

    private void StartReservedResponse(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        ResponsePlan plan)
    {
        operation.TryStart(() => RunAsCurrentOperationAsync(
            operation,
            () => RunResponseAsync(session, state, operation, plan)));
    }

    private static async Task RunAsCurrentOperationAsync(
        ResponseOperation operation,
        Func<Task> work)
    {
        var previous = s_currentOperation.Value;
        s_currentOperation.Value = operation;
        try
        {
            await work();
        }
        finally
        {
            s_currentOperation.Value = previous;
        }
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
            // Enqueue before yielding: background worker scheduling must not reorder inputs.
            var created = operation.InputItemId is not null
                ? state.EnqueueInputResolution(async () =>
                {
                    await AcquireGenerationAsync(state, operation, cancellationToken);
                    await session.SendAsync(new VoiceResponseCreatedMessage(
                        operation.ResponseId, new[] { operation.InputItemId }), cancellationToken);
                }, operation.Cancellation.Token)
                : AcquireGenerationAsync(state, operation, cancellationToken);
            await Task.Yield();
            await created;
            cancellationToken.ThrowIfCancellationRequested();

            await SendOutputAsync(session, state, operation, plan, cancellationToken);
        }
        catch (OperationCanceledException) when (
            operation.IsCancellationRequested || cancellationToken.IsCancellationRequested || !state.IsActive)
        {
        }
        catch (Exception exception)
        {
            if (operation.IsCancellationRequested || cancellationToken.IsCancellationRequested || !state.IsActive)
            {
                _logger.LogDebug("Response cleanup failed after termination; error_type={ErrorType}",
                    exception.GetType().FullName);
                return;
            }
            operation.RecordFailure(exception);
            _logger.LogError("Voice response {ResponseId} failed; error_type={ErrorType}",
                operation.ResponseId, exception.GetType().FullName);
            await TrySendErrorAsync(session, state, operation, cancellationToken);
        }
        finally
        {
            operation.ReleaseGeneration();
            RemoveOperation(state, operation.ResponseId);
        }
    }

    private static async Task SendOutputAsync(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        ResponsePlan plan,
        CancellationToken cancellationToken)
    {
        var itemId = VoiceIds.CreateItemId();
        var text = new StringBuilder();
        await foreach (var chunk in plan.Chunks.WithCancellation(cancellationToken))
        {
            EnsureActive(state, operation, cancellationToken);
            text.Append(chunk);
            if (plan.Streaming)
            {
                await session.SendAsync(
                    new VoiceResponseOutputTextDeltaMessage(
                        operation.ResponseId,
                        itemId,
                        chunk,
                        plan.Voice),
                    cancellationToken);
                EnsureActive(state, operation, cancellationToken);
                // Let incoming interruption and timeout events run between words.
                await Task.Yield();
            }
        }

        EnsureActive(state, operation, cancellationToken);
        await session.SendAsync(
            new VoiceResponseOutputTextDoneMessage(
                operation.ResponseId,
                itemId,
                text.ToString(),
                plan.Voice),
            cancellationToken);
        EnsureActive(state, operation, cancellationToken);
        state.MarkTerminal(operation.ResponseId);
        EnsureActive(state, operation, cancellationToken);
        await session.SendAsync(
            new VoiceResponseDoneMessage(operation.ResponseId),
            cancellationToken);
        EnsureActive(state, operation, cancellationToken);
        operation.RecordCompleted();
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
            }, operation.Cancellation.Token);
            await Task.Yield();
            await created;
            cancellationToken.ThrowIfCancellationRequested();
            await session.SendAsync(
                new VoiceResponseOutputTextDeltaMessage(
                    operation.ResponseId,
                    itemId,
                    text),
                cancellationToken);
            await session.SendAsync(
                new VoiceResponseCancelMessage(
                    operation.ResponseId,
                    "sample_self_correction"),
                cancellationToken);
        }
        catch (OperationCanceledException) when (
            operation.IsCancellationRequested || cancellationToken.IsCancellationRequested || !state.IsActive)
        {
        }
        catch (Exception exception)
        {
            _logger.LogError("Self-cancelling response failed; error_type={ErrorType}", exception.GetType().FullName);
            RemoveOperation(state, operation.ResponseId);
        }
    }

    private static void EnsureActive(
        VoiceConnectionState state, ResponseOperation operation, CancellationToken token)
    {
        if (operation.IsCancellationRequested || !state.IsActive)
        {
            throw new OperationCanceledException(token);
        }
        token.ThrowIfCancellationRequested();
    }

    private async Task TrySendErrorAsync(
        VoiceSession session,
        VoiceConnectionState state,
        ResponseOperation operation,
        CancellationToken cancellationToken)
    {
        try
        {
            EnsureActive(state, operation, cancellationToken);
            await session.SendAsync(
                new VoiceErrorMessage(
                    "generation_failed",
                    "The response could not be generated.",
                    operation.ResponseId),
                cancellationToken);
        }
        catch (Exception exception)
        {
            _logger.LogDebug("Could not report response failure; error_type={ErrorType}", exception.GetType().FullName);
        }
    }

    private async Task<bool> TerminateAsync(
        VoiceConnectionState state,
        ResponseOutcome outcome)
    {
        var ownsTermination = state.TryBeginTermination(
            out var operations,
            out var completion);
        if (ownsTermination)
        {
            try
            {
                foreach (var operation in operations)
                {
                    operation.SelectOutcome(outcome);
                }
                // The state snapshot now belongs to this terminator. Cancellation callbacks
                // may run inline, so select outcomes first and never cancel under the state lock.
                await NotifyCancellationAsync(state.Lifetime);
                await Task.WhenAll(operations.Select(CancelAndDisposeAsync));
                await state.WaitForInputResolutionsAsync();
            }
            finally
            {
                state.CompleteTermination();
            }
        }

        await completion;
        return ownsTermination;
    }

    private static void RemoveOperation(
        VoiceConnectionState state,
        string responseId)
    {
        if (state.TryRemoveOperation(responseId, out var operation))
        {
            operation.ReleaseGeneration();
            operation.Dispose();
        }
    }

    private async Task CancelAndDisposeAsync(ResponseOperation operation)
    {
        try
        {
            await NotifyCancellationAsync(operation.Cancellation);
            var work = operation.Work;
            if (work is not null &&
                !ReferenceEquals(s_currentOperation.Value, operation) &&
                work.Id != Task.CurrentId)
            {
                await work;
            }
        }
        catch (Exception exception)
        {
            _logger.LogDebug("Response cancellation failed; error_type={ErrorType}", exception.GetType().FullName);
        }
        finally
        {
            operation.ReleaseGeneration();
            operation.Dispose();
        }
    }

    private static async Task AcquireGenerationAsync(
        VoiceConnectionState state, ResponseOperation operation, CancellationToken token)
    {
        if (!await operation.TryAcquireGenerationAsync(state.GenerationGate, token))
        {
            throw new OperationCanceledException(token);
        }
    }

    private async Task NotifyCancellationAsync(CancellationTokenSource cancellation)
    {
        try
        {
            await cancellation.CancelAsync();
        }
        catch (Exception exception)
        {
            // Notification failures must not bypass joining the response workers.
            _logger.LogWarning("Cancellation notification failed; error_type={ErrorType}",
                exception.GetType().FullName);
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
            _logger.LogWarning("Voice protocol message could not be sent; error_type={ErrorType}", exception.GetType().FullName);
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
            _logger.LogDebug("Voice response cleanup failed; error_type={ErrorType}", exception.GetType().FullName);
        }
    }
}
