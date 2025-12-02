namespace HelloWorldA365.Mcp;

using System.Text.Json;

/// <summary>
/// HTTP logging handler for debugging purposes
/// </summary>
public class McpClientHttpRequestLogger(ILogger logger) : DelegatingHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        // Log request
        logger.LogInformation("HTTP Request: {Method} {Uri}", request.Method, request.RequestUri);
        logger.LogInformation("Request Headers: {Headers}", JsonSerializer.Serialize(
            request.Headers.ToDictionary(h => h.Key, h => string.Join(", ", h.Value))
        ));

        if (request.Content != null)
        {
            var requestBody = await request.Content.ReadAsStringAsync(cancellationToken);
            logger.LogInformation("Request Body: {Body}", requestBody);
        }

        // Send request
        var response = await base.SendAsync(request, cancellationToken);

        // Log response
        logger.LogInformation("HTTP Response: {StatusCode} {ReasonPhrase}", (int)response.StatusCode, response.ReasonPhrase);
        logger.LogInformation("Response Headers: {Headers}", JsonSerializer.Serialize(
            response.Headers.ToDictionary(h => h.Key, h => string.Join(", ", h.Value))
        ));

        if (response.Content != null)
        {
            var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
            logger.LogInformation("Response Body: {Body}", responseBody);
        }

        return response;
    }
}