namespace HelloWorldA365.AgentLogic;

using HelloWorldA365.AgentLogic.SemanticKernel;
using HelloWorldA365.Models;

public sealed class AgentLogicServiceFactory(
    IConfiguration configuration,
    IServiceProvider serviceProvider,
    ILogger<AgentLogicServiceFactory> logger,
    SemanticKernelAgentLogicServiceFactory semanticKernelAgentLogicServiceFactory)
{
    private readonly string implementationType = configuration["Type"] ?? "SK";

    /// <summary>
    /// Gets or creates a AgentLogicService instance for the specified agent.
    /// The implementation (Semantic Kernel vs OpenAI) is determined by the Type configuration setting.
    /// </summary>
    /// <param name="agent">The agent to get the service for.</param>
    /// <returns>A AgentLogicService instance.</returns>
    public async Task<IAgentLogicService> GetService(AgentMetadata agent)
    {
        // Note: We should not cache the service per bot.
        // The service must be created per turn. Context is not desined to be shared across turns.
        return await CreateServiceAsync(agent);
    }

    private async Task<IAgentLogicService> CreateServiceAsync(AgentMetadata agent)
    {
        switch (implementationType.ToUpperInvariant())
        {
            case "SK":
            case "SEMANTICKERNEL":
            default:
                logger.LogInformation("Creating Semantic Kernel-based AgentLogicService for agent {AgentId}", agent.AgentId);
                return await semanticKernelAgentLogicServiceFactory.CreateAsync(agent);

        }
    }
}