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
        string reason) =>
        TrySendAsync(
            state,
            () => state.EnqueueInputResolution(() => session.SendAsync(
                new VoiceResponseNoneMessage(new[] { inputItemId }, reason),
                state.Lifetime.Token)));

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
        if (state.TryRemoveOperation(responseId, out var operation))
        {
            operation.SelectOutcome(outcome);
            Observe(CancelAndDisposeAsync(operation));
        }
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
                ? state.EnqueueInputResolution(() => session.SendAsync(
                    new VoiceResponseCreatedMessage(
                        operation.ResponseId,
                        new[] { operation.InputItemId }),
                    cancellationToken))
                : Task.CompletedTask;
            await Task.Yield();
            await created;
            cancellationToken.ThrowIfCancellationRequested();

            await SendOutputAsync(session, state, operation, plan, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested || !state.IsActive)
        {
        }
        catch (Exception exception)
        {
            operation.RecordFailure(exception);
            _logger.LogError(exception, "Voice response {ResponseId} failed", operation.ResponseId);
            await TrySendErrorAsync(session, state, operation.ResponseId);
        }
        finally
        {
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
            cancellationToken.ThrowIfCancellationRequested();
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
                // Let incoming interruption and timeout events run between words.
                await Task.Yield();
            }
        }

        await session.SendAsync(
            new VoiceResponseOutputTextDoneMessage(
                operation.ResponseId,
                itemId,
                text.ToString(),
                plan.Voice),
            cancellationToken);
        state.MarkTerminal(operation.ResponseId);
        await session.SendAsync(
            new VoiceResponseDoneMessage(operation.ResponseId),
            cancellationToken);
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
            var created = state.EnqueueInputResolution(() => session.SendAsync(
                new VoiceResponseCreatedMessage(
                    operation.ResponseId,
                    new[] { operation.InputItemId! }),
                cancellationToken));
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
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested || !state.IsActive)
        {
        }
        catch (Exception exception)
        {
            _logger.LogError(exception, "Self-cancelling response failed");
            RemoveOperation(state, operation.ResponseId);
        }
    }

    private async Task TrySendErrorAsync(
        VoiceSession session,
        VoiceConnectionState state,
        string responseId)
    {
        try
        {
            if (!state.IsActive)
            {
                return;
            }
            await session.SendAsync(
                new VoiceErrorMessage(
                    "generation_failed",
                    "The response could not be generated.",
                    responseId),
                state.Lifetime.Token);
        }
        catch (Exception exception)
        {
            _logger.LogDebug(exception, "Could not report response failure");
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
                await state.Lifetime.CancelAsync();
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
            operation.Dispose();
        }
    }

    private async Task CancelAndDisposeAsync(ResponseOperation operation)
    {
        try
        {
            await operation.Cancellation.CancelAsync();
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
            _logger.LogDebug(exception, "Response cancellation failed");
        }
        finally
        {
            operation.Dispose();
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
            _logger.LogDebug(exception, "Voice response cleanup failed");
        }
    }
}
