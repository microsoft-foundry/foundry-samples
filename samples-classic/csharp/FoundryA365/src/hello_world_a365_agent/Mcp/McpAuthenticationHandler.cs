namespace HelloWorldA365.Mcp;

using System.Net.Http.Headers;
using Azure.Core;
using HelloWorldA365.Models;
using HelloWorldA365.Services;

/// <summary>
/// HTTP message handler that automatically adds authentication tokens to requests
/// using AgentTokenCredential for MCP endpoint authentication with built-in token caching.
/// Only authenticates requests to the configured MCP server endpoint.
/// </summary>
public class McpAuthenticationHandler : DelegatingHandler
{
    private readonly AgentTokenCredential _tokenCredential;
    private readonly ILogger _logger;
    private readonly string[] _scopes;
    private readonly Uri _mcpServerEndpoint;

    public McpAuthenticationHandler(
        AgentTokenHelper tokenHelper, 
        AgentMetadata agent, 
        string certificateData,
        ILogger logger,
        string mcpServerEndpoint,
        string[]? scopes = null)
    {
        _tokenCredential = new AgentTokenCredential(tokenHelper, agent, certificateData);
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _scopes = scopes ?? throw new ArgumentNullException(nameof(scopes));

        if (string.IsNullOrWhiteSpace(mcpServerEndpoint))
        {
            throw new ArgumentException("MCP server endpoint cannot be null or empty", nameof(mcpServerEndpoint));
        }
            
        _mcpServerEndpoint = new Uri(mcpServerEndpoint);
        _logger.LogInformation("MCPAuthenticationHandler configured for selective authentication on endpoint: {Endpoint}", _mcpServerEndpoint);
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        // Only add authentication for requests to the configured MCP server endpoint
        if (ShouldAuthenticateRequest(request))
        {
            try
            {
                var requestContext = new TokenRequestContext(_scopes);
                    
                var accessToken = await _tokenCredential.GetTokenAsync(requestContext, cancellationToken);

                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken.Token);

                _logger.LogDebug("Added authentication token to MCP request for {RequestUri}, token expires at {ExpiresOn}", 
                    request.RequestUri, accessToken.ExpiresOn);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to acquire authentication token for MCP request to {RequestUri}", request.RequestUri);
                throw;
            }
        }
        else
        {
            _logger.LogDebug("Skipping authentication for non-MCP request to {RequestUri}", request.RequestUri);
        }

        return await base.SendAsync(request, cancellationToken);
    }

    /// <summary>
    /// Determines if the request should be authenticated based on the target endpoint
    /// </summary>
    /// <param name="request">The HTTP request</param>
    /// <returns>True if the request should be authenticated, false otherwise</returns>
    private bool ShouldAuthenticateRequest(HttpRequestMessage request)
    {
        if (request.RequestUri == null)
        {
            _logger.LogDebug("Request has no URI, skipping authentication");
            return false;
        }

        var requestUri = request.RequestUri;
            
        // Match scheme and host
        if (!string.Equals(requestUri.Scheme, _mcpServerEndpoint.Scheme, StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(requestUri.Host, _mcpServerEndpoint.Host, StringComparison.OrdinalIgnoreCase))
        {
            _logger.LogDebug("Request scheme/host mismatch: Request={RequestScheme}://{RequestHost}, MCP={MCPScheme}://{MCPHost}", 
                requestUri.Scheme, requestUri.Host, _mcpServerEndpoint.Scheme, _mcpServerEndpoint.Host);
            return false;
        }

        // Match port if specified
        if (requestUri.Port != _mcpServerEndpoint.Port)
        {
            _logger.LogDebug("Request port mismatch: Request={RequestPort}, MCP={MCPPort}", 
                requestUri.Port, _mcpServerEndpoint.Port);
            return false;
        }

        var requestPath = requestUri.AbsolutePath.TrimEnd('/');
        var mcpPath = _mcpServerEndpoint.AbsolutePath.TrimEnd('/');
            
        var shouldAuthenticate = requestPath.StartsWith(mcpPath, StringComparison.OrdinalIgnoreCase);
            
        _logger.LogDebug("Path matching: Request='{RequestPath}', MCP='{MCPPath}', Should Authenticate={ShouldAuthenticate}", 
            requestPath, mcpPath, shouldAuthenticate);
                
        return shouldAuthenticate;
    }
}