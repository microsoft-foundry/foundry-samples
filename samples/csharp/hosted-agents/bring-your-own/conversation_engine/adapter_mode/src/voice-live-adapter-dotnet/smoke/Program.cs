// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;


var options = SmokeOptions.Parse(args);
using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
using var socket = new ClientWebSocket();

await socket.ConnectAsync(options.Uri, timeout.Token);
await SendAsync(socket, new
{
    type = "session.start",
    id = "m_smoke_start",
    ts = Timestamp(),
    protocol_version = "1.0",
    reconnect = false,
    response_timeouts = new
    {
        first_output_ms = 30_000,
        idle_ms = 30_000,
        max_duration_ms = 120_000,
    },
}, timeout.Token);

using (var ready = await ReceiveAsync(socket, timeout.Token))
{
    RequireType(ready.RootElement, "session.ready");
}

await SendAsync(socket, new
{
    type = "user.message",
    id = "m_smoke_user",
    ts = Timestamp(),
    item_id = "in_smoke_user",
    content = new[] { new { type = "input_text", text = options.Text } },
}, timeout.Token);

var frameTypes = new List<string>();
var streamedText = new StringBuilder();
string? completedText = null;
string? responseId = null;
string? outputItemId = null;
var sawOutputDone = false;
while (true)
{
    using var frame = await ReceiveAsync(socket, timeout.Token);
    var root = frame.RootElement;
    var frameType = root.GetProperty("type").GetString()
        ?? throw new InvalidOperationException("A frame has no type.");
    frameTypes.Add(frameType);

    switch (frameType)
    {
        case "response.created" when responseId is null && frameTypes.Count == 1:
            responseId = RequiredString(root, "response_id");
            break;
        case "response.output_text.delta" when responseId is not null && !sawOutputDone:
            RequireId(root, "response_id", responseId);
            outputItemId = RequireConsistentId(root, "item_id", outputItemId);
            streamedText.Append(RequiredText(root, "delta"));
            break;
        case "response.output_text.done" when responseId is not null && !sawOutputDone:
            RequireId(root, "response_id", responseId);
            outputItemId = RequireConsistentId(root, "item_id", outputItemId);
            completedText = RequiredText(root, "text");
            if (string.IsNullOrEmpty(completedText))
            {
                throw new InvalidOperationException("Completed output text is empty.");
            }
            sawOutputDone = true;
            break;
        case "response.done" when responseId is not null && sawOutputDone:
            RequireId(root, "response_id", responseId);
            break;
        case "error":
            throw new InvalidOperationException($"Agent returned an error: {root}");
        default:
            throw new InvalidOperationException(
                $"Unexpected or out-of-order frame {frameType}: {root}");
    }

    if (frameType == "response.done")
    {
        break;
    }
}

var expectedFrames = new[] { "response.created" }
    .Concat(Enumerable.Repeat("response.output_text.delta", Regex.Matches(options.Text, @"\s*\S+|\s+$").Count))
    .Concat(new[] { "response.output_text.done", "response.done" })
    .ToArray();
if (!frameTypes.SequenceEqual(expectedFrames))
{
    throw new InvalidOperationException(
        $"Expected {string.Join(',', expectedFrames)}, received {string.Join(',', frameTypes)}.");
}
if (responseId is null || outputItemId is null || !sawOutputDone)
{
    throw new InvalidOperationException("The response did not contain correlated completed output.");
}

if (!string.Equals(completedText, options.Text, StringComparison.Ordinal) ||
    !string.Equals(streamedText.ToString(), options.Text, StringComparison.Ordinal))
{
    throw new InvalidOperationException("Expected the input echoed verbatim in streaming chunks.");
}

Console.WriteLine($"frames={string.Join(',', frameTypes)}");
Console.WriteLine($"response={completedText}");

await SendAsync(socket, new
{
    type = "session.end",
    id = "m_smoke_end",
    ts = Timestamp(),
    reason = "validation_complete",
}, timeout.Token);
await socket.CloseAsync(
    WebSocketCloseStatus.NormalClosure,
    "smoke test complete",
    timeout.Token);

static string Timestamp() => DateTimeOffset.UtcNow.ToString("O");

static async Task SendAsync(
    ClientWebSocket socket,
    object message,
    CancellationToken cancellationToken)
{
    var payload = JsonSerializer.SerializeToUtf8Bytes(message);
    await socket.SendAsync(
        payload,
        WebSocketMessageType.Text,
        endOfMessage: true,
        cancellationToken);
}

static async Task<JsonDocument> ReceiveAsync(
    ClientWebSocket socket,
    CancellationToken cancellationToken)
{
    using var stream = new MemoryStream();
    var buffer = new byte[4096];
    while (true)
    {
        var result = await socket.ReceiveAsync(buffer, cancellationToken);
        if (result.MessageType == WebSocketMessageType.Close)
        {
            throw new InvalidOperationException(
                $"Agent closed the connection: {(int?)result.CloseStatus} {result.CloseStatusDescription}");
        }
        if (result.MessageType != WebSocketMessageType.Text)
        {
            throw new InvalidOperationException($"Unexpected WebSocket message type {result.MessageType}.");
        }

        stream.Write(buffer, 0, result.Count);
        if (result.EndOfMessage)
        {
            return JsonDocument.Parse(stream.ToArray());
        }
    }
}

static void RequireType(JsonElement frame, string expected)
{
    var actual = frame.GetProperty("type").GetString();
    if (!string.Equals(actual, expected, StringComparison.Ordinal))
    {
        throw new InvalidOperationException($"Expected {expected}, received {frame}.");
    }
}

static string RequiredText(JsonElement frame, string propertyName)
{
    var value = frame.GetProperty(propertyName).GetString();
    return string.IsNullOrEmpty(value)
        ? throw new InvalidOperationException($"Frame property {propertyName} is empty: {frame}")
        : value;
}

static string RequiredString(JsonElement frame, string propertyName)
{
    var value = frame.GetProperty(propertyName).GetString();
    return string.IsNullOrWhiteSpace(value)
        ? throw new InvalidOperationException($"Frame property {propertyName} is empty: {frame}")
        : value;
}

static void RequireId(JsonElement frame, string propertyName, string expected)
{
    var actual = RequiredString(frame, propertyName);
    if (!string.Equals(actual, expected, StringComparison.Ordinal))
    {
        throw new InvalidOperationException(
            $"Expected {propertyName} {expected}, received {actual}: {frame}");
    }
}

static string RequireConsistentId(JsonElement frame, string propertyName, string? expected)
{
    var actual = RequiredString(frame, propertyName);
    if (expected is not null && !string.Equals(actual, expected, StringComparison.Ordinal))
    {
        throw new InvalidOperationException(
            $"Expected {propertyName} {expected}, received {actual}: {frame}");
    }
    return actual;
}

internal sealed record SmokeOptions(Uri Uri, string Text)
{
    internal static SmokeOptions Parse(string[] args)
    {
        var uri = new Uri("ws://127.0.0.1:8088/voice_conversation_engine");
        var text = "Hello, Voice Live!";

        for (var index = 0; index < args.Length; index++)
        {
            switch (args[index])
            {
                case "--uri" when index + 1 < args.Length:
                    uri = new Uri(args[++index], UriKind.Absolute);
                    break;
                case "--text" when index + 1 < args.Length:
                    text = args[++index];
                    break;
                default:
                    throw new ArgumentException(
                        "Usage: dotnet run --project smoke/VoiceLiveAdapter.SmokeTest.csproj -- " +
                        "[--uri ws://host/voice_conversation_engine] [--text message]");
            }
        }

        if (uri.Scheme is not ("ws" or "wss"))
        {
            throw new ArgumentException("--uri must use ws or wss.");
        }

        return new SmokeOptions(uri, text);
    }
}
