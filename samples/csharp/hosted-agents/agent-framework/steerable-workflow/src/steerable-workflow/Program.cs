// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Azure.AI.AgentServer.Core;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

Env.NoClobber().TraversePath().Load();

// The same probe is shared by the cancellable and steered executors. If the queued turn starts
// before the cancelled superstep finishes unwinding, Maximum becomes 2 and the demo fails loudly.
var concurrency = new ConcurrencyProbe();
var input = new SteeringInputExecutor();
var checkpoint = new CheckpointExecutor();
var longRunning = new LongRunningExecutor(concurrency);
var steered = new SteeredOutputExecutor(concurrency);
var echo = new EchoOutputExecutor();

AIAgent agent = new WorkflowBuilder(input)
    // The input executor targets exactly one branch based on the first token in the request.
    .AddEdge(input, checkpoint)
    .AddEdge(input, steered)
    .AddEdge(input, echo)
    // first:<token> must cross a completed superstep before entering cancellable work.
    .AddEdge(checkpoint, longRunning)
    .WithOutputFrom(checkpoint, longRunning, steered, echo)
    .Build()
    .AsAIAgent(
        id: "steerable-workflow",
        name: "steerable-workflow",
        includeExceptionDetails: true,
        includeWorkflowOutputsInResponse: true);

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(
    agent,
    configure: options =>
    {
        // These are host-level AgentServer choices and must be set on the first registration.
        // Resilience pairs workflow checkpoints with stored response snapshots; steering queues
        // a second input instead of rejecting the active conversation as locked.
        options.ResilientBackground = true;
        options.SteerableConversations = true;
    });
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();

internal static class SteeringState
{
    // A named shared scope lets each executor read state written by a different executor.
    public const string Scope = "steering";
    public const string Key = "state";
}

internal sealed class SteeringWorkflowState
{
    public int Turn { get; set; }

    public int CheckpointNumber { get; set; }

    public string Token { get; set; } = "";
}

internal sealed record FirstTurn(string Token);

internal sealed record SteeredTurn(string Token);

internal sealed record EchoTurn(string Token);

internal sealed record LongRunningTurn(string Token);

