// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json;
using Azure.Core;
using Azure.Core.Pipeline;

namespace BrowserAutomation;

public sealed record ToolboxTool(
    string Name,
    string Description,
    BinaryData InputSchema);

public sealed record ToolboxCallResult(
    string Output,
    string? BrowserSessionId,
    string? LiveViewUrl,
    bool IsError,
    string? SessionName = null,
    string? PublicOutput = null);

public sealed class ToolboxClient
{
    private readonly string _endpoint;
    private readonly HttpPipeline _pipeline;
    private readonly ILogger _logger;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly HttpClient _client = new()
    {
        Timeout = TimeSpan.FromSeconds(120),
    };
    private string? _sessionId;
    private IReadOnlyList<ToolboxTool>? _tools;
    private int _requestId;
    private bool _initialized;

    public ToolboxClient(
        string endpoint,
        TokenCredential credential,
        ILogger logger)
    {
        _endpoint = endpoint;
        _pipeline = new HttpPipeline(
            new HttpClientTransport(_client),
            [new BearerTokenAuthenticationPolicy(credential, Constants.AzureAiScope)]);
        _logger = logger;
    }

    public async Task<IReadOnlyList<ToolboxTool>> ListToolsAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            if (_tools is not null)
                return _tools;

            await InitializeCoreAsync(cancellationToken);
            var result = await PostCoreAsync(
                "tools/list",
                new { },
                cancellationToken);
            _tools = result.GetProperty("tools")
                .EnumerateArray()
                .Select(tool => new ToolboxTool(
                    tool.GetProperty("name").GetString()!,
                    tool.TryGetProperty("description", out var description)
                        ? description.GetString() ?? ""
                        : "",
                    BinaryData.FromString(
                        tool.GetProperty("inputSchema").GetRawText())))
                .ToList();
            _logger.LogInformation(
                "Discovered {Count} toolbox tools",
                _tools.Count);
            return _tools;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<ToolboxCallResult> CallToolAsync(
        string name,
        BinaryData arguments,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            await InitializeCoreAsync(cancellationToken);
            using var argumentDocument = JsonDocument.Parse(arguments);
            var result = await PostCoreAsync(
                "tools/call",
                new
                {
                    name,
                    arguments = argumentDocument.RootElement.Clone(),
                },
                cancellationToken);

            var textItems = result.TryGetProperty("content", out var content)
                ? content.EnumerateArray()
                    .Where(item =>
                        item.TryGetProperty("type", out var type)
                        && type.GetString() == "text")
                    .Select(item => item.GetProperty("text").GetString() ?? "")
                    .Where(text => text.Length > 0)
                    .ToList()
                : [];

            string? browserSessionId = null;
            string? liveViewUrl = null;
            var sanitized = new List<string>();
            foreach (var text in textItems)
            {
                try
                {
                    using var document = JsonDocument.Parse(text);
                    var root = document.RootElement;
                    if (root.ValueKind != JsonValueKind.Object)
                    {
                        sanitized.Add(text);
                        continue;
                    }

                    if (root.TryGetProperty("browserSessionId", out var id))
                        browserSessionId ??= id.GetString();
                    if (root.TryGetProperty("liveViewUrl", out var url))
                        liveViewUrl ??= url.GetString();

                    if (root.TryGetProperty("liveViewUrl", out _))
                    {
                        var values = root.EnumerateObject()
                            .Where(property => property.Name != "liveViewUrl")
                            .ToDictionary(
                                property => property.Name,
                                property => property.Value.Clone());
                        values["note"] = JsonSerializer.SerializeToElement(
                            "Live-view URL omitted from model-visible tool output.");
                        sanitized.Add(JsonSerializer.Serialize(values));
                    }
                    else
                    {
                        sanitized.Add(text);
                    }
                }
                catch (JsonException)
                {
                    sanitized.Add(text);
                }
            }

            var output = sanitized.Count > 0
                ? string.Join("\n", sanitized)
                : result.GetRawText();
            var isError = result.TryGetProperty("isError", out var error)
                && error.GetBoolean();
            IReadOnlyList<string> liveViewUrls = liveViewUrl is null ? [] : [liveViewUrl];
            var publicOutput = string.Join("\n",
                (sanitized.Count > 0 ? sanitized : [output]).Select(text =>
                    Redaction.PublicToolOutput(name, text, isError, liveViewUrls)));
            return new ToolboxCallResult(
                output,
                browserSessionId,
                liveViewUrl,
                isError,
                PublicOutput: publicOutput);
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task InitializeCoreAsync(CancellationToken cancellationToken)
    {
        if (_initialized)
            return;

        await PostCoreAsync(
            "initialize",
            new
            {
                protocolVersion = "2025-03-26",
                capabilities = new { },
                clientInfo = new
                {
                    name = "browser-automation-byo",
                    version = "1.0.0",
                },
            },
            cancellationToken);
        await PostNotificationCoreAsync(
            "notifications/initialized",
            cancellationToken);
        _initialized = true;
    }

    private async Task PostNotificationCoreAsync(
        string method,
        CancellationToken cancellationToken)
    {
        var payload = JsonSerializer.Serialize(new
        {
            jsonrpc = "2.0",
            method,
        });
        using var message = CreateMessage(payload);
        await _pipeline.SendAsync(message, cancellationToken);
        EnsureSuccess(message.Response);
    }

    private async Task<JsonElement> PostCoreAsync(
        string method,
        object parameters,
        CancellationToken cancellationToken)
    {
        var payload = JsonSerializer.Serialize(new
        {
            jsonrpc = "2.0",
            id = Interlocked.Increment(ref _requestId),
            method,
            @params = parameters,
        });
        using var message = CreateMessage(payload);
        await _pipeline.SendAsync(message, cancellationToken);
        var response = message.Response;
        EnsureSuccess(response);
        if (response.Headers.TryGetValue("mcp-session-id", out var sessionId))
            _sessionId = sessionId;

        if (response.ContentStream is not { } body)
            throw new InvalidOperationException($"MCP {method} returned no response body.");
        using var document = await JsonDocument.ParseAsync(
            body,
            cancellationToken: cancellationToken);
        var root = document.RootElement;
        if (root.TryGetProperty("error", out var error))
            throw new InvalidOperationException(
                $"MCP {method} failed: {error.GetRawText()}");
        return root.GetProperty("result").Clone();
    }

    private HttpMessage CreateMessage(string payload)
    {
        var message = _pipeline.CreateMessage();
        message.Request.Method = RequestMethod.Post;
        message.Request.Uri.Reset(new Uri(_endpoint));
        message.Request.Content = RequestContent.Create(payload);
        message.Request.Headers.SetValue("Content-Type", "application/json; charset=utf-8");
        if (_sessionId is not null)
            message.Request.Headers.SetValue("mcp-session-id", _sessionId);
        return message;
    }

    private static void EnsureSuccess(Azure.Response response)
    {
        if (response.Status is < 200 or >= 300)
            throw new HttpRequestException(
                $"Response status code does not indicate success: {response.Status} ({response.ReasonPhrase}).",
                null,
                (HttpStatusCode)response.Status);
    }
}
