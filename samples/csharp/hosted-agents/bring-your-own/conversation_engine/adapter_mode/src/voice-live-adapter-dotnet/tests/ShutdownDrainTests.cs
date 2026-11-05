// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Azure.AI.AgentServer.Invocations;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class ShutdownDrainTests
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(3);

    [TestCase(false)]
    [TestCase(true)]
    public async Task CancelledSessionEndJoin_RetainsCleanupForScopeDisposal(bool noInput)
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton(new InvocationAdapter(new EchoHttpAgent()));
        services.AddVoice<ScopedVoiceAgent>();
        await using var provider = services.BuildServiceProvider();
        var scope = provider.CreateAsyncScope();
        var agent = (ScopedVoiceAgent)scope.ServiceProvider.GetRequiredService<InvocationWebSocketHandler>();
        var session = new CleanupSession();
        Task? ending = null;
        Task? disposal = null;
        try
        {
            await agent.Start(session);
            await agent.Input(session);
            await session.OutputStarted.Task.WaitAsync(Limit);
            if (noInput)
            {
                await agent.NoInput(session).WaitAsync(Limit);
                Assert.That(session.Messages.OfType<VoiceEndCallMessage>().Count(), Is.EqualTo(1));
            }
            ending = agent.End(session);
            await session.CleanupStarted.Task.WaitAsync(Limit);
            using var cancellation = new CancellationTokenSource();
            await cancellation.CancelAsync();
            Assert.That(async () => await ending.WaitAsync(cancellation.Token),
                Throws.InstanceOf<OperationCanceledException>());
            disposal = scope.DisposeAsync().AsTask();
            Assert.ThrowsAsync<TimeoutException>(async () =>
                await disposal.WaitAsync(TimeSpan.FromMilliseconds(100)));
            Assert.That(session.CleanupFinished.Task.IsCompleted, Is.False);
        }
        finally
        {
            session.ReleaseCleanup.TrySetResult();
            if (ending is not null)
            {
                await ending.WaitAsync(Limit);
            }
            disposal ??= scope.DisposeAsync().AsTask();
            await disposal.WaitAsync(Limit);
        }
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
    }


    [TestCase(false)]
    [TestCase(true)]
    public async Task SdkOwnedScope_WaitsForDisconnectedResponseCleanup(bool alreadyDisconnected)
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton(new InvocationAdapter(new EchoHttpAgent()));
        services.AddVoice<ScopedVoiceAgent>();
        await using var provider = services.BuildServiceProvider();
        var scope = provider.CreateAsyncScope();
        var agent = (ScopedVoiceAgent)scope.ServiceProvider.GetRequiredService<InvocationWebSocketHandler>();
        var session = new CleanupSession();
        await agent.Start(session);
        await agent.Input(session);
        await session.OutputStarted.Task.WaitAsync(Limit);
        agent.Terminating(session);
        if (alreadyDisconnected)
        {
            await session.CleanupStarted.Task.WaitAsync(Limit);
        }
        var disposal = scope.DisposeAsync().AsTask();
        try
        {
            await session.CleanupStarted.Task.WaitAsync(Limit);
            Assert.ThrowsAsync<TimeoutException>(async () =>
                await disposal.WaitAsync(TimeSpan.FromMilliseconds(100)));
            Assert.That(session.CleanupFinished.Task.IsCompleted, Is.False);
        }
        finally
        {
            session.ReleaseCleanup.TrySetResult();
            await disposal.WaitAsync(Limit);
            await session.CleanupFinished.Task.WaitAsync(Limit);
        }
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
    }

    private sealed class CleanupSession : CapturingVoiceSession
    {
        internal TaskCompletionSource OutputStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource CleanupStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource ReleaseCleanup { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource CleanupFinished { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public override async Task SendAsync(VoiceOutboundMessage message, CancellationToken token = default)
        {
            if (message is VoiceResponseOutputTextDeltaMessage)
            {
                OutputStarted.TrySetResult();
                try
                {
                    await Task.Delay(Timeout.Infinite, token);
                }
                finally
                {
                    CleanupStarted.TrySetResult();
                    await ReleaseCleanup.Task;
                    CleanupFinished.TrySetResult();
                }
            }
            await base.SendAsync(message, token);
        }
    }

    private sealed class ScopedVoiceAgent : VoiceAgent
    {
        public ScopedVoiceAgent(ILogger<VoiceAgent> logger, InvocationAdapter backend)
            : base(logger, backend) { }

        internal Task Start(VoiceSession session) => OnSessionStartAsync(session,
            new VoiceSessionStartEvent("m_start", DateTimeOffset.UtcNow, "1.0", reconnect: false,
                new VoiceResponseTimeouts(1000, 1000, 30000), greeting: null,
                noInputTimeoutMs: null, caller: null), CancellationToken.None);

        internal Task Input(VoiceSession session) => OnUserMessageAsync(session,
            new VoiceUserMessageEvent("m_user", DateTimeOffset.UtcNow, "in_shutdown",
                new[] { new VoiceInputTextPart("test") }), CancellationToken.None);

        internal Task NoInput(VoiceSession session) => OnUserNoInputAsync(session,
            new VoiceUserNoInputEvent("m_no_input", DateTimeOffset.UtcNow, "in_silence", 3),
            CancellationToken.None);

        internal Task End(VoiceSession session) => OnSessionEndAsync(session,
            new VoiceSessionEndEvent("m_end", DateTimeOffset.UtcNow, "test_complete"),
            CancellationToken.None);

        internal void Terminating(VoiceSession session) => OnConnectionTerminating(session);
    }
}