internal sealed class SteeringInputExecutor()
    : ChatProtocolExecutor("steering-input", new() { AutoSendTurnToken = false })
{
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        base.ConfigureProtocol(protocolBuilder)
            .SendsMessage<FirstTurn>()
            .SendsMessage<SteeredTurn>()
            .SendsMessage<EchoTurn>();

    protected override async ValueTask TakeTurnAsync(
        List<ChatMessage> messages,
        IWorkflowContext context,
        bool? emitEvents,
        CancellationToken cancellationToken = default)
    {
        string request = messages.LastOrDefault()?.Text
            ?? throw new InvalidOperationException("The steerable workflow requires an input message.");
        string[] parts = request.Split(':', 2, StringSplitOptions.TrimEntries);
        if (parts.Length != 2 || string.IsNullOrWhiteSpace(parts[1]))
        {
            throw new InvalidOperationException("Expected '<mode>:<token>'.");
        }

        SteeringWorkflowState state =
            await context.ReadStateAsync<SteeringWorkflowState>(
                SteeringState.Key,
                SteeringState.Scope,
                cancellationToken).ConfigureAwait(false)
            ?? new();

        // This update is committed when the input superstep completes. Other executors see it in
        // the next superstep, and a later steering turn sees it after the session is restored.
        state.Turn++;
        state.Token = parts[1];
        await context.QueueStateUpdateAsync(
            SteeringState.Key,
            state,
            SteeringState.Scope,
            cancellationToken).ConfigureAwait(false);

        object message = parts[0] switch
        {
            // first enters the checkpoint-producing branch; steer confirms restored state after
            // pending work resumes; echo exists only for inexpensive CI and readiness checks.
            "first" => new FirstTurn(parts[1]),
            "steer" => new SteeredTurn(parts[1]),
            "echo" => new EchoTurn(parts[1]),
            _ => throw new InvalidOperationException(
                $"Unknown mode '{parts[0]}'. Expected first, steer, or echo."),
        };
        await context.SendMessageAsync(message, cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}

[SendsMessage(typeof(LongRunningTurn))]
[YieldsOutput(typeof(string))]
internal sealed class CheckpointExecutor()
    : Executor<FirstTurn>("checkpoint")
{
    public override async ValueTask HandleAsync(
        FirstTurn message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        SteeringWorkflowState state =
            await context.ReadStateAsync<SteeringWorkflowState>(
                SteeringState.Key,
                SteeringState.Scope,
                cancellationToken).ConfigureAwait(false)
            ?? throw new InvalidOperationException("Steering state was not initialized.");

        // Queueing state, output, and the long-running message in this executor lets the superstep
        // complete first. Hosting can then pair this workflow checkpoint with the stored response
        // before the next executor begins cancellable work.
        state.CheckpointNumber++;
        await context.QueueStateUpdateAsync(
            SteeringState.Key,
            state,
            SteeringState.Scope,
            cancellationToken).ConfigureAwait(false);
        await context.YieldOutputAsync(
            $"CHECKPOINT-SAVED:{state.CheckpointNumber}:{message.Token}",
            cancellationToken).ConfigureAwait(false);
        await context.SendMessageAsync(
            new LongRunningTurn(message.Token),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}

[YieldsOutput(typeof(string))]
internal sealed class LongRunningExecutor(ConcurrencyProbe concurrency)
    : Executor<LongRunningTurn>("long-running")
{
    public override async ValueTask HandleAsync(
        LongRunningTurn message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        concurrency.Enter();
        try
        {
            // The first handler cancels this delay when steering arrives. The queued turn then
            // resumes from the prior checkpoint, replays this pending executor, and completes it.
            await Task.Delay(
                TimeSpan.FromSeconds(GetDelaySeconds()),
                cancellationToken).ConfigureAwait(false);
            await context.YieldOutputAsync(
                $"FIRST-NATURAL-COMPLETE:{message.Token}",
                cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            concurrency.Exit();
        }
    }

    private static int GetDelaySeconds()
    {
        const int DefaultDelaySeconds = 30;
        string? value = Environment.GetEnvironmentVariable("LONG_RUNNING_DELAY_SECONDS");
        return int.TryParse(
            value,
            NumberStyles.None,
            CultureInfo.InvariantCulture,
            out int seconds)
            && seconds > 0
                ? seconds
                : DefaultDelaySeconds;
    }
}

[YieldsOutput(typeof(string))]
internal sealed class SteeredOutputExecutor(ConcurrencyProbe concurrency)
    : Executor<SteeredTurn>("steered-output")
{
    public override async ValueTask HandleAsync(
        SteeredTurn message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        concurrency.Enter();
        try
        {
            // This state came from the checkpoint committed before the cancelled long-running
            // superstep. Turn must now be 2 because the queued steering input ran on the same
            // restored WorkflowSession.
            SteeringWorkflowState state =
                await context.ReadStateAsync<SteeringWorkflowState>(
                    SteeringState.Key,
                    SteeringState.Scope,
                    cancellationToken).ConfigureAwait(false)
                ?? throw new InvalidOperationException("Steering state was not restored.");

            await context.YieldOutputAsync(
                $"STEERED-COMPLETE:{message.Token}:CHECKPOINT-{state.CheckpointNumber}:" +
                $"SESSION-TURN-{state.Turn}:MAX-CONCURRENCY-{concurrency.Maximum}",
                cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            concurrency.Exit();
        }
    }
}

[YieldsOutput(typeof(string))]
internal sealed class EchoOutputExecutor()
    : Executor<EchoTurn>("echo-output")
{
    public override ValueTask HandleAsync(
        EchoTurn message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default) =>
        context.YieldOutputAsync($"ECHO-COMPLETE:{message.Token}", cancellationToken);
}

internal sealed class ConcurrencyProbe
{
    private int _active;
    private int _maximum;

    public int Maximum => Volatile.Read(ref this._maximum);

    public void Enter()
    {
        int active = Interlocked.Increment(ref this._active);

        // Lock-free maximum tracking keeps the probe correct if a regression allows both
        // executors to overlap. The expected value for a valid steering run is exactly 1.
        int current;
        do
        {
            current = Volatile.Read(ref this._maximum);
            if (active <= current)
            {
                return;
            }
        }
        while (Interlocked.CompareExchange(ref this._maximum, active, current) != current);
    }

    public void Exit() => Interlocked.Decrement(ref this._active);
}
