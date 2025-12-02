namespace HelloWorldA365.Mcp;

using System.Text;
using HelloWorldA365.AgentLogic;
using HelloWorldA365.Models;
using HelloWorldA365.Services;
using Microsoft.SemanticKernel;
using ModelContextProtocol.Client;

public sealed class McpToolDiscovery(
    ILogger<McpToolDiscovery> logger,
    IConfiguration configuration,
    AgentTokenHelper tokenHelper)
{
    // If certificateData is empty then AgentTokenCredential uses managed identity through IMDS using DefaultAzureCredential
    private readonly string certificateData = configuration.GetCertificateData() ?? string.Empty;
    
    public async Task<IEnumerable<KernelFunction>> Discover(AgentMetadata agent)
    {
        // Check if agent has MCP server URL configured
        if (string.IsNullOrWhiteSpace(agent.McpServerUrl))
        {
            logger.LogInformation("Agent {AgentId} has no MCP server URL configured, skipping MCP tool discovery", agent.AgentId);
            return [];
        }

        var tools = await GetMcpToolsAsync(agent);
        return tools.Select(aiFunction =>
        {
            var originalKernelFunction = aiFunction.AsKernelFunction();
            var wrapper = new McpFunctionWrapper(originalKernelFunction, aiFunction.Name, logger, configuration);
            return wrapper.CreateWrappedFunction();
        });
    }

    private async Task<IList<McpClientTool>> GetMcpToolsAsync(AgentMetadata agent)
    {
        var mcpClient = await SetupMcpClientAsync(agent);
        var tools = await mcpClient.ListToolsAsync();
        LogDiscoveredTools(tools, agent.McpServerUrl!);
        return tools;
    }
    
    /// <summary>
    /// Sets up and configures the MCP client with authentication and logging handlers
    /// </summary>
    /// <param name="agent">The agent for authentication</param>
    /// <returns>Configured MCP client ready for use</returns>
    private async Task<IMcpClient> SetupMcpClientAsync(AgentMetadata agent)
    {
        if (string.IsNullOrWhiteSpace(agent.McpServerUrl))
        {
            throw new ArgumentException("Agent MCP server URL is not configured", nameof(agent));
        }

        // Create HTTP client handler chain for MCP service authentication
        var httpClientHandler = new HttpClientHandler();

        // WARNING: Only use this in development/testing - never in production!
        // This bypasses SSL certificate validation
        httpClientHandler.ServerCertificateCustomValidationCallback =
            HttpClientHandler.DangerousAcceptAnyServerCertificateValidator;

        // Create authentication handler for MCP service using AgentTokenCredential
        var authHandler = new McpAuthenticationHandler(
            tokenHelper, 
            agent, 
            certificateData, 
            logger, 
            agent.McpServerUrl, // Use the agent's MCP server URL instead of global config
            ["https://api.test.powerplatform.com/.default"])
        {
            InnerHandler = httpClientHandler
        };

        logger.LogInformation("Configured MCPAuthenticationHandler with AgentTokenCredential for agent {AgentId} with selective authentication for MCP endpoint {Endpoint}", agent.AgentId, agent.McpServerUrl);

        // Create logging handler (optional - for debugging HTTP requests)
        var loggingHandler = new McpClientHttpRequestLogger(logger)
        {
            InnerHandler = authHandler
        };

        // Setup SSE client transport options without manual token management
        var options = new SseClientTransportOptions
        {
            Endpoint = new Uri(agent.McpServerUrl),
            TransportMode = HttpTransportMode.AutoDetect,
            Name = "MCPClientService"
        };

        // Create HTTP client with the authentication handler chain
        var httpClient = new HttpClient(loggingHandler);
        var clientTransport = new SseClientTransport(options, httpClient);
            
        return await McpClientFactory.CreateAsync(clientTransport);
    }

    /// <summary>
    /// Logs discovered MCP tools for debugging and monitoring purposes
    /// </summary>
    /// <param name="tools">The collection of discovered MCP tools</param>
    /// <param name="mcpServerUrl">The MCP server URL for this agent</param>
    private void LogDiscoveredTools(IList<McpClientTool> tools, string mcpServerUrl)
    {
        logger.LogInformation("Discovered {ToolCount} tools from MCP service at {McpServiceEndpoint}", tools.Count, mcpServerUrl);
            
        if (tools.Count == 0)
        {
            logger.LogWarning("No tools were discovered from MCP service at {McpServiceEndpoint}", mcpServerUrl);
            return;
        }

        var toolList = new StringBuilder();
        foreach (var tool in tools)
        {
            toolList.AppendLine($"- {tool.Name} ({tool.Description})");
        }
        logger.LogInformation("Tools:\n{ToolList}", toolList.ToString());
    }
}