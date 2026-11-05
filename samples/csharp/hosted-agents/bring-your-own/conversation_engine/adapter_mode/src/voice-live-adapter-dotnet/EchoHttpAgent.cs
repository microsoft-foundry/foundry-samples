// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Encodings.Web;
using System.Text.RegularExpressions;
using Azure.AI.AgentServer.Invocations;

namespace VoiceHostedAgent;

/// <summary>A plain HTTP-shaped Echo handler with no Voice or Bridge state.</summary>
public sealed class EchoHttpAgent : InvocationHandler
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public override async Task HandleAsync(
        HttpRequest request,
        HttpResponse response,
        InvocationContext context,
        CancellationToken cancellationToken)
    {
        using var body = await JsonDocument.ParseAsync(request.Body, cancellationToken: cancellationToken);
        var text = body.RootElement.GetProperty("input").GetString()
            ?? throw new InvalidOperationException("Expected an input string.");
        response.ContentType = "text/event-stream";
        foreach (Match match in Regex.Matches(text, @"\s*\S+|\s+$"))
        {
            cancellationToken.ThrowIfCancellationRequested();
            await Task.Yield();
            await response.WriteAsync(
                "data: " + JsonSerializer.Serialize(new { type = "token", content = match.Value }, JsonOptions) + "\n\n",
                cancellationToken);
            await response.Body.FlushAsync(cancellationToken);
        }
        await response.WriteAsync(
            "data: " + JsonSerializer.Serialize(new { type = "done", full_text = text }, JsonOptions) + "\n\n",
            cancellationToken);
        await response.Body.FlushAsync(cancellationToken);
    }
}
