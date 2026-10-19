// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace BrowserAutomation;

public static class Middlewares
{
    private static readonly ILogger Logger =
        LoggerFactory.Create(builder => builder.AddConsole())
            .CreateLogger("Middlewares");
    private static string? _liveViewUrl;

    public static async ValueTask<object?> FunctionInvocationMiddleware(
        AIAgent agent,
        FunctionInvocationContext context,
        Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next,
        CancellationToken cancellationToken)
    {
        var functionName = context.Function.Name;
        Logger.LogInformation("[tool] name={Name}", functionName);

        var result = await next(context, cancellationToken);

        if (functionName.EndsWith(
                "close_browser_session",
                StringComparison.OrdinalIgnoreCase))
        {
            Interlocked.Exchange(ref _liveViewUrl, null);
            return result;
        }

        if (!functionName.EndsWith(
                "create_browser_session",
                StringComparison.OrdinalIgnoreCase))
            return result;

        var serializedResult = SerializeResult(result);
        Logger.LogInformation(
            "[tool-result] name={Name} type={ResultType} response={Response}",
            functionName,
            result?.GetType().FullName ?? "<null>",
            serializedResult);

        try
        {
            using var document = JsonDocument.Parse(serializedResult);
            if (!TryExtractBrowserSession(
                    document.RootElement,
                    out var browserSessionId,
                    out var liveViewUrl))
            {
                Logger.LogWarning(
                    "[browser-session] create result did not contain browserSessionId");
                return result;
            }

            if (!string.IsNullOrEmpty(liveViewUrl))
                Interlocked.Exchange(ref _liveViewUrl, liveViewUrl);

            Logger.LogInformation(
                "[browser-session] id={BrowserSessionId} liveViewUrl={LiveViewUrl}",
                browserSessionId,
                liveViewUrl ?? "<missing>");

            return JsonSerializer.Serialize(new
            {
                browserSessionId,
                note = "The live view link is delivered directly to the user.",
            });
        }
        catch (JsonException exception)
        {
            Logger.LogWarning(
                exception,
                "[browser-session] failed to parse create result");
            return result;
        }
    }

    public static async Task<AgentResponse> LiveViewUrlMiddleware(
        IEnumerable<ChatMessage> messages,
        AgentSession? session,
        AgentRunOptions? options,
        AIAgent innerAgent,
        CancellationToken cancellationToken)
    {
        var response = await innerAgent.RunAsync(
            messages,
            session,
            options,
            cancellationToken);

        var liveViewUrl = Interlocked.Exchange(ref _liveViewUrl, null);
        if (!string.IsNullOrEmpty(liveViewUrl))
        {
            Logger.LogInformation(
                "[live-view] injecting non-streaming response url={LiveViewUrl}",
                liveViewUrl);
            response.Messages.Add(new ChatMessage(
                ChatRole.Assistant,
                $"\n\n🔴 [Browser Live View]({liveViewUrl})"));
        }
        return response;
    }

    public static async IAsyncEnumerable<AgentResponseUpdate>
        LiveViewUrlStreamingMiddleware(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            AIAgent innerAgent,
            [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await foreach (var update in innerAgent.RunStreamingAsync(
                           messages,
                           session,
                           options,
                           cancellationToken))
        {
            var liveViewUrl = Interlocked.Exchange(ref _liveViewUrl, null);
            if (!string.IsNullOrEmpty(liveViewUrl))
            {
                Logger.LogInformation(
                    "[live-view] injecting streaming response url={LiveViewUrl}",
                    liveViewUrl);
                yield return new AgentResponseUpdate(
                    ChatRole.Assistant,
                    [new TextContent(
                        $"🔴 Created Browser Session: [Live View]({liveViewUrl})\n\n")]);
            }
            yield return update;
        }

        var finalLiveViewUrl = Interlocked.Exchange(ref _liveViewUrl, null);
        if (!string.IsNullOrEmpty(finalLiveViewUrl))
        {
            Logger.LogInformation(
                "[live-view] appending final streaming response url={LiveViewUrl}",
                finalLiveViewUrl);
            yield return new AgentResponseUpdate(
                ChatRole.Assistant,
                [new TextContent(
                    $"\n\n🔴 [Browser Live View]({finalLiveViewUrl})")])
            {
                FinishReason = ChatFinishReason.Stop,
            };
        }
    }

    private static string SerializeResult(object? result)
    {
        if (result is null)
            return "null";

        if (result is string text)
            return JsonSerializer.Serialize(text);

        try
        {
            return JsonSerializer.Serialize(result, result.GetType());
        }
        catch (Exception exception) when (
            exception is JsonException or NotSupportedException)
        {
            return JsonSerializer.Serialize(result.ToString());
        }
    }

    private static bool TryExtractBrowserSession(
        JsonElement element,
        out string browserSessionId,
        out string? liveViewUrl)
    {
        string? extractedBrowserSessionId = null;
        liveViewUrl = null;
        ExtractBrowserSessionValues(
            element,
            ref extractedBrowserSessionId,
            ref liveViewUrl);
        browserSessionId = extractedBrowserSessionId ?? "";
        return !string.IsNullOrEmpty(browserSessionId);
    }

    private static void ExtractBrowserSessionValues(
        JsonElement element,
        ref string? browserSessionId,
        ref string? liveViewUrl)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (var property in element.EnumerateObject())
                {
                    if (property.Value.ValueKind == JsonValueKind.String)
                    {
                        if (property.Name.Equals(
                                "browserSessionId",
                                StringComparison.OrdinalIgnoreCase))
                            browserSessionId ??= property.Value.GetString();
                        else if (property.Name.Equals(
                                     "liveViewUrl",
                                     StringComparison.OrdinalIgnoreCase))
                            liveViewUrl ??= property.Value.GetString();
                    }

                    ExtractBrowserSessionValues(
                        property.Value,
                        ref browserSessionId,
                        ref liveViewUrl);
                }
                break;

            case JsonValueKind.Array:
                foreach (var item in element.EnumerateArray())
                {
                    ExtractBrowserSessionValues(
                        item,
                        ref browserSessionId,
                        ref liveViewUrl);
                }
                break;

            case JsonValueKind.String:
                var text = element.GetString();
                if (string.IsNullOrWhiteSpace(text)
                    || (text[0] != '{' && text[0] != '['))
                    break;

                try
                {
                    using var nestedDocument = JsonDocument.Parse(text);
                    ExtractBrowserSessionValues(
                        nestedDocument.RootElement,
                        ref browserSessionId,
                        ref liveViewUrl);
                }
                catch (JsonException exception)
                {
                    Logger.LogDebug(
                        exception,
                        "[browser-session] nested result text was not JSON");
                }
                break;
        }
    }

}
