namespace WorkstreamManager.AgentLogic.ResponsesApi.Helpers;

using Azure.Core;
using Azure.Identity;
using WorkstreamManager.AgentLogic;
using WorkstreamManager.Models;
using WorkstreamManager.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

/// <summary>
/// Handles HTTP communication with the OpenAI Responses API, including
/// request building, tool-call loop execution, and response parsing.
/// </summary>
internal class ResponsesApiClient
{
    private readonly AgentMetadata _agentMetadata;
    private readonly ILogger _logger;
    private readonly IConfiguration _configuration;
    private readonly string _accessToken;
    private readonly List<McpServerConfig> _mcpServers;
    private readonly HttpClient _httpClient;

    internal ResponsesApiClient(
        AgentMetadata agentMetadata,
        ILogger logger,
        IConfiguration configuration,
        string accessToken,
        List<McpServerConfig> mcpServers,
        HttpClient httpClient)
    {
        _agentMetadata = agentMetadata ?? throw new ArgumentNullException(nameof(agentMetadata));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _accessToken = accessToken;
        _mcpServers = mcpServers ?? throw new ArgumentNullException(nameof(mcpServers));
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    }

    internal Task<string> InvokeAsync(
        string input,
        string conversationId,
        string? instructionsOverride = null,
        bool includeMcpTools = true,
        bool persistResponseId = true,
        List<JsonNode>? additionalTools = null,
        Func<string, string, Task<string?>>? localToolExecutor = null)
    {
        return AgentInvocationTracing.TraceAsync(input, invocation =>
            InvokeCoreAsync(input, conversationId, instructionsOverride, includeMcpTools,
                persistResponseId, additionalTools, localToolExecutor, invocation));
    }

    private async Task<string> InvokeCoreAsync(
        string input,
        string conversationId,
        string? instructionsOverride,
        bool includeMcpTools,
        bool persistResponseId,
        List<JsonNode>? additionalTools,
        Func<string, string, Task<string?>>? localToolExecutor,
        System.Diagnostics.Activity? invocation)
    {
        var endpoint = _configuration["AzureOpenAIEndpoint"] ?? throw new InvalidOperationException("AzureOpenAIEndpoint not configured");
        var deployment = _configuration["ModelDeployment"] ?? throw new InvalidOperationException("ModelDeployment not configured");
        var instructions = instructionsOverride ?? AgentInstructions.GetInstructions(_agentMetadata);

        var mcpTools = includeMcpTools
            ? _mcpServers.Select(server => (object)new
            {
                type = "mcp",
                server_label = server.McpServerName,
                server_url = server.Url,
                server_description = $"MCP server: {server.McpServerName}",
                require_approval = "never",
                headers = new Dictionary<string, string>
                {
                    ["Authorization"] = $"Bearer {_accessToken}"
                }
            }).ToArray()
            : Array.Empty<object>();

        var localTools = includeMcpTools ? additionalTools ?? [] : [];

        _logger.LogInformation(
            "Invoking Responses API with {McpToolCount} MCP tool servers and {LocalToolCount} local tools (persistResponseId={Persist})",
            mcpTools.Length,
            localTools.Count,
            persistResponseId);

        var previousResponseId = LoadPreviousResponseId(conversationId);
        if (previousResponseId != null)
        {
            _logger.LogInformation("Continuing conversation {ConversationId} with previous_response_id: {PreviousResponseId}", conversationId, previousResponseId);
        }

        var requestUrl = $"{endpoint.TrimEnd('/')}/openai/responses?api-version=2025-03-01-preview";

        var (success, responseContent) = await SendRequestAsync(
            requestUrl,
            BuildRequestBody(input, deployment, instructions, includeMcpTools, mcpTools, localTools, previousResponseId));
        if (!success)
        {
            AgentInvocationTracing.RecordError(invocation, "responses_api_error");
            return responseContent;
        }

        for (var iteration = 0; iteration < 10; iteration++)
        {
            var functionCalls = ExtractFunctionCalls(responseContent);
            if (functionCalls.Count == 0)
            {
                break;
            }

            var currentResponseId = TryExtractResponseId(responseContent);
            if (string.IsNullOrWhiteSpace(currentResponseId))
            {
                AgentInvocationTracing.RecordError(invocation, "missing_response_id");
                _logger.LogError("Responses API returned function calls without a response id.");
                return "I encountered an error processing your request.";
            }

            var toolOutputs = new List<object>();
            foreach (var functionCall in functionCalls)
            {
                var toolOutput = localToolExecutor is null
                    ? null
                    : await localToolExecutor(functionCall.Name, functionCall.Arguments);
                toolOutputs.Add(new
                {
                    type = "function_call_output",
                    call_id = functionCall.CallId,
                    output = toolOutput ?? $"Error: Unsupported tool '{functionCall.Name}'."
                });
            }

            (success, responseContent) = await SendRequestAsync(
                requestUrl,
                BuildRequestBody(toolOutputs, deployment, instructions, includeMcpTools, mcpTools, localTools, currentResponseId));
            if (!success)
            {
                AgentInvocationTracing.RecordError(invocation, "responses_api_error");
                return responseContent;
            }
        }

        if (ExtractFunctionCalls(responseContent).Count > 0)
        {
            AgentInvocationTracing.RecordError(invocation, "tool_iteration_limit");
            _logger.LogWarning("Responses API tool-call limit reached before a final response.");
        }

        if (persistResponseId)
        {
            SaveResponseId(conversationId, responseContent);
        }

        return ExtractOutputText(responseContent, invocation);
    }

