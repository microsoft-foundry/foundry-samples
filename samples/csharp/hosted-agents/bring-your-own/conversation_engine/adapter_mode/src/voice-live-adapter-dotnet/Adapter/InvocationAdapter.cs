// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.IO.Pipelines;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using Azure.AI.AgentServer.Invocations;
using Azure.AI.AgentServer.Invocations.Voice;

namespace VoiceHostedAgent;

/// <summary>Call a streaming HTTP handler in process; never bind an HTTP endpoint.</summary>
public sealed class InvocationAdapter(InvocationHandler handler)
{
    private const int MaximumFrameCharacters = 65_536;
    private const int MaximumOutputCharacters = 8_000;

    internal async IAsyncEnumerable<string> Stream(
        VoiceSession session,
        string inputId,
        string text,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var pipe = new Pipe(new PipeOptions(pauseWriterThreshold: 16_384, resumeWriterThreshold: 8_192));
        var http = new DefaultHttpContext();
        http.Request.Method = "POST";
        http.Request.Path = "/invocations";
        http.Request.ContentType = "application/json";
        using var body = new MemoryStream(JsonSerializer.SerializeToUtf8Bytes(new { input = text }));
        http.Request.Body = body;
        http.RequestAborted = lifetime.Token;
        await using var output = pipe.Writer.AsStream(leaveOpen: true);
        http.Response.Body = output;
        var original = session.InvocationContext;
        var context = new InvocationContext(
            inputId, original.SessionId, original.ClientHeaders,
            original.QueryParameters, original.PlatformContext);
        var producer = ProduceAsync();
        try
        {
            var completed = false;
            var accumulated = new StringBuilder();
            await using var input = pipe.Reader.AsStream(leaveOpen: true);
            await foreach (var message in ReadEventsAsync(input, cancellationToken))
            {
                ValidateResponse(http.Response);
                if (completed)
                {
                    throw new InvalidOperationException("SSE event after done.");
                }
                var type = message.GetProperty("type").GetString();
                if (type == "token")
                {
                    var chunk = message.GetProperty("content").GetString();
                    if (string.IsNullOrEmpty(chunk) || accumulated.Length + chunk.Length > MaximumOutputCharacters)
                    {
                        throw new InvalidOperationException("Invalid or oversized invocation token.");
                    }
                    accumulated.Append(chunk);
                    yield return chunk;
                }
                else if (type == "done" &&
                    message.GetProperty("full_text").GetString() == accumulated.ToString())
                {
                    completed = true;
                }
                else
                {
                    throw new InvalidOperationException("Invalid invocation SSE event.");
                }
            }
            ValidateResponse(http.Response);
            if (!completed)
            {
                throw new InvalidOperationException("Invocation ended without done.");
            }
        }
        finally
        {
            // Unblock a backpressured writer, cancel the handler and await its finally blocks.
            lifetime.Cancel();
            await pipe.Reader.CompleteAsync();
            await producer;
        }

        async Task ProduceAsync()
        {
            Exception? failure = null;
            try
            {
                await handler.HandleAsync(http.Request, http.Response, context, lifetime.Token);
            }
            catch (Exception exception)
            {
                failure = exception;
            }
            finally
            {
                await pipe.Writer.CompleteAsync(failure);
            }
        }
    }

    private static void ValidateResponse(HttpResponse response)
    {
        if (response.StatusCode is < 200 or >= 300 ||
            response.ContentType?.StartsWith("text/event-stream", StringComparison.OrdinalIgnoreCase) != true)
        {
            throw new InvalidOperationException("Expected a successful SSE invocation response.");
        }
    }

    private static async IAsyncEnumerable<JsonElement> ReadEventsAsync(
        Stream input,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        using var reader = new StreamReader(input, new UTF8Encoding(false, true),
            detectEncodingFromByteOrderMarks: false, bufferSize: 1024, leaveOpen: true);
        var chars = new char[1024];
        var pending = "";
        int count;
        while ((count = await reader.ReadAsync(chars.AsMemory(), cancellationToken)) != 0)
        {
            pending = (pending + new string(chars, 0, count)).Replace("\r\n", "\n", StringComparison.Ordinal);
            int boundary;
            while ((boundary = pending.IndexOf("\n\n", StringComparison.Ordinal)) >= 0)
            {
                if (boundary > MaximumFrameCharacters)
                {
                    throw new InvalidOperationException("SSE frame exceeds its character budget.");
                }
                var frame = pending[..boundary];
                pending = pending[(boundary + 2)..];
                var fields = frame.Split('\n').Where(line => line.StartsWith("data:", StringComparison.Ordinal))
                    .Select(line => line[5..].StartsWith(' ') ? line[6..] : line[5..]).ToArray();
                if (fields.Length != 0)
                {
                    using var document = JsonDocument.Parse(string.Join('\n', fields));
                    if (document.RootElement.ValueKind != JsonValueKind.Object)
                    {
                        throw new InvalidOperationException("Expected a JSON SSE object.");
                    }
                    yield return document.RootElement.Clone();
                }
            }
            if (pending.Length > MaximumFrameCharacters)
            {
                throw new InvalidOperationException("SSE frame exceeds its character budget.");
            }
        }
        if (!string.IsNullOrWhiteSpace(pending))
        {
            throw new InvalidOperationException("SSE ended inside a frame.");
        }
    }
}
