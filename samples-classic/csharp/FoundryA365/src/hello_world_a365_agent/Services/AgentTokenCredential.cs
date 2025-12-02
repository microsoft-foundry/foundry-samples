namespace HelloWorldA365.Services;

using System.IdentityModel.Tokens.Jwt;
using Azure.Core;
using HelloWorldA365.Models;

/// <summary>
/// TokenCredential implementation that calls AgentTokenHelper to acquire tokens.
/// Includes token caching and expiry handling with thread-safe token refresh.
/// </summary>
public class AgentTokenCredential(AgentTokenHelper agentTokenHelper, AgentMetadata agent, string certificateData) : TokenCredential
{
    private AccessToken? cachedToken;
    private readonly SemaphoreSlim tokenSemaphore = new(1, 1);

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        return GetTokenAsync(requestContext, cancellationToken).GetAwaiter().GetResult();
    }

    public override async ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        // Check if we have a valid cached token (with 5-minute buffer before expiry)
        if (cachedToken.HasValue && DateTimeOffset.UtcNow.AddMinutes(5) < cachedToken.Value.ExpiresOn)
        {
            return cachedToken.Value;
        }

        // Use semaphore to ensure only one token request at a time
        await tokenSemaphore.WaitAsync(cancellationToken);
        try
        {
            // Double-check pattern: another thread might have refreshed the token
            if (cachedToken.HasValue && DateTimeOffset.UtcNow.AddMinutes(5) < cachedToken.Value.ExpiresOn)
            {
                return cachedToken.Value;
            }

            // Use all scopes from the request context, or default if none
            var scopes = requestContext.Scopes.Length > 0
                ? requestContext.Scopes
                : ["https://canary.graph.microsoft.com/.default"];

            var token = await agentTokenHelper.GetAgenticUserTokenAsync(
                agent.AgentApplicationId.ToString(),
                agent.AgentId.ToString(),
                agent.EmailId ?? agent.UserId.ToString(),
                certificateData,
                agent.TenantId.ToString(),
                scopes);

            // Parse the JWT token to get expiry time, or default to 1 hour
            var expiresOn = GetTokenExpiryTime(token);
            var accessToken = new AccessToken(token, expiresOn);

            cachedToken = accessToken;
            return accessToken;
        }
        finally
        {
            tokenSemaphore.Release();
        }
    }

    private static DateTimeOffset GetTokenExpiryTime(string token)
    {
        try
        {
            if (new JwtSecurityTokenHandler().CanReadToken(token))
            {
                var jwtToken = new JwtSecurityToken(token);
                return jwtToken.ValidTo;
            }
        }
        catch
        {
            // If parsing fails, default to 1 hour from now
        }

        return DateTimeOffset.UtcNow.AddHours(1);
    }
}
