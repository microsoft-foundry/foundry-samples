// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;

namespace EchoClient;

public sealed record ReceivedEvent(double ReceivedMs, JsonElement Payload);
public sealed record StreamSummary(string TaskId, string ArtifactId, int Chunks, double FirstChunkMs, double LastChunkMs, string Output);

public static class EchoValidation
{
    public static async IAsyncEnumerable<JsonElement> ReadSseAsync(
        TextReader reader, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var data = new List<string>();
        while (await reader.ReadLineAsync(cancellationToken) is { } line)
        {
            if (line.StartsWith("data:", StringComparison.Ordinal))
            {
                data.Add(line[5..].TrimStart(' '));
            }
            else if (line.Length == 0 && data.Count > 0)
            {
                using var document = JsonDocument.Parse(string.Join("\n", data));
                data.Clear();
                yield return document.RootElement.Clone();
            }
        }

        if (data.Count > 0)
        {
            throw new InvalidDataException("The SSE stream ended before the final event separator.");
        }
    }

    public static void RequireSse(string? mediaType)
    {
        if (!string.Equals(mediaType, "text/event-stream", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"Expected SSE, received '{mediaType}'. Unary fallback is not accepted.");
        }
    }

    public static JsonElement Result(JsonElement payload, string? expectedRequestId = null)
    {
        if (payload.TryGetProperty("error", out var error))
        {
            throw new InvalidDataException($"A2A protocol error: {error.GetRawText()}");
        }

        if (payload.GetProperty("jsonrpc").GetString() != "2.0"
            || !payload.TryGetProperty("result", out var result))
        {
            throw new InvalidDataException("Expected a native JSON-RPC 2.0 result.");
        }

        if (expectedRequestId is not null && (!payload.TryGetProperty("id", out var id)
            || id.ValueKind != JsonValueKind.String || id.GetString() != expectedRequestId))
        {
            throw new InvalidDataException("JSON-RPC response ID does not match the request.");
        }

        return result;
    }

    public static string Text(JsonElement artifact) => string.Concat(artifact.GetProperty("parts")
        .EnumerateArray().Where(part => part.TryGetProperty("text", out _)).Select(part => part.GetProperty("text").GetString()));

    public static string ValidateTask(JsonElement task, string expected, string? expectedArtifactId = null)
    {
        if (task.GetProperty("status").GetProperty("state").GetString() != "TASK_STATE_COMPLETED")
        {
            throw new InvalidDataException("The Task is not completed.");
        }

        var artifacts = task.GetProperty("artifacts");
        if (artifacts.GetArrayLength() != 1 || Text(artifacts[0]) != expected
            || (expectedArtifactId is not null && artifacts[0].GetProperty("artifactId").GetString() != expectedArtifactId))
        {
            throw new InvalidDataException("The completed Task does not contain the exact expected artifact.");
        }

        return task.GetProperty("id").GetString() ?? throw new InvalidDataException("Task ID is missing.");
    }

    public static StreamSummary ValidateStream(IReadOnlyList<ReceivedEvent> events, string expected)
    {
        var taskIds = new HashSet<string>();
        var artifactIds = new HashSet<string>();
        var chunks = new List<string>();
        var arrivals = new List<double>();
        var states = new List<string>();
        bool finalChunk = false;
        bool completed = false;
        foreach (var received in events)
        {
            if (completed)
            {
                throw new InvalidDataException("Received an event after terminal Task completion.");
            }

            var result = Result(received.Payload);
            foreach (var (field, idField) in new[] { ("task", "id"), ("statusUpdate", "taskId"), ("artifactUpdate", "taskId") })
            {
                if (!result.TryGetProperty(field, out var value))
                {
                    continue;
                }

                taskIds.Add(value.GetProperty(idField).GetString() ?? throw new InvalidDataException("Missing task ID."));
                if (field == "artifactUpdate")
                {
                    bool append = value.TryGetProperty("append", out var appendValue) && appendValue.GetBoolean();
                    if (completed || finalChunk || append != (chunks.Count > 0))
                    {
                        throw new InvalidDataException("Unexpected artifact append/final-chunk ordering.");
                    }

                    var artifact = value.GetProperty("artifact");
                    artifactIds.Add(artifact.GetProperty("artifactId").GetString() ?? throw new InvalidDataException("Missing artifact ID."));
                    chunks.Add(Text(artifact));
                    arrivals.Add(received.ReceivedMs);
                    finalChunk = value.TryGetProperty("lastChunk", out var last) && last.GetBoolean();
                }
                else if (value.TryGetProperty("status", out var status))
                {
                    string state = status.GetProperty("state").GetString()!;
                    states.Add(state);
                    completed = state == "TASK_STATE_COMPLETED";
                }
            }
        }

        string assembled = string.Concat(chunks);
        if (taskIds.Count != 1 || artifactIds.Count != 1 || chunks.Count is < 2 or > 16
            || assembled != expected || !finalChunk || states.LastOrDefault() != "TASK_STATE_COMPLETED")
        {
            throw new InvalidDataException("Expected one completed Task, one artifact, 2-16 chunks, and exact Echo output.");
        }

        if (arrivals[^1] - arrivals[0] < (chunks.Count - 1) * 250)
        {
            throw new InvalidDataException("Possible buffering: artifact updates arrived too close together.");
        }

        return new StreamSummary(taskIds.Single(), artifactIds.Single(), chunks.Count, arrivals[0], arrivals[^1], assembled);
    }
}
