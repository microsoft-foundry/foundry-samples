namespace HelloWorldA365.AgentLogic.SemanticKernel;

using Azure.Core;
using Azure.Identity;
using HelloWorldA365.AgentLogic.AuthCache;
using HelloWorldA365.Mcp;
using HelloWorldA365.Models; // added for PresenceState
using HelloWorldA365.Services;
using Microsoft.Agents.A365.Tooling.Extensions.SemanticKernel.Services;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.App.UserAuth;
using Microsoft.SemanticKernel;

/// <summary>
/// There are still some work left here:
/// 1- The factory structure doesn't follow the factory pattern.
/// 2- There are constants that need to be moved to configuration (TBD on what configuration).
/// 3- We need a way to dynamically build the MCP server URL. It is environment specific and it won't work in prod as is.
/// 4- still the way we get the AA cert seems hacky.
/// 5- Scope needs to be updated.
/// 6- Remove disabling cert validation.
/// </summary>
public sealed class SemanticKernelAgentLogicServiceFactory(
    IConfiguration configuration,
    IServiceProvider serviceProvider,
    ILogger<SemanticKernelAgentLogicServiceFactory> logger,
    McpToolDiscovery mcpToolDiscovery,
    AgentTokenHelper tokenHelper,
    IMcpToolRegistrationService mcpToolRegistrationService,
    IAgentTokenCache tokenCache)
{
    private readonly string certificateData = configuration.GetCertificateData() ?? string.Empty;

    public async Task<IAgentLogicService> CreateAsync(AgentMetadata agent, ITurnContext turnContext)
    {
        var kernelBuilder = Kernel.CreateBuilder();
        AddModel(kernelBuilder);
        var kernel = kernelBuilder.Build();
        await ConfigureKernelPlugins(agent, kernel, turnContext);
        // Resolve GraphService for constructor injection
        var scopedServiceProvider = serviceProvider.CreateScope().ServiceProvider;

        // Attempt to set presence to busy and status message indicating active work

        return new SemanticKernelAgentLogicService(tokenHelper, agent, kernel, certificateData, configuration, logger, mcpToolRegistrationService, tokenCache);
    }

    private async Task ConfigureKernelPlugins(AgentMetadata agent, Kernel kernel, ITurnContext turnContext)
    {
        var scopedServiceProvider = serviceProvider.CreateScope().ServiceProvider;
        // Prod scope for MCP servers.
        // aka.ms/atg/repo
        // https://github.com/bap-microsoft/MCP-Platform?tab=readme-ov-file#environments
        var requestContext = new TokenRequestContext(["ea9ffc3e-8a23-4a7d-836d-234d7c7565c1/.default"]);
        var tokenCredential = new AgentTokenCredential(tokenHelper, agent, certificateData);
        var accessToken = tokenCredential.GetTokenAsync(requestContext, CancellationToken.None).GetAwaiter().GetResult();
        string agentUserId = agent.UserId.ToString();
        var environmentId = configuration["McpPlatformEnvironmentId"] ?? Environment.GetEnvironmentVariable("McpPlatformEnvironmentId");
        if (string.IsNullOrEmpty(environmentId))
        {
            environmentId = $"Default-{agent.TenantId.ToString()}";
        }
        UserAuthorization userAuthorization = null;
        string authHandlerName = string.Empty;

        await mcpToolRegistrationService.AddToolServersToAgentAsync(kernel, userAuthorization, authHandlerName, turnContext, accessToken.Token);
    }

    private IKernelBuilder AddModel(IKernelBuilder kernelBuilder)
    {
        var deployment = configuration["ModelDeployment"] ?? throw new ArgumentNullException("ModelDeployment");
        var azureOpenAiEndpoint = configuration["AzureOpenAIEndpoint"] ?? throw new ArgumentNullException("AzureOpenAIEndPoint");
        // Kept this for people who use API key in settings.
        // var apiKey = _configuration["OpenAiApiKey"] ?? throw new ArgumentNullException("OpenAiApiKey");

        return kernelBuilder.AddAzureOpenAIChatCompletion(
            deploymentName: deployment,
            endpoint: azureOpenAiEndpoint,
            // Ensure token is always picked up from terminal
            new DefaultAzureCredential()
        );
    }
}