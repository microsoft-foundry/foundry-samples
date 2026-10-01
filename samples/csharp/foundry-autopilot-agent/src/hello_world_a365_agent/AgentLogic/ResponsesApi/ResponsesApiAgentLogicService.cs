namespace HelloWorldA365.AgentLogic.ResponsesApi;

using Azure.Core;
using Azure.Identity;
using HelloWorldA365.Models;
using HelloWorldA365.Services;
using Microsoft.Agents.A365.Notifications;
using Microsoft.Agents.A365.Notifications.Models;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.State;
using Microsoft.Agents.Core.Models;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// OpenAI Responses API-based implementation of AgentLogicService.
/// Uses MCP tool definitions directly via the Responses API's native MCP support.
/// </summary>
public class ResponsesApiAgentLogicService : IAgentLogicService
{
    private readonly AgentMetadata _agentMetadata;
    private readonly ILogger _logger;
    private readonly IConfiguration _configuration;
    private readonly string _accessToken;
    private readonly List<McpServerConfig> _mcpServers;
    private readonly HttpClient _httpClient;

    public ResponsesApiAgentLogicService(
        AgentMetadata agent,
        IConfiguration configuration,
        ILogger logger,
        string accessToken,
        List<McpServerConfig> mcpServers)
    {
        _agentMetadata = agent ?? throw new ArgumentNullException(nameof(agent));
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _accessToken = accessToken;
        _mcpServers = mcpServers;

        _httpClient = new HttpClient();
    }

    public async Task NewActivityReceived(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken)
    {
        var incomingText = turnContext.Activity.Text;
        _logger.LogInformation("New activity received (Responses API): {IncomingText}", incomingText);

        var sender = turnContext.Activity.From;

        if (turnContext.Activity.ChannelId == "email" || turnContext.Activity.ChannelId == "agents:email")
        {
            var subject = string.Empty;
            if (turnContext.Activity.ChannelData is JsonElement jsonElement && jsonElement.TryGetProperty("subject", out var subjectProperty))
            {
                subject = subjectProperty.GetString() ?? string.Empty;
            }
            incomingText = $"Please respond to this email From: {sender!.Id}\nSubject: {subject}\nMessage: {incomingText}";
        }
        else if (turnContext.Activity.ChannelId == "msteams")
        {
            incomingText = $"Respond to this chat message with chat id {turnContext.Activity.Conversation.Id} " +
                           $"From: {sender?.Name} ({sender?.Id})\n" +
                           $"Message: {incomingText}\n" +
                           "If user hasn't explicitly asked to send teams messages don't use teams mcp tool to respond, that causes double responses.";
        }
        else if (turnContext.Activity.Type == ActivityTypes.InstallationUpdate)
        {
            incomingText = $"You were just added as a digital worker. Please send an email to {sender!.Id} with information on what you can do.";
        }

        var conversationId = turnContext.Activity.Conversation?.Id ?? "default";
        var response = await InvokeResponsesApiAsync(incomingText, conversationId);

        if (turnContext.Activity.Type == ActivityTypes.Message)
        {
            // The Message handler opens a StreamingResponse via QueueInformativeUpdateAsync
            // and ends it with EndStreamAsync in a finally. We must queue a final text chunk
            // here (even when extraction yielded no assistant text, e.g. tool-call-only
            // outputs) so the channel doesn't render "No text was streamed".
            var finalText = string.IsNullOrWhiteSpace(response) ? "Done." : response;
            turnContext.StreamingResponse.QueueTextChunk(finalText);
        }
        else if (!string.IsNullOrEmpty(response))
        {
            await turnContext.SendActivityAsync(MessageFactory.Text(response), cancellationToken);
        }
    }

    public async Task<string> NewEmailReceived(string fromEmail, string subject, string messageBody)
    {
        var formattedMessage = $"Please respond to this email From: {fromEmail}\nSubject: {subject}\nMessage: {messageBody}";
        return await InvokeResponsesApiAsync(formattedMessage, $"email:{fromEmail}:{subject}");
    }

    public async Task<string> NewChatReceived(string chatId, string fromUser, string messageBody)
    {
        var formattedMessage = $"Respond to this chat message with chat id {chatId} " +
                               $"From: {fromUser}\nMessage: {messageBody}";
        return await InvokeResponsesApiAsync(formattedMessage, chatId);
    }

    public async Task HandleEmailNotificationAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity emailEvent)
    {
        var fromEmail = emailEvent.From.Id;
        var emailJson = JsonSerializer.Serialize(emailEvent, new JsonSerializerOptions { WriteIndented = true });
        var conversationId = turnContext.Activity.Conversation?.Id ?? "email-notification";
        var response = await InvokeResponsesApiAsync($"You received a new email. Please look at the email and return a response in html format. From: {fromEmail}\nEmail details:\n{emailJson}", conversationId);
        var responseActivity = EmailResponse.CreateEmailResponseActivity(response);

        _logger.LogInformation(
            "Outgoing email response activity - original ReplyToId={OriginalReplyToId}, ConversationId={ConversationId}",
            responseActivity.ReplyToId,
            responseActivity.Conversation?.Id);

        await turnContext.SendActivityAsync(responseActivity);
    }

    public async Task HandleCommentNotificationAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity commentEvent)
    {
        _logger.LogInformation("Processing comment notification (Responses API)");

        var comment = commentEvent.WpxCommentNotification;
        if (comment == null)
        {
            _logger.LogWarning("Comment notification received without WpxComment payload; skipping.");
            return;
        }

        // The document the comment lives on is delivered as the first attachment on the activity.
        var attachments = turnContext.Activity.Attachments;
        var contentUrl = attachments?.FirstOrDefault()?.ContentUrl;
        if (string.IsNullOrEmpty(contentUrl))
        {
            _logger.LogWarning(
                "Comment notification for CommentId={CommentId} on DocumentId={DocumentId} has no attachment ContentUrl; cannot fetch document content.",
                comment.CommentId,
                comment.DocumentId);
            return;
        }

        // Figure out which Office product (and therefore which MCP server) to use.
        // The sub-channel is set by the OnAgenticWord/Excel/PowerPointNotification routers.
        var subChannel = turnContext.Activity.ChannelId?.SubChannel ?? string.Empty;
        string productLabel;
        string mcpServerName;
        if (subChannel.Equals(SubChannels.AgentsWordSubChannel, StringComparison.OrdinalIgnoreCase))
        {
            productLabel = "Word";
            mcpServerName = "mcp_WordServer";
        }
        else if (subChannel.Equals(SubChannels.AgentsExcelSubChannel, StringComparison.OrdinalIgnoreCase))
        {
            productLabel = "Excel";
            mcpServerName = "mcp_ExcelServer";
        }
        else if (subChannel.Equals(SubChannels.AgentsPowerPointSubChannel, StringComparison.OrdinalIgnoreCase))
        {
            productLabel = "PowerPoint";
            mcpServerName = "mcp_PowerPointServer";
        }
        else
        {
            // Fall back to inferring from the file extension on the content URL.
            (productLabel, mcpServerName) = InferProductFromUrl(contentUrl);
        }

        var commenter = commentEvent.From?.Name ?? commentEvent.From?.Id ?? "the commenter";
        var commentText = (turnContext.Activity.Text ?? string.Empty).Trim();
        var commentSnippet = string.IsNullOrEmpty(commentText) ? "(no comment text)" : commentText;
        var conversationId = $"comment:{comment.DocumentId ?? "unknown-doc"}:{comment.CommentId ?? "unknown-comment"}";

        var prompt = $"""
            You have been @-mentioned in a {productLabel} comment and must reply to it.

            Use the {mcpServerName} MCP tools to do the following, in order:
              1. Call GetDocumentContent with the sharing URL below to read the document and
                 locate the text that the comment refers to.
              2. Call ReplyToComment with commentId="{comment.CommentId}" to post your reply
                 directly on the thread. Do NOT respond via chat or email — the reply must be
                 posted through the {mcpServerName} ReplyToComment tool so it shows up on the
                 comment thread in the document.

            Keep the reply concise, helpful, and grounded in the actual document content.
            Format the reply as plain text (the comment thread does not render HTML).

            Document URL: {contentUrl}
            DocumentId:   {comment.DocumentId}
            CommentId:    {comment.CommentId}
            ParentCommentId: {comment.ParentCommentId ?? "(none — this is a top-level comment)"}
            Commenter:    {commenter}
            Comment text: {commentSnippet}
            """;

        var response = await InvokeResponsesApiAsync(prompt, conversationId);

        // The reply is posted on the comment thread by the MCP server's ReplyToComment tool,
        // so there is nothing to send back through the activity protocol here. The model's
        // final text (if any) is logged for diagnostics only.
        _logger.LogInformation(
            "Comment reply flow finished for {Product} CommentId={CommentId}. Model output (for diagnostics only): {Response}",
            productLabel,
            comment.CommentId,
            string.IsNullOrWhiteSpace(response) ? "(empty — reply was posted via MCP tool)" : response);
    }

    private static (string Product, string McpServer) InferProductFromUrl(string url)
    {
        var lower = url.ToLowerInvariant();
        if (lower.Contains(".xlsx") || lower.Contains(".xlsm") || lower.Contains(".xlsb"))
        {
            return ("Excel", "mcp_ExcelServer");
        }
        if (lower.Contains(".pptx") || lower.Contains(".ppt"))
        {
            return ("PowerPoint", "mcp_PowerPointServer");
        }
        // Default to Word — covers .docx/.doc and the unknown case.
        return ("Word", "mcp_WordServer");
    }

    public Task HandleInstallationUpdateAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity installationEvent)
    {
        _logger.LogInformation("Processing installation update (Responses API)");
        return Task.CompletedTask;
    }

    /// <summary>
    /// Invokes the OpenAI Responses API with MCP tools from the manifest.
    /// </summary>
    private Task<string> InvokeResponsesApiAsync(string input, string conversationId) =>
        AgentInvocationTracing.TraceAsync(
            input,
            invocation => InvokeResponsesApiCoreAsync(input, conversationId, invocation));

    private async Task<string> InvokeResponsesApiCoreAsync(
        string input,
        string conversationId,
        System.Diagnostics.Activity? invocation)
    {
        var envVars = Environment.GetEnvironmentVariables();
        var envLines = new List<string>(envVars.Count);
        foreach (System.Collections.DictionaryEntry entry in envVars)
        {
            envLines.Add($"{entry.Key}={entry.Value}");
        }
        envLines.Sort(StringComparer.OrdinalIgnoreCase);
        _logger.LogInformation("Process environment variables ({Count}):{NewLine}{EnvVars}", envLines.Count, Environment.NewLine, string.Join(Environment.NewLine, envLines));

        var endpoint = _configuration["AzureOpenAIEndpoint"] ?? throw new InvalidOperationException("AzureOpenAIEndpoint not configured");
        var deployment = _configuration["ModelDeployment"] ?? throw new InvalidOperationException("ModelDeployment not configured");
        var instructions = AgentInstructions.GetInstructions(_agentMetadata);

        // Build MCP tool definitions from discovered servers
        var mcpTools = _mcpServers.Select(server => new
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
        }).ToArray<object>();

        _logger.LogInformation("Invoking Responses API with {McpToolCount} MCP tool servers", mcpTools.Length);

        // Load previous_response_id for conversation continuity
        var previousResponseId = LoadPreviousResponseId(conversationId);
        if (previousResponseId != null)
        {
            _logger.LogInformation("Continuing conversation {ConversationId} with previous_response_id: {PreviousResponseId}", conversationId, previousResponseId);
        }

        var requestBody = new Dictionary<string, object>
        {
            ["model"] = deployment,
            ["instructions"] = instructions,
            ["input"] = input,
            ["tools"] = mcpTools
        };

        if (previousResponseId != null)
        {
            requestBody["previous_response_id"] = previousResponseId;
        }

        var json = JsonSerializer.Serialize(requestBody, new JsonSerializerOptions
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        });

        _logger.LogDebug("Responses API request: {Request}", json);

        // Use Azure AI Foundry Responses API endpoint (model specified in body)
        var requestUrl = $"{endpoint.TrimEnd('/')}/openai/responses?api-version=2025-03-01-preview";

        using var request = new HttpRequestMessage(HttpMethod.Post, requestUrl);
        request.Content = new StringContent(json, Encoding.UTF8, "application/json");

        // Fall back to Bearer token auth (e.g., with DefaultAzureCredential token)
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
            AgentInvocationTracing.RecordError(invocation, $"http_{(int)response.StatusCode}");
            _logger.LogError("Responses API call failed with status {StatusCode}: {Response}", response.StatusCode, responseContent);
            return $"I encountered an error processing your request. Status: {response.StatusCode}";
        }

        _logger.LogDebug("Responses API response: {Response}", responseContent);

        // Save the response id for conversation continuity
        SaveResponseId(conversationId, responseContent);

        return ExtractOutputText(responseContent, invocation);
    }

    private static string GetResponseStoreDir()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return Path.Combine(home, ".a365agent");
    }

    private static string GetResponseIdFilePath(string conversationId)
    {
        // SHA-256 hash conversation ID to produce a fixed-length, filesystem-safe filename
        // and avoid PathTooLongException for long conversation IDs.
        var hashBytes = SHA256.HashData(Encoding.UTF8.GetBytes(conversationId));
        var safeId = Convert.ToHexString(hashBytes).ToLowerInvariant();
        return Path.Combine(GetResponseStoreDir(), $"{safeId}.responseid");
    }

    private string? LoadPreviousResponseId(string conversationId)
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

    /// <summary>
    /// Extracts the final output text from the Responses API response JSON.
    /// </summary>
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

            // Fallback: try to get a simple text response
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
