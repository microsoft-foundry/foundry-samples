using Azure.Core;
using HelloWorldA365.Services;
using System.Collections.Concurrent;

namespace HelloWorldA365.AgentLogic.AuthCache;

/// <summary>
/// Cache only for observability (exporter) scoped tokens per (agentId, tenantId).
/// </summary>
public interface IAgentTokenCache
{
    /// <summary>
    /// Registers (idempotent) a credential to be used for observability token acquisition.
    /// </summary>
    void RegisterObservability(string agentId, string tenantId, AgentTokenCredential credential, string[] observabilityScopes);

    /// <summary>
    /// Returns an observability token (cached inside the credential) or null on failure/not registered.
    /// </summary>
    string? GetObservabilityToken(string agentId, string tenantId);
}

public sealed class AgentTokenCache : IAgentTokenCache
{
    private sealed record Entry(AgentTokenCredential Credential, string[] Scopes);

    private readonly ConcurrentDictionary<string, Entry> _map = new();

    public void RegisterObservability(string agentId, string tenantId, AgentTokenCredential credential, string[] observabilityScopes)
    {
        // First registration wins; subsequent calls ignored (idempotent).
        _map.TryAdd(agentId, new Entry(credential, observabilityScopes));
    }

    public string? GetObservabilityToken(string agentId, string tenantId)
    {
        if (!_map.TryGetValue(agentId, out var entry))
            return null;

        try
        {
            // Use sync path; credential handles caching & refresh internally.
            var ctx = new TokenRequestContext(entry.Scopes);
            return entry.Credential.GetToken(ctx, CancellationToken.None).Token;
        }
        catch
        {
            return null;
        }
    }
}