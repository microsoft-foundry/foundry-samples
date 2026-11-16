// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Buffers;
using System.IO.Pipelines;
using System.Runtime.CompilerServices;
using System.Runtime.ExceptionServices;
using System.Text;
using System.Text.Json;
using Azure.AI.AgentServer.Invocations;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.AspNetCore.Http.Features;

namespace VoiceHostedAgent;

/// <summary>Call a streaming HTTP handler in process; never bind an HTTP endpoint.</summary>
public sealed class InvocationAdapter(InvocationHandler handler, ILogger<InvocationAdapter>? logger = null)
{
    private const int MaximumFrameBytes = 512 * 1024;
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
        var completion = new InvocationResponseFeature();
        http.Features.Set<IHttpResponseFeature>(completion);
        http.Request.Method = "POST";
        http.Request.Path = "/invocations";
        http.Request.ContentType = "application/json";
        using var body = new MemoryStream(JsonSerializer.SerializeToUtf8Bytes(new { input = text }));
        http.Request.Body = body;
        http.RequestAborted = lifetime.Token;
        await using var output = pipe.Writer.AsStream(leaveOpen: true);
        http.Features.Set<IHttpResponseBodyFeature>(new InvocationResponseBodyFeature(output, completion));
        var original = session.InvocationContext;
        var context = new InvocationContext(
            inputId, original.SessionId, original.ClientHeaders,
            original.QueryParameters, original.PlatformContext);
        var producer = ProduceAsync();
        var completedNormally = false;
        try
        {
            var completed = false;
            var accumulated = new StringBuilder();
            var outputCharacters = 0;
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
                    if (string.IsNullOrEmpty(chunk) ||
                        (outputCharacters += chunk.EnumerateRunes().Count()) > MaximumOutputCharacters)
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
            completedNormally = true;
        }
        finally
        {
            // Unblock a backpressured writer, cancel the handler and await its finally blocks.
            Exception? cleanupFailure = null;
            try
            {
                if (!completedNormally) { lifetime.Cancel(); }
            }
            catch (Exception error)
            {
                logger?.LogWarning("Handler cancellation callback failed; error_type={ErrorType}",
                    error.GetType().Name);
            }
            try { await pipe.Reader.CompleteAsync(); }
            catch (Exception error) { cleanupFailure = error; }
            try { await producer; }
            catch (Exception error) { cleanupFailure ??= error; }
            // There is no HTTP server to run OnCompleted for this synthetic response.
            // Run every callback, after the handler drains and before CE success.
            while (completion.Callbacks.TryPop(out var callback))
            {
                try { await callback.Callback(callback.State); }
                catch (Exception error) { cleanupFailure ??= error; }
            }
            if (cleanupFailure is not null)
            {
                if (completedNormally) { ExceptionDispatchInfo.Throw(cleanupFailure); }
                logger?.LogWarning("Handler completion failed; error_type={ErrorType}",
                    cleanupFailure.GetType().Name);
            }
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
                // Flush BodyWriter's buffered tail while the reader is still consuming.
                // Finalization must not replace a primary handler/startup failure.
                try { await http.Response.CompleteAsync(); }
                catch (Exception exception) { failure ??= exception; }
                await pipe.Writer.CompleteAsync(failure);
            }
        }
    }

    private sealed class InvocationResponseFeature : HttpResponseFeature
    {
        private readonly Stack<(Func<object, Task> Callback, object State)> _starting = new();
        private Task? _start;
        private bool _hasStarted;

        internal Stack<(Func<object, Task> Callback, object State)> Callbacks { get; } = new();
        internal Exception? BodyFailure { get; set; }

        public override bool HasStarted => _hasStarted;

        public override void OnStarting(Func<object, Task> callback, object state)
        {
            if (HasStarted) { throw new InvalidOperationException("The response has already started."); }
            _starting.Push((callback, state));
        }

        public override void OnCompleted(Func<object, Task> callback, object state) =>
            Callbacks.Push((callback, state));

        // Cache faults too: catching a failed write cannot turn failed startup into success.
        internal Task StartAsync() => _start ??= StartCoreAsync();

        private async Task StartCoreAsync()
        {
            while (_starting.TryPop(out var callback))
            {
                await callback.Callback(callback.State);
            }
            _hasStarted = true;
            if (Headers is HeaderDictionary headers) { headers.IsReadOnly = true; }
        }
    }

    // Reuse ASP.NET's buffering/completion and PipeWriter's Stream adapter. Both public
    // body APIs share startup, including FlushAsync when no bytes have been buffered.
    private sealed class InvocationResponseBodyFeature(Stream output, InvocationResponseFeature response)
        : StreamResponseBodyFeature(output), IHttpResponseBodyFeature
    {
        private PipeWriter? _writer;
        private Stream? _stream;

        private PipeWriter StartingWriter => _writer ??= new StartingResponseWriter(base.Writer, response);
        PipeWriter IHttpResponseBodyFeature.Writer => StartingWriter;
        Stream IHttpResponseBodyFeature.Stream => _stream ??= StartingWriter.AsStream(leaveOpen: true);

        public override async Task StartAsync(CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await response.StartAsync();
            await base.StartAsync(cancellationToken);
        }

        public override async Task CompleteAsync()
        {
            try
            {
                if (response.BodyFailure is { } failure) { ExceptionDispatchInfo.Throw(failure); }
                await response.StartAsync();
            }
            catch (Exception error)
            {
                // Release buffered memory even when startup failed; do not flush failed output.
                await base.Writer.CompleteAsync(error);
                throw;
            }
            await base.CompleteAsync();
        }
    }

    private sealed class StartingResponseWriter(PipeWriter writer, InvocationResponseFeature response) : PipeWriter
    {
        public override void Advance(int bytes) => writer.Advance(bytes);
        public override Memory<byte> GetMemory(int sizeHint = 0) => writer.GetMemory(sizeHint);
        public override Span<byte> GetSpan(int sizeHint = 0) => writer.GetSpan(sizeHint);
        public override void CancelPendingFlush() => writer.CancelPendingFlush();
        public override bool CanGetUnflushedBytes => writer.CanGetUnflushedBytes;
        public override long UnflushedBytes => writer.UnflushedBytes;
        public override void Complete(Exception? exception = null) =>
            CompleteAsync(exception).AsTask().GetAwaiter().GetResult();

        public override async ValueTask<FlushResult> FlushAsync(CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await response.StartAsync();
            return await writer.FlushAsync(cancellationToken);
        }

        public override async ValueTask CompleteAsync(Exception? exception = null)
        {
            if (exception is not null)
            {
                response.BodyFailure ??= exception;
                await writer.CompleteAsync(exception);
                return;
            }
            try { await response.StartAsync(); }
            catch (Exception error)
            {
                await writer.CompleteAsync(exception ?? error);
                throw;
            }
            await writer.CompleteAsync(exception);
        }
    }

    private static void ValidateResponse(HttpResponse response)
    {
        if (response.StatusCode is < 200 or >= 300 ||
            !string.Equals(response.ContentType?.Split(';', 2)[0].Trim(),
                "text/event-stream", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Expected a successful SSE invocation response.");
        }
    }

    internal static async IAsyncEnumerable<JsonElement> ReadEventsAsync(
        Stream input,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var utf8 = new UTF8Encoding(false, true);
        var buffer = new byte[4096];
        var line = new ArrayBufferWriter<byte>();
        var data = new List<string>();
        var firstLine = true;
        var skipLf = false;
        var frameBytes = 0;
        int count;
        while ((count = await input.ReadAsync(buffer, cancellationToken)) != 0)
        {
            for (var index = 0; index < count; index++)
            {
                var value = buffer[index];
                if (skipLf)
                {
                    skipLf = false;
                    if (value == '\n')
                    {
                        continue;
                    }
                }
                // Normalize CRLF to LF and exempt one leading UTF-8 BOM from the budget.
                if (++frameBytes > MaximumFrameBytes + (firstLine ? 3 : 0))
                {
                    throw new InvalidOperationException("SSE frame exceeds its byte budget.");
                }
                if (value is (byte)'\n' or (byte)'\r')
                {
                    var message = FinishLine();
                    skipLf = value == '\r';
                    if (message.HasValue)
                    {
                        yield return message.Value;
                    }
                }
                else
                {
                    line.GetSpan(1)[0] = value;
                    line.Advance(1);
                }
            }
            cancellationToken.ThrowIfCancellationRequested();
            await Task.Yield();
        }
        if (line.WrittenCount != 0)
        {
            FinishLine(); // EOF never supplies an event's missing blank line.
        }
        if (data.Count != 0)
        {
            throw new InvalidOperationException("SSE ended inside an event.");
        }

        JsonElement? FinishLine()
        {
            var text = utf8.GetString(line.WrittenSpan);
            line.Clear();
            if (firstLine)
            {
                firstLine = false;
                if (text.StartsWith('\uFEFF'))
                {
                    text = text[1..];
                    frameBytes -= 3;
                }
            }
            if (frameBytes > MaximumFrameBytes)
            {
                throw new InvalidOperationException("SSE frame exceeds its byte budget.");
            }
            if (text.Length == 0)
            {
                frameBytes = 0;
                if (data.Count != 0)
                {
                    var payload = string.Join('\n', data);
                    data.Clear();
                    using var document = JsonDocument.Parse(payload);
                    if (document.RootElement.ValueKind != JsonValueKind.Object)
                    {
                        throw new InvalidOperationException("Expected a JSON SSE object.");
                    }
                    return document.RootElement.Clone();
                }
            }
            else
            {
                var colon = text.IndexOf(':');
                var field = colon < 0 ? text : text[..colon];
                if (field == "data")
                {
                    var value = colon < 0 ? "" : text[(colon + 1)..];
                    data.Add(value.StartsWith(' ') ? value[1..] : value);
                }
            }
            return null;
        }
    }
}