    internal string? LoadPreviousResponseId(string conversationId)
    {
        try
        {
            var filePath = GetResponseIdFilePath(conversationId);
            if (File.Exists(filePath))
            {
                var id = File.ReadAllText(filePath).Trim();
                return string.IsNullOrEmpty(id) ? null : id;
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to load previous_response_id for conversation {ConversationId}", conversationId);
        }

        return null;
    }

    internal static DateTimeOffset? TryParseDateTimeOffsetProperty(object? value)
    {
        switch (value)
        {
            case null:
                return null;
            case DateTimeOffset dto:
                return dto;
            case DateTime dt:
                var utc = dt.Kind == DateTimeKind.Unspecified
                    ? DateTime.SpecifyKind(dt, DateTimeKind.Utc)
                    : dt.ToUniversalTime();
                return new DateTimeOffset(utc);
            default:
                var text = value.ToString();
                return DateTimeOffset.TryParse(text, out var parsed) ? parsed : null;
        }
    }

    private Dictionary<string, object> BuildRequestBody(
        object inputPayload,
        string deployment,
        string instructions,
        bool includeMcpTools,
        IReadOnlyCollection<object> mcpTools,
        IReadOnlyCollection<JsonNode> localTools,
        string? priorResponseId)
    {
        var requestBody = new Dictionary<string, object>
        {
            ["model"] = deployment,
            ["instructions"] = instructions,
            ["input"] = inputPayload,
        };

        if (includeMcpTools)
        {
            var allTools = new List<object>();
            allTools.AddRange(mcpTools);
            foreach (var localTool in localTools)
            {
                allTools.Add(localTool);
            }

            if (allTools.Count > 0)
            {
                requestBody["tools"] = allTools;
            }
        }

        if (priorResponseId != null)
        {
            requestBody["previous_response_id"] = priorResponseId;
        }

        return requestBody;
    }

    private async Task<(bool Success, string Content)> SendRequestAsync(string requestUrl, Dictionary<string, object> requestBody)
    {
        var json = JsonSerializer.Serialize(requestBody, new JsonSerializerOptions
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        });

        _logger.LogInformation("Responses API request ({Bytes} bytes): {Request}", json.Length, json);

        using var request = new HttpRequestMessage(HttpMethod.Post, requestUrl);
        request.Content = new StringContent(json, Encoding.UTF8, "application/json");

        var instanceClientId = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID")
            ?? throw new InvalidOperationException("FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID environment variable is not set.");
        var credential = new DefaultAzureCredential(new DefaultAzureCredentialOptions
        {
            ManagedIdentityClientId = instanceClientId,
        });
        var token = await credential.GetTokenAsync(new TokenRequestContext(new[] { "https://cognitiveservices.azure.com/.default" }), CancellationToken.None);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

        var response = await _httpClient.SendAsync(request);
        var responseContent = await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogError("Responses API call failed with status {StatusCode}: {Response}", response.StatusCode, responseContent);
            return (false, $"I encountered an error processing your request. Status: {response.StatusCode}");
        }

