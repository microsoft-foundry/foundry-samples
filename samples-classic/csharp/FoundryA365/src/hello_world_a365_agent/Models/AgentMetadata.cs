namespace HelloWorldA365.Models;

public class AgentMetadata 
{
    // Business properties
    public Guid UserId { get; set; }
    public Guid AgentId { get; set; }
    public Guid AgentApplicationId { get; set; }
    public Guid TenantId { get; set; }
    public string AgentFriendlyName { get; set; } = string.Empty;

    // This is used to keep track of which AppService is responsible for running logic of this agent.
    public string OwningServiceName { get; set; } = string.Empty;

    public DateTime? LastEmailCheck { get; set; }
    public DateTime? LastTeamsCheck { get; set; }
    public string EmailId { get; set; } = string.Empty;
    public string? WebhookUrl { get; set; }
    public bool SkipAgentIdAuth { get; set; } = false;

    public bool IsMessagingEnabled { get; set; } = false;

    /// <summary>
    /// MCP Server URL for this agent. If null or empty, MCP tools will not be enabled.
    /// </summary>
    public string? McpServerUrl { get; set; }

    public AgentMetadata()
    {
    }

    public AgentMetadata(Guid tenantId, Guid agentId, Guid userId, string agentFriendlyName, string owningServiceName)
    {
        TenantId = tenantId;
        AgentId = agentId;
        UserId = userId;
        AgentFriendlyName = agentFriendlyName;
        OwningServiceName = owningServiceName;
    }
}