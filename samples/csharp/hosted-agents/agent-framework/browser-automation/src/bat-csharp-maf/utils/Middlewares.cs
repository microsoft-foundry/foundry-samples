// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
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
    private const string LiveViewStateKey = "BrowserAutomation.LiveViewState";
    private const string LiveViewUrlsKey = "BrowserAutomation.LiveViewUrls";

    private sealed class LiveViewRequestState(ConcurrentDictionary<string, string> urls)
    {
        public ConcurrentDictionary<string, string> Urls { get; } = urls;
        public ConcurrentQueue<KeyValuePair<string, string>> Pending { get; } = new();
    }

    public static async ValueTask<object?> FunctionInvocationMiddleware(
        AIAgent agent,
        FunctionInvocationContext context,
        Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next,
        CancellationToken cancellationToken)
    {
        var functionName = context.Function.Name;
        Logger.LogInformation("[tool] name={Name}", functionName);

        var isClose = functionName.EndsWith(
            "close_browser_session",
            StringComparison.OrdinalIgnoreCase);
        var isCreate = functionName.EndsWith(
            "create_browser_session",
            StringComparison.OrdinalIgnoreCase);
        if (!isCreate && !isClose)
            return await next(context, cancellationToken);

        if (context.Options?.AdditionalProperties?.TryGetValue(LiveViewStateKey, out var value) != true
            || value is not LiveViewRequestState state)
            throw new InvalidOperationException("Browser tools require live-view response middleware.");

        var result = await next(context, cancellationToken);
        var serializedResult = SerializeResult(result);

        try
        {
            using var document = JsonDocument.Parse(serializedResult);
            if (ContainsToolError(document.RootElement))
                return result;

            if (isClose)
            {
                if (context.Arguments.TryGetValue("browserSessionId", out var reference)
                    && reference?.ToString() is { Length: > 0 } closedSessionId)
                    state.Urls.TryRemove(closedSessionId, out _);
                else
                    Logger.LogWarning("[browser-session] close call did not identify a browserSessionId");
                return result;
            }

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
            {
                state.Urls[browserSessionId] = liveViewUrl;
                state.Pending.Enqueue(new(browserSessionId, liveViewUrl));
            }

            Logger.LogInformation(
                "[browser-session] id={BrowserSessionId}",
                browserSessionId);

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
                "[browser-session] failed to parse browser result");
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
        session ??= await innerAgent.CreateSessionAsync(cancellationToken);
        var (runOptions, state) = PrepareLiveViewState(session, options);
        var response = await innerAgent.RunAsync(
            messages,
            session,
            runOptions,
            cancellationToken);

        cancellationToken.ThrowIfCancellationRequested();
        var footer = FormatLiveViewFooter(state);
        if (footer is not null)
        {
            response.Messages.Add(new ChatMessage(
                ChatRole.Assistant,
                footer));
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
        session ??= await innerAgent.CreateSessionAsync(cancellationToken);
        var (runOptions, state) = PrepareLiveViewState(session, options);
        await foreach (var update in innerAgent.RunStreamingAsync(
                           messages,
                           session,
                           runOptions,
                           cancellationToken))
        {
            cancellationToken.ThrowIfCancellationRequested();
            foreach (var notice in GetCreationNotices(state))
                yield return notice;
            yield return update;
        }

        cancellationToken.ThrowIfCancellationRequested();
        foreach (var notice in GetCreationNotices(state))
            yield return notice;
        var footer = FormatLiveViewFooter(state);
        if (footer is not null)
        {
            yield return new AgentResponseUpdate(
                ChatRole.Assistant,
                [new TextContent(footer)])
            {
                FinishReason = ChatFinishReason.Stop,
            };
        }
    }

    private static (AgentRunOptions Options, LiveViewRequestState State) PrepareLiveViewState(
        AgentSession session, AgentRunOptions? options)
    {
        ConcurrentDictionary<string, string> urls;
        lock (session.StateBag)
        {
            urls = session.StateBag.GetValue<ConcurrentDictionary<string, string>>(LiveViewUrlsKey)
                ?? new ConcurrentDictionary<string, string>();
            session.StateBag.SetValue(LiveViewUrlsKey, urls);
        }
        var state = new LiveViewRequestState(urls);
        var runOptions = options?.Clone() ?? new AgentRunOptions();
        runOptions.AdditionalProperties ??= new();
        runOptions.AdditionalProperties[LiveViewStateKey] = state;
        return (runOptions, state);
    }

    private static IEnumerable<AgentResponseUpdate> GetCreationNotices(LiveViewRequestState state)
    {
        while (state.Pending.TryDequeue(out var browser))
        {
            if (state.Urls.TryGetValue(browser.Key, out var activeUrl) && activeUrl == browser.Value)
                yield return new AgentResponseUpdate(
                    ChatRole.Assistant,
                    [new TextContent(
                        $"🔴 Created Browser Session: [Live View]({browser.Value})\n\n")]);
        }
    }

    private static string? FormatLiveViewFooter(LiveViewRequestState state)
    {
        var browsers = state.Urls.ToArray().OrderBy(pair => pair.Key, StringComparer.Ordinal).ToList();
        return browsers.Count switch
        {
            0 => null,
            1 => $"\n\n🔴 [Browser Live View]({browsers[0].Value})\n",
            _ => "\n\n---\n\n**Active Browser Sessions:**\n\n"
                + string.Join("\n", browsers.Select(browser =>
                    $"- **{browser.Key}**: [Live View]({browser.Value})")) + "\n",
        };
    }

    private static bool ContainsToolError(JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                return element.EnumerateObject().Any(property =>
                    (property.Name.Equals("isError", StringComparison.OrdinalIgnoreCase)
                        && property.Value.ValueKind == JsonValueKind.True)
                    || ContainsToolError(property.Value));
            case JsonValueKind.Array:
                return element.EnumerateArray().Any(ContainsToolError);
            case JsonValueKind.String:
                var text = element.GetString()?.TrimStart();
                if (string.IsNullOrEmpty(text) || (text[0] != '{' && text[0] != '['))
                    return false;
                try
                {
                    using var nested = JsonDocument.Parse(text);
                    return ContainsToolError(nested.RootElement);
                }
                catch (JsonException exception)
                {
                    Logger.LogDebug(exception, "[browser-session] result text was not JSON");
                    return false;
                }
            default:
                return false;
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
