// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

Env.NoClobber().TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT environment variable is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set.");

// A declaration exposes the tool schema to the model without providing an in-agent implementation.
// The resulting unterminated function call can therefore cross a workflow checkpoint boundary.
AIFunctionDeclaration simulateCrash = AIFunctionFactory.CreateDeclaration(
    name: "simulate_crash",
    description: "Terminate the current agent process to demonstrate durable workflow recovery. Call only when the user explicitly requests a crash recovery demonstration.",
    jsonSchema: JsonSerializer.SerializeToElement(new
    {
        type = "object",
        properties = new { },
        additionalProperties = false,
    }));

AIAgent crashAgent = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        // Recovery reconstructs the workflow in a new process, so executor identity must be stable.
        Id = "crash-recovery-agent",
        Name = "Crash Recovery Agent",
        Description = "An agent that demonstrates workflow recovery after an intentional process crash",
        ChatOptions = new()
        {
            ModelId = deployment,
            Instructions = """
                You are a crash recovery demonstration agent.
                Call simulate_crash exactly once only when the user explicitly asks you to demonstrate
                crash recovery. After the tool returns, explain briefly that the process was replaced
                and the workflow resumed from its checkpoint. For any other request, answer normally
                without calling the tool.
                """,
            Tools = [simulateCrash],
        },
    });

ExecutorBinding agentExecutor = crashAgent.BindAsExecutor(new AIAgentHostOptions
{
    EmitAgentUpdateEvents = true,
    EmitAgentResponseEvents = true,
    // Route the model's pending FunctionCallContent into the workflow instead of raising it to the
    // hosting client. AIAgentHostExecutor checkpoints that pending call before the tool executor runs.
    InterceptUnterminatedFunctionCalls = true,
});
var crashToolExecutor = new CrashToolExecutor();

AIAgent agent = new WorkflowBuilder(agentExecutor)
    // The tool result returns through the reverse edge with the original CallId, allowing the
    // restored Agent Executor to continue the same model turn after process replacement.
    .AddEdge(agentExecutor, crashToolExecutor)
    .AddEdge(crashToolExecutor, agentExecutor)
    .WithOutputFrom(agentExecutor)
    .Build()
    .AsAIAgent(
        id: "resilient-workflow",
        name: "resilient-workflow",
        includeExceptionDetails: true,
        includeWorkflowOutputsInResponse: true);

var builder = AgentHost.CreateBuilder(args);

// AgentServer must register durable background tasks on the first Responses registration.
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.ResilientBackground = true);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();

[SendsMessage(typeof(FunctionResultContent))]
internal sealed class CrashToolExecutor()
    : Executor<FunctionCallContent>("simulate-crash-tool")
{
    // This flag is deliberately process-local. It is set by workflow restoration, not persisted by
    // the sample, so the replacement process can distinguish recovery without an external marker.
    private bool _restoredFromCheckpoint;

    public override async ValueTask HandleAsync(
        FunctionCallContent message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        if (!string.Equals(message.Name, "simulate_crash", StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Unexpected function call '{message.Name}'.");
        }

        if (!this._restoredFromCheckpoint)
        {
            // Let hosting persist the completed Agent Executor superstep before terminating.
            await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
            Console.Out.Flush();
            Console.Error.Flush();
            Environment.Exit(70);
            throw new InvalidOperationException("Process termination did not stop execution.");
        }

        // Consume the restore signal so another call in this process does not masquerade as recovery.
        this._restoredFromCheckpoint = false;
        await context.SendMessageAsync(
            new FunctionResultContent(
                message.CallId,
                "Crash recovery succeeded. The workflow resumed the pending tool call from its checkpoint."),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    protected override ValueTask OnCheckpointRestoredAsync(
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // The pending FunctionCallContent was already saved by the Agent Executor superstep. It is
        // delivered again after this hook, so the executor can return the result instead of crashing.
        this._restoredFromCheckpoint = true;
        return ValueTask.CompletedTask;
    }
}
