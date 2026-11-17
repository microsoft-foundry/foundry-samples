// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Azure.Core;
using Azure.Identity;
using EchoClient;

var options = new Dictionary<string, string>(StringComparer.Ordinal);
var switches = new HashSet<string>(StringComparer.Ordinal);
for (int index = 0; index < args.Length; index++)
{
    if (args[index] is "--stream" or "--azure-auth")
    {
        switches.Add(args[index]);
    }
    else if (args[index] is "--endpoint" or "--session-id" or "--message" or "--output" or "--card-endpoint")
    {
        if (++index >= args.Length)
        {
            throw new ArgumentException("Missing option value.");
        }

        options.Add(args[index - 1], args[index]);
    }
    else
    {
        throw new ArgumentException($"Unknown argument '{args[index]}'.");
    }
}

bool streaming = switches.Contains("--stream");
string endpoint = options.GetValueOrDefault("--endpoint", "http://localhost:8088/a2a");
string message = options.GetValueOrDefault("--message", streaming
    ? "Step 1: Receive the request.\nStep 2: Start the A2A Task.\nStep 3: Prepare the response.\nStep 4: Send this line immediately.\nStep 5: Keep the connection open.\nStep 6: Append more text to the same artifact.\nStep 7: Check the assembled response.\nStep 8: Complete the Task."
    : "hello");
string expected = $"Echo: {message}";
string traceId = Guid.NewGuid().ToString("N");
string parentId = Guid.NewGuid().ToString("N")[..16];
var evidence = new Dictionary<string, object?>
{
    ["endpoint"] = endpoint, ["trace_id"] = traceId, ["parent_id"] = parentId,
    ["session_id"] = options.GetValueOrDefault("--session-id"), ["started_utc"] = DateTimeOffset.UtcNow,
};
var events = new List<ReceivedEvent>();
evidence["events"] = events;
using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(180) };
client.DefaultRequestHeaders.Add("A2A-Version", "1.0");
client.DefaultRequestHeaders.Add("traceparent", $"00-{traceId}-{parentId}-01");
if (options.TryGetValue("--session-id", out string? session))
{
    client.DefaultRequestHeaders.Add("x-agent-session-id", session);
}

try
{
    if (switches.Contains("--azure-auth"))
    {
        var credential = new AzureDeveloperCliCredential();
        AccessToken token = await credential.GetTokenAsync(new TokenRequestContext(["https://ai.azure.com/.default"]));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
    }

    if (options.TryGetValue("--card-endpoint", out string? cardEndpoint))
    {
        using var card = JsonDocument.Parse(await client.GetStringAsync(cardEndpoint));
        evidence["agent_card"] = card.RootElement.Clone();
        Console.WriteLine($"CARD streaming={card.RootElement.GetProperty("capabilities").GetRawText()}");
    }

    string requestId = Guid.NewGuid().ToString("N");
    string requestJson = JsonSerializer.Serialize(new
    {
        jsonrpc = "2.0", id = requestId,
        method = streaming ? "SendStreamingMessage" : "SendMessage",
        @params = new
        {
            message = new
            {
                messageId = Guid.NewGuid().ToString("N"), role = "ROLE_USER",
                parts = new[] { new { text = message } }, metadata = new { streaming_demo = streaming },
            },
        },
    });
    evidence["request_json"] = requestJson;
    Console.WriteLine($"SENT {requestJson}");
    var started = Stopwatch.StartNew();
    using var request = new HttpRequestMessage(HttpMethod.Post, endpoint)
    {
        Content = new StringContent(requestJson, Encoding.UTF8, "application/json"),
    };
    request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(streaming ? "text/event-stream" : "application/json"));
    using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
    response.EnsureSuccessStatusCode();
    evidence["http_status"] = (int)response.StatusCode;
    evidence["content_type"] = response.Content.Headers.ContentType?.ToString();
    evidence["session_header"] = response.Headers.TryGetValues("x-agent-session-id", out var sessionHeaders)
        ? string.Join(",", sessionHeaders) : null;
    string taskId;
    string? artifactId = null;
    if (streaming)
    {
        EchoValidation.RequireSse(response.Content.Headers.ContentType?.MediaType);
        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync());
        await foreach (var payload in EchoValidation.ReadSseAsync(reader))
        {
            double elapsed = started.Elapsed.TotalMilliseconds;
            EchoValidation.Result(payload, requestId);
            events.Add(new ReceivedEvent(elapsed, payload));
            Console.WriteLine($"RECEIVED +{elapsed,8:F2}ms {payload.GetRawText()}");
        }

        var summary = EchoValidation.ValidateStream(events, expected);
        taskId = summary.TaskId;
        artifactId = summary.ArtifactId;
        evidence["stream"] = summary;
    }
    else
    {
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        evidence["response"] = json.RootElement.Clone();
        taskId = EchoValidation.ValidateTask(EchoValidation.Result(json.RootElement, requestId).GetProperty("task"), expected);
    }

    string getRequestId = Guid.NewGuid().ToString("N");
    string getJson = JsonSerializer.Serialize(new { jsonrpc = "2.0", id = getRequestId, method = "GetTask", @params = new { id = taskId } });
    using var getResponse = await client.PostAsync(endpoint, new StringContent(getJson, Encoding.UTF8, "application/json"));
    getResponse.EnsureSuccessStatusCode();
    using var stored = JsonDocument.Parse(await getResponse.Content.ReadAsStringAsync());
    if (EchoValidation.ValidateTask(EchoValidation.Result(stored.RootElement, getRequestId), expected, artifactId) != taskId)
    {
        throw new InvalidDataException("GetTask returned a different Task.");
    }

    evidence["get_task_response"] = stored.RootElement.Clone();
    evidence["get_task_verified"] = true;
    evidence["task_id"] = taskId;
    evidence["assembled_output"] = expected;
    evidence["sha256"] = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(expected))).ToLowerInvariant();
    evidence["outcome"] = "PASS";
    Console.WriteLine($"PASS: exact Echo artifact and GetTask verified. Task={taskId} Trace={traceId}");
}
catch (Exception exception)
{
    evidence["outcome"] = "FAIL";
    evidence["error"] = exception.Message;
    Console.Error.WriteLine(exception);
    Environment.ExitCode = 1;
}
finally
{
    evidence["finished_utc"] = DateTimeOffset.UtcNow;
    if (options.TryGetValue("--output", out string? output))
    {
        string path = Path.GetFullPath(output);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        await File.WriteAllTextAsync(path, JsonSerializer.Serialize(evidence, new JsonSerializerOptions { WriteIndented = true }));
    }
}