        _logger.LogInformation("Responses API response ({Bytes} bytes): {Response}", responseContent.Length, responseContent);
        return (true, responseContent);
    }

    private List<ResponsesApiFunctionCall> ExtractFunctionCalls(string responseJson)
    {
        try
        {
            using var doc = JsonDocument.Parse(responseJson);
            if (!doc.RootElement.TryGetProperty("output", out var output) || output.ValueKind != JsonValueKind.Array)
            {
                return [];
            }

            var functionCalls = new List<ResponsesApiFunctionCall>();
            foreach (var item in output.EnumerateArray())
            {
                if (!item.TryGetProperty("type", out var typeProp) ||
                    !string.Equals(typeProp.GetString(), "function_call", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var callId = item.TryGetProperty("call_id", out var callIdProp) ? callIdProp.GetString() : null;
                var name = item.TryGetProperty("name", out var nameProp) ? nameProp.GetString() : null;
                var arguments = item.TryGetProperty("arguments", out var argumentsProp)
                    ? argumentsProp.ValueKind == JsonValueKind.String
                        ? argumentsProp.GetString() ?? "{}"
                        : argumentsProp.GetRawText()
                    : "{}";

                if (!string.IsNullOrWhiteSpace(callId) && !string.IsNullOrWhiteSpace(name))
                {
                    functionCalls.Add(new ResponsesApiFunctionCall(callId, name, arguments));
                }
            }

            return functionCalls;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to extract function calls from Responses API response.");
            return [];
        }
    }

    private string? TryExtractResponseId(string responseJson)
    {
        try
        {
            using var doc = JsonDocument.Parse(responseJson);
            return doc.RootElement.TryGetProperty("id", out var idProp) ? idProp.GetString() : null;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to extract response id from Responses API response.");
            return null;
        }
    }

    private static string GetResponseStoreDir()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return Path.Combine(home, ".a365agent");
    }

    private static string GetResponseIdFilePath(string conversationId)
    {
        var safeId = Convert.ToBase64String(Encoding.UTF8.GetBytes(conversationId))
            .Replace('/', '_').Replace('+', '-').TrimEnd('=');
        return Path.Combine(GetResponseStoreDir(), $"{safeId}.responseid");
    }

    private void SaveResponseId(string conversationId, string responseJson)
    {
        try
        {
            using var doc = JsonDocument.Parse(responseJson);
            if (doc.RootElement.TryGetProperty("id", out var idProp))
            {
                var responseId = idProp.GetString();
                if (!string.IsNullOrEmpty(responseId))
                {
                    var dir = GetResponseStoreDir();
                    Directory.CreateDirectory(dir);
                    File.WriteAllText(GetResponseIdFilePath(conversationId), responseId);
                    _logger.LogDebug("Saved response_id {ResponseId} for conversation {ConversationId}", responseId, conversationId);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to save response_id for conversation {ConversationId}", conversationId);
        }
    }

    private string ExtractOutputText(string responseJson, System.Diagnostics.Activity? invocation)
    {
        try
        {
            using var doc = JsonDocument.Parse(responseJson);
            var root = doc.RootElement;
            AgentInvocationTracing.RecordResponse(invocation, root);

            if (root.TryGetProperty("output", out var output) && output.ValueKind == JsonValueKind.Array)
            {
                var textParts = new StringBuilder();
                foreach (var item in output.EnumerateArray())
                {
                    if (item.TryGetProperty("type", out var type) && type.GetString() == "message")
                    {
                        if (item.TryGetProperty("content", out var content) && content.ValueKind == JsonValueKind.Array)
                        {
                            foreach (var contentItem in content.EnumerateArray())
                            {
                                if (contentItem.TryGetProperty("type", out var contentType) &&
                                    contentType.GetString() == "output_text" &&
                                    contentItem.TryGetProperty("text", out var text))
                                {
                                    textParts.Append(text.GetString());
                                }
                            }
                        }
                    }
                }

                return textParts.ToString();
            }

            if (root.TryGetProperty("output_text", out var simpleText))
            {
                return simpleText.GetString() ?? string.Empty;
            }

            _logger.LogWarning("Could not extract output text from Responses API response");
            AgentInvocationTracing.RecordError(invocation, "missing_response_output");
            return string.Empty;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error parsing Responses API response");
            AgentInvocationTracing.RecordError(invocation, "invalid_response");
            return string.Empty;
        }
    }
}

internal record ResponsesApiFunctionCall(string CallId, string Name, string Arguments);
