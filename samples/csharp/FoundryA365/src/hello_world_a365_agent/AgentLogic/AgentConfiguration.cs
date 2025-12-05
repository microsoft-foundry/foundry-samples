namespace HelloWorldA365.AgentLogic;

public static class AgentConfiguration
{
    public static string? GetAgentEmailFilter(this IConfiguration configuration) =>
        configuration.GetValue<string>("AgentConfiguration:AgentEmailFilter");

    public static string? GetCertificateData(this IConfiguration configuration) =>
        configuration["agent-blueprint-secret"];
}