// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

namespace BrowserAutomation;

internal sealed class ToolCatalog
{
    internal static readonly AsyncLocal<ToolCatalog?> Current = new();
    private readonly Dictionary<string, FunctionTool> _tools = new(StringComparer.Ordinal);

    internal void Capture(ChatOptions? options)
    {
        lock (_tools)
        {
            foreach (var function in options?.Tools?.OfType<AIFunction>() ?? [])
            {
                var parameters = function.JsonSchema.EnumerateObject().ToDictionary(
                    property => property.Name,
                    property => BinaryData.FromString(property.Value.GetRawText()));
                _tools[function.Name] = new FunctionTool(function.Name, parameters, null)
                {
                    Description = function.Description,
                };
            }
        }
    }

    internal void Publish(ResponseObject response)
    {
        lock (_tools)
        {
            response.Tools.Clear();
            foreach (var tool in _tools.Values)
                response.Tools.Add(tool);
        }
    }
}

internal sealed class ToolCatalogChatClient(
    IChatClient innerClient) : DelegatingChatClient(innerClient)
{
    public override Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Capture(options);
        return base.GetResponseAsync(messages, options, cancellationToken);
    }

    public override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Capture(options);
        return base.GetStreamingResponseAsync(messages, options, cancellationToken);
    }

    private void Capture(ChatOptions? options)
    {
        if (ToolCatalog.Current.Value is not { } catalog)
            throw new InvalidOperationException("Tool catalog response handling is required.");
        catalog.Capture(options);
    }
}

internal sealed class ToolCatalogResponseHandler(
    AgentFrameworkResponseHandler innerHandler) : ResponseHandler
{
    public override async IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var catalog = new ToolCatalog();
        await using var events = innerHandler.CreateAsync(
            request, context, cancellationToken).GetAsyncEnumerator(cancellationToken);
        while (true)
        {
            var previous = ToolCatalog.Current.Value;
            bool hasNext;
            try
            {
                // Reapply the scope on each pull; iterator yields restore AsyncLocal values.
                ToolCatalog.Current.Value = catalog;
                hasNext = await events.MoveNextAsync();
            }
            finally
            {
                ToolCatalog.Current.Value = previous;
            }
            if (!hasNext)
                yield break;

            var streamEvent = events.Current;
            switch (streamEvent)
            {
                case ResponseCompletedEvent completed:
                    catalog.Publish(completed.Response);
                    break;
                case ResponseIncompleteEvent incomplete:
                    catalog.Publish(incomplete.Response);
                    break;
                case ResponseFailedEvent failed:
                    catalog.Publish(failed.Response);
                    break;
            }
            yield return streamEvent;
        }
    }
}
