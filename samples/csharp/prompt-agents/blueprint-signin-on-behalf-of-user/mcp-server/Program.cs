using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Azure.Functions.Worker.Extensions.Mcp;
using Microsoft.Extensions.Hosting;

FunctionsApplication.CreateBuilder(args).Build().Run();

public sealed class GreetingTool
{
    [Function(nameof(Greet))]
    public string Greet(
        [McpToolTrigger("greet", "Greets the caller.")]
        ToolInvocationContext invocation,
        FunctionContext functionContext) =>
        $"Hello from the agent's tool. Invocation ID: {functionContext.InvocationId}";
}
