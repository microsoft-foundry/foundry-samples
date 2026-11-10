// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Collections.Concurrent;
using Azure.AI.AgentServer.Invocations.Voice;

namespace VoiceHostedAgent.Tests;

internal class CapturingVoiceSession : VoiceSession
{
    private readonly ConcurrentQueue<VoiceOutboundMessage> _messages = new();

    internal IReadOnlyList<VoiceOutboundMessage> Messages => _messages.ToArray();

    internal void ClearMessages() => _messages.Clear();

    public override Task SendAsync(
        VoiceOutboundMessage message,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        _messages.Enqueue(message);
        return Task.CompletedTask;
    }
}

internal sealed class BlockingOutputVoiceSession : CapturingVoiceSession
{
    internal bool BlockOutput { get; set; } = true;
    internal int AllowedDeltaCount { get; set; }
    private int _deltaCount;

    internal TaskCompletionSource OutputStarted { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal TaskCompletionSource OutputCancelled { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    public override async Task SendAsync(
        VoiceOutboundMessage message,
        CancellationToken cancellationToken = default)
    {
        if (message is VoiceResponseOutputTextDeltaMessage &&
            Interlocked.Increment(ref _deltaCount) <= AllowedDeltaCount)
        {
            await base.SendAsync(message, cancellationToken);
            return;
        }
        if (BlockOutput &&
            message is VoiceResponseOutputTextDeltaMessage or VoiceResponseOutputTextDoneMessage)
        {
            OutputStarted.TrySetResult();
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            }
            finally
            {
                if (cancellationToken.IsCancellationRequested)
                {
                    OutputCancelled.TrySetResult();
                }
            }
        }
        await base.SendAsync(message, cancellationToken);
    }
}

internal sealed class FailingOutputVoiceSession : CapturingVoiceSession
{
    public override Task SendAsync(
        VoiceOutboundMessage message,
        CancellationToken cancellationToken = default) =>
        message is VoiceResponseOutputTextDeltaMessage
            ? Task.FromException(new InvalidOperationException("Test output failure."))
            : base.SendAsync(message, cancellationToken);
}

internal sealed class BlockingReadyVoiceSession : VoiceSession
{
    private readonly ConcurrentQueue<VoiceOutboundMessage> _messages = new();

    internal TaskCompletionSource ReadySendStarted { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal TaskCompletionSource ReleaseReadySend { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal IReadOnlyList<VoiceOutboundMessage> Messages => _messages.ToArray();

    public override async Task SendAsync(
        VoiceOutboundMessage message,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (message is VoiceSessionReadyMessage)
        {
            ReadySendStarted.TrySetResult();
            await ReleaseReadySend.Task.WaitAsync(cancellationToken);
        }
        _messages.Enqueue(message);
    }
}

internal sealed class BlockingResponseDoneVoiceSession : VoiceSession
{
    private readonly ConcurrentQueue<VoiceOutboundMessage> _messages = new();

    internal TaskCompletionSource ResponseDoneSendStarted { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal TaskCompletionSource ReleaseResponseDoneSend { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal TaskCompletionSource ResponseDoneSendCancelled { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal IReadOnlyList<VoiceOutboundMessage> Messages => _messages.ToArray();

    internal void ClearMessages() => _messages.Clear();

    public override async Task SendAsync(
        VoiceOutboundMessage message,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (message is VoiceResponseDoneMessage)
        {
            ResponseDoneSendStarted.TrySetResult();
            try
            {
                await ReleaseResponseDoneSend.Task.WaitAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                ResponseDoneSendCancelled.TrySetResult();
                throw;
            }
        }
        _messages.Enqueue(message);
    }
}

/// <summary>Lets tests run later response workers before earlier ones.</summary>
internal sealed class PausedResponseContext : SynchronizationContext
{
    private readonly List<(SendOrPostCallback Callback, object? State)> _callbacks = new();
    private bool _released;

    public override void Post(SendOrPostCallback callback, object? state)
    {
        lock (_callbacks)
        {
            if (!_released)
            {
                _callbacks.Add((callback, state));
                return;
            }
        }
        ThreadPool.QueueUserWorkItem(_ => callback(state));
    }

    internal void RunInReverseOrder()
    {
        (SendOrPostCallback Callback, object? State)[] callbacks;
        lock (_callbacks)
        {
            // Reverse initial worker dispatch only. Later word-send continuations run normally.
            _released = true;
            callbacks = _callbacks.ToArray();
            _callbacks.Clear();
        }
        foreach (var (callback, state) in callbacks.Reverse())
        {
            callback(state);
        }
    }
}

internal sealed class BlockingCreatedVoiceSession : CapturingVoiceSession
{
    internal TaskCompletionSource CreatedSendStarted { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal TaskCompletionSource ReleaseCreatedSend { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    public override async Task SendAsync(
        VoiceOutboundMessage message,
        CancellationToken cancellationToken = default)
    {
        if (message is VoiceResponseCreatedMessage { InReplyTo: not null } created &&
            created.InReplyTo.Contains("in_first"))
        {
            CreatedSendStarted.TrySetResult();
            await ReleaseCreatedSend.Task.WaitAsync(cancellationToken);
        }
        await base.SendAsync(message, cancellationToken);
    }
}
