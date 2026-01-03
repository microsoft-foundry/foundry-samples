using Azure.AI.AgentServer.Core.Context;
using Azure.AI.AgentServer.Responses.Invocation;
using Microsoft.Extensions.DependencyInjection;

// Run Agent Server with customized agent invocation factory
// Uses DI to provide IAgentInvocation.
await AgentServerApplication.RunAsync(new ApplicationOptions(
    ConfigureServices: services => services.AddSingleton<IAgentInvocation, SystemUtilityAgentInvocation>(),
    TelemetrySourceName: "SystemUtilityAgent"
)).ConfigureAwait(false);
