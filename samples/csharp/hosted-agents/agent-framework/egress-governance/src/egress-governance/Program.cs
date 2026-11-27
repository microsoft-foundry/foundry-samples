// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Core;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

var probe = new GovernanceProbe();
var reply = new GovernanceReply();
var agent = new WorkflowBuilder(probe)
    .AddEdge(probe, reply)
    .WithOutputFrom(reply)
    .Build()
    .AsAIAgent(name: "egress-governance", includeWorkflowOutputsInResponse: true);

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());
builder.Build().Run();

internal sealed class GovernanceProbe()
    : ChatProtocolExecutor("governance-probe", new() { AutoSendTurnToken = false })
{
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        base.ConfigureProtocol(protocolBuilder).SendsMessage<string>();

    protected override ValueTask TakeTurnAsync(
        List<ChatMessage> messages,
        IWorkflowContext context,
        bool? emitEvents,
        CancellationToken cancellationToken = default) =>
        context.SendMessageAsync("probe", cancellationToken: cancellationToken);
}

[YieldsOutput(typeof(string))]
internal sealed class GovernanceReply() : Executor<string>("governance-reply")
{
    public override ValueTask HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default) =>
        context.YieldOutputAsync("Governance sample ready.", cancellationToken);
}
