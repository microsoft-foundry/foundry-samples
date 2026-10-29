// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Azure.Core;
using Azure.Identity;
using EchoClient;

var options = new Dictionary<string, string>(StringComparer.Ordinal);
for (int i = 0; i < args.Length; i += 2)
{
    if (i + 1 == args.Length || args[i] is not ("--deployments" or "--local-server" or "--output" or "--scenarios"))
    {
        throw new ArgumentException("Use --deployments <file> OR --local-server <dll>, --output <directory>, and optionally --scenarios 1,3,12.");
    }
    options.Add(args[i], args[i + 1]);
}
bool local = options.ContainsKey("--local-server");
if (local == options.ContainsKey("--deployments")) { throw new ArgumentException("Specify exactly one execution target."); }
string runId = $"{DateTime.UtcNow:yyyyMMddHHmmss}-{Guid.NewGuid():N}"[..25];
string output = Path.GetFullPath(options.GetValueOrDefault("--output", Path.Combine(".runs", runId)));
Directory.CreateDirectory(output);
var jsonOptions = new JsonSerializerOptions { WriteIndented = true, PropertyNameCaseInsensitive = true };
Deployment? deployment = local ? null : JsonSerializer.Deserialize<Deployment>(
    File.ReadAllText(options["--deployments"]), jsonOptions) ?? throw new InvalidDataException("Deployment state is empty.");
int[] selected = options.TryGetValue("--scenarios", out string? selector)
    ? selector.Split(',').Select(int.Parse).Distinct().ToArray() : Enumerable.Range(1, 12).ToArray();
if (selected.Length == 0 || selected.Any(n => n is < 1 or > 12)) { throw new ArgumentException("Scenarios must be 1 through 12."); }
if (deployment is not null && selected.Any(n => deployment.Agents.Count(a => a.Scenario == n
    && !string.IsNullOrEmpty(a.Name) && !string.IsNullOrEmpty(a.Version)) != 1))
{
    throw new InvalidDataException("Deployment state must contain exactly one pinned agent/version for each selected scenario.");
}
using var http = new HttpClient { Timeout = TimeSpan.FromMinutes(3) };
if (!local)
{
    var token = await new AzureDeveloperCliCredential().GetTokenAsync(new TokenRequestContext(["https://ai.azure.com/.default"]));
    http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
}
var results = new List<ScenarioResult>();
foreach (int number in selected)
{
    string directory = Path.Combine(output, $"s{number:D2}");
    Directory.CreateDirectory(directory);
    string session = $"a2a-s{number:D2}-{runId}";
    Agent? agent = deployment?.Agents.Single(a => a.Scenario == number);
    var evidence = new List<object>();
    var checks = new List<string>();
    var sessions = new List<string>();
    var timer = Stopwatch.StartNew();
    LocalHost? host = null;
    string endpoint = local ? $"http://localhost:{18500 + number}/a2a"
        : $"{deployment!.ProjectEndpoint.TrimEnd('/')}/agents/{agent!.Name}/endpoint/protocols/a2a?api-version=v1";
    string traceId = Guid.NewGuid().ToString("N");
    string? failure = null;
    try
    {
        if (local) { host = await LocalHost.Start(options["--local-server"], number, directory, http); }
        else { await CreateSession(session); }
        var wire = new Wire(http, endpoint, session, traceId, evidence);
        string input = $"scenario-{number:D2}-{runId}";
        switch (number)
        {
            case 2:
            case 7:
            case 12:
            {
                var result = await wire.Rpc("SendMessage", Message(input));
                var task = result.GetProperty("task");
                string id = EchoValidation.ValidateTask(task, $"Echo: {input}");
                string context = task.GetProperty("contextId").GetString()!;
                checks.Add("Completed Task contains exactly one exact Echo artifact.");
                if (number == 12)
                {
                    if (local)
                    {
                        await host!.DisposeAsync();
                        host = await LocalHost.Start(options["--local-server"], number, directory, http, "restored");
                    }
                    else
                    {
                        string second = session + "-b";
                        await CreateSession(second);
                        wire = new Wire(http, endpoint, second, traceId, evidence);
                        checks.Add($"Independent hosted sessions: {session}, {second}; same authenticated caller.");
                    }
                }
                var restored = await wire.Rpc("GetTask", new { id });
                Require(EchoValidation.ValidateTask(restored, $"Echo: {input}") == id, "GetTask returned a different Task.");
                Require(restored.GetProperty("contextId").GetString() == context, "GetTask changed the context.");
                checks.Add(number == 12 ? local ? "File-backed snapshot survived process reconstruction." : "Foundry-backed snapshot retrieved in a second hosted session."
                    : "GetTask preserves Task identity, context and artifact.");
                if (number == 12)
                {
                    var page = await wire.Rpc("ListTasks", new { contextId = context, pageSize = 1, includeArtifacts = true });
                    var tasks = page.GetProperty("tasks");
                    Require(tasks.GetArrayLength() == 1 && EchoValidation.ValidateTask(tasks[0], $"Echo: {input}") == id,
                        "ListTasks did not return the saved snapshot in the second session.");
                    checks.Add("ListTasks reads the saved Task with its artifact in the second host/session.");
                }
                break;
            }
            case 3:
            {
                input = "first\nsecond\nthird\nfourth";
                var stream = await wire.Stream(Message(input));
                Require(stream.Chunks == 4, "Expected four paced artifact chunks.");
                var saved = await wire.Rpc("GetTask", new { id = stream.TaskId });
                EchoValidation.ValidateTask(saved, $"Echo: {input}", stream.ArtifactId);
                evidence.Add(new { stream });
                checks.Add("Four SSE chunks; matching RPC/Task/artifact IDs; append/final flags; exact assembled artifact and terminal completion.");
                checks.Add("Measured first-to-last artifact arrival spread >= 450 ms (three 250 ms server delays).");
                break;
            }
            case 4:
            {
                var initial = (await wire.Rpc("SendMessage", Message("Prepare a greeting"))).GetProperty("task");
                Require(State(initial) == "TASK_STATE_INPUT_REQUIRED", "Expected input-required.");
                Require(EchoValidation.Text(initial.GetProperty("status").GetProperty("message")) == "Who should I greet?",
                    "Clarification prompt was not returned.");
                string id = initial.GetProperty("id").GetString()!;
                string context = initial.GetProperty("contextId").GetString()!;
                var other = (await wire.Rpc("SendMessage", Message("Another greeting", contextId: context))).GetProperty("task");
                Require(other.GetProperty("id").GetString() != id && other.GetProperty("contextId").GetString() == context,
                    "A new message in the same context must create a separate Task.");
                var completed = (await wire.Rpc("SendMessage", Message("Ada", id, context))).GetProperty("task");
                Require(EchoValidation.ValidateTask(completed, "Hello, Ada!") == id
                    && completed.GetProperty("contextId").GetString() == context, "Continuation changed Task/context identity.");
                checks.Add("Exact clarification; independent Task in the same context; original Task/context completed with Hello, Ada!.");
                break;
            }
            case 5:
            {
                var initial = (await wire.Rpc("SendMessage", Message(input, immediately: true))).GetProperty("task");
                Require(State(initial) is "TASK_STATE_SUBMITTED" or "TASK_STATE_WORKING", "returnImmediately did not return an unfinished Task.");
                string id = initial.GetProperty("id").GetString()!;
                var pollTimer = Stopwatch.StartNew();
                JsonElement current;
                do
                {
                    await Task.Delay(150);
                    current = await wire.Rpc("GetTask", new { id });
                    Require(State(current) is "TASK_STATE_SUBMITTED" or "TASK_STATE_WORKING" or "TASK_STATE_COMPLETED",
                        "Long-running Task entered an unexpected state.");
                } while (State(current) != "TASK_STATE_COMPLETED" && pollTimer.Elapsed < TimeSpan.FromSeconds(30));
                Require(EchoValidation.ValidateTask(current, $"Report: {input}") == id, "Polling changed the Task.");
                checks.Add("returnImmediately returned unfinished; polling observed exact completed report on the same Task.");
                break;
            }
            default:
            {
                string prefix = number switch { 6 => "Welcome", 9 => "Configured", 10 => "Composed", _ => "Echo" };
                var reply = await wire.Rpc("SendMessage", Message(input));
                Require(EchoValidation.Text(reply.GetProperty("message")) == $"{prefix}: {input}", "Message-only reply differs.");
                Require(!reply.TryGetProperty("task", out _), "Expected a message-only reply, not a Task.");
                checks.Add($"Exact message-only {prefix} reply from the scenario's fixed startup.");
                if (number == 10)
                {
                    string invocationEndpoint = local ? endpoint[..^4] + "/invocations"
                        : $"{deployment!.ProjectEndpoint.TrimEnd('/')}/agents/{agent!.Name}/endpoint/protocols/invocations?api-version=v1";
                    string status = await wire.Text(HttpMethod.Post, invocationEndpoint, "status");
                    Require(status == "Agent is ready", "Independent Invocations endpoint did not return its exact response.");
                    checks.Add("Same agent/session also serves the independent Invocations handler.");
                }
                if (number == 11 && local)
                {
                    Require(await wire.Text(HttpMethod.Get, endpoint[..^4] + "/", null) == "My application", "Application route is missing.");
                    await wire.Text(HttpMethod.Get, endpoint[..^4] + "/readiness", null);
                    checks.Add("Own application route, readiness, and A2A coexist.");
                }
                break;
            }
        }
        if (local)
        {
            Require(host!.Logs.Contains($"A2A_SUITE_CONFIG_VERIFIED scenario={number} ", StringComparison.Ordinal),
                "Startup configuration verification marker is missing.");
            checks.Add("Startup verifier checked DI/store/native options and configured health/shutdown where applicable.");
        }
    }
    catch (Exception ex) when (ex is not OutOfMemoryException)
    {
        failure = ex.ToString();
    }
    finally
    {
        if (host is not null) { await host.DisposeAsync(); }
    }
    if (!local)
    {
        foreach (string createdSession in sessions)
        {
            try
            {
                string logs = await Commands.Run("azd", ["ai", "agent", "monitor", agent!.Name, "--session-id", createdSession,
                    "--tail", "300", "--utc", "--cwd", deployment!.DeploymentRoot, "--environment", deployment.Environment]);
                await File.WriteAllTextAsync(Path.Combine(directory, createdSession + ".log"), logs);
                Require(logs.Contains($"A2A_SUITE_CONFIG_VERIFIED scenario={number} source_sha={agent.SourceSha ?? deployment.SourceSha} ", StringComparison.Ordinal),
                    "Hosted startup verification for this scenario/SDK source was not found.");
                if (number == 12) { Require(logs.Contains("store=FoundryTaskStore", StringComparison.Ordinal), "Hosted persistence did not use FoundryTaskStore."); }
                checks.Add($"Hosted startup contract confirmed in {createdSession}.");
            }
            catch (Exception ex) when (ex is not OutOfMemoryException)
            {
                failure = failure is null ? ex.ToString() : failure + "\nLog verification also failed:\n" + ex;
            }
        }
    }
    var resultEntry = new ScenarioResult(number, agent?.Name, agent?.Version, session, traceId,
        failure is null ? "PASS" : "FAIL", timer.Elapsed.TotalSeconds, checks, failure);
    results.Add(resultEntry);
    await File.WriteAllTextAsync(Path.Combine(directory, "wire.json"), JsonSerializer.Serialize(evidence, jsonOptions));
    await File.WriteAllTextAsync(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(resultEntry, jsonOptions));
    Console.WriteLine($"s{number:D2}: {resultEntry.Status} ({timer.Elapsed.TotalSeconds:F1}s){(failure is null ? "" : " - " + failure.Split('\n')[0])}");

    async Task CreateSession(string id)
    {
        string result = await Commands.Run("azd", ["ai", "agent", "sessions", "create", agent!.Name, agent.Version,
            "--session-id", id, "--output", "json", "--no-prompt", "--cwd", deployment!.DeploymentRoot,
            "--environment", deployment.Environment]);
        await File.WriteAllTextAsync(Path.Combine(directory, id + ".json"), result);
        using var created = JsonDocument.Parse(result);
        Require(created.RootElement.GetProperty("agent_session_id").GetString() == id
            && created.RootElement.GetProperty("version_indicator").GetProperty("agent_version").GetString() == agent.Version
            && created.RootElement.GetProperty("status").GetString() == "active",
            "Created session does not match the requested ID, pinned version or active status.");
        sessions.Add(id);
        checks.Add($"Session {id} is active and pinned to version {agent.Version}.");
    }
}
await File.WriteAllTextAsync(Path.Combine(output, "summary.json"), JsonSerializer.Serialize(
    new { runId, mode = local ? "local" : "hosted", deployment, startedScenarios = selected, results }, jsonOptions));
Console.WriteLine($"Evidence: {output}");
Environment.ExitCode = results.All(r => r.Status == "PASS") ? 0 : 1;

static void Require(bool condition, string message)
{
    if (!condition) { throw new InvalidDataException(message); }
}
static string? State(JsonElement task) => task.GetProperty("status").GetProperty("state").GetString();
static object Message(string text, string? taskId = null, string? contextId = null, bool immediately = false) => new
{
    message = new { messageId = Guid.NewGuid().ToString("N"), role = "ROLE_USER", parts = new[] { new { text } }, taskId, contextId },
    configuration = new { returnImmediately = immediately },
};

sealed record Deployment(string ProjectEndpoint, string DeploymentRoot, string Environment, string SourceSha, Agent[] Agents);
sealed record Agent(int Scenario, string Name, string Version, string? SourceSha = null);
sealed record ScenarioResult(int Scenario, string? Agent, string? Version, string Session, string TraceId, string Status,
    double DurationSeconds, List<string> Checks, string? Error);

sealed class Wire(HttpClient http, string endpoint, string session, string traceId, List<object> evidence)
{
    public async Task<JsonElement> Rpc(string method, object parameters)
    {
        string id = Guid.NewGuid().ToString("N");
        string body = JsonSerializer.Serialize(new { jsonrpc = "2.0", id, method, @params = parameters });
        string response = await Text(HttpMethod.Post, endpoint, body);
        using var json = JsonDocument.Parse(response);
        return EchoValidation.Result(json.RootElement, id).Clone();
    }

    public async Task<StreamSummary> Stream(object parameters)
    {
        string id = Guid.NewGuid().ToString("N");
        string body = JsonSerializer.Serialize(new { jsonrpc = "2.0", id, method = "SendStreamingMessage", @params = parameters });
        using var request = Request(HttpMethod.Post, endpoint, body);
        request.Headers.Accept.ParseAdd("text/event-stream");
        var timer = Stopwatch.StartNew();
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
        evidence.Add(new { method = "POST", endpoint, session, request = body, status = (int)response.StatusCode });
        response.EnsureSuccessStatusCode();
        EchoValidation.RequireSse(response.Content.Headers.ContentType?.MediaType);
        using var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(2));
        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync(deadline.Token));
        var events = new List<ReceivedEvent>();
        await foreach (var payload in EchoValidation.ReadSseAsync(reader, deadline.Token))
        {
            var received = new ReceivedEvent(timer.Elapsed.TotalMilliseconds, payload);
            evidence.Add(received);
            EchoValidation.Result(payload, id);
            events.Add(received);
        }
        return EchoValidation.ValidateStream(events, "Echo: first\nsecond\nthird\nfourth", minimumChunkGapMs: 150);
    }

    public async Task<string> Text(HttpMethod method, string uri, string? body)
    {
        using var request = Request(method, uri, body);
        var timer = Stopwatch.StartNew();
        using var response = await http.SendAsync(request);
        string text = await response.Content.ReadAsStringAsync();
        evidence.Add(new { method = method.Method, endpoint = uri, session, request = body,
            status = (int)response.StatusCode, receivedMs = timer.Elapsed.TotalMilliseconds, response = text });
        response.EnsureSuccessStatusCode();
        return text;
    }

    private HttpRequestMessage Request(HttpMethod method, string uri, string? body)
    {
        var request = new HttpRequestMessage(method, uri);
        request.Headers.Add("A2A-Version", "1.0");
        request.Headers.Add("x-agent-session-id", session);
        request.Headers.Add("traceparent", $"00-{traceId}-{Guid.NewGuid():N}"[..52] + "-01");
        if (body is not null) { request.Content = new StringContent(body, Encoding.UTF8, "application/json"); }
        return request;
    }
}

static class Commands
{
    public static async Task<string> Run(string executable, string[] arguments)
    {
        var info = new ProcessStartInfo(executable) { RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (string argument in arguments) { info.ArgumentList.Add(argument); }
        using var process = Process.Start(info) ?? throw new IOException($"Could not start {executable}.");
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(5));
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException) { process.Kill(entireProcessTree: true); throw; }
        string result = await stdout;
        string errors = await stderr;
        if (process.ExitCode != 0) { throw new IOException($"{executable} failed ({process.ExitCode}): {result}\n{errors}"); }
        return result + (arguments.Contains("--output") ? "" : errors);
    }
}

sealed class LocalHost : IAsyncDisposable
{
    private readonly Process process;
    private readonly string path;
    private readonly StringBuilder logs = new();
    private bool disposed;
    public string Logs { get { lock (logs) { return logs.ToString(); } } }
    private LocalHost(Process process, string path)
    {
        this.process = process;
        this.path = path;
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) { lock (logs) { logs.AppendLine(e.Data); } } };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) { lock (logs) { logs.AppendLine(e.Data); } } };
    }

    public static async Task<LocalHost> Start(string dll, int scenario, string directory, HttpClient http, string suffix = "initial")
    {
        var reservation = new System.Net.Sockets.TcpListener(IPAddress.Any, 18500 + scenario);
        reservation.Server.ExclusiveAddressUse = true;
        try { reservation.Start(); }
        finally { reservation.Stop(); }
        var info = new ProcessStartInfo("dotnet") { RedirectStandardOutput = true, RedirectStandardError = true };
        info.ArgumentList.Add(Path.GetFullPath(dll));
        info.Environment["A2A_SUITE_SCENARIO"] = scenario.ToString();
        info.Environment["PORT"] = (18500 + scenario).ToString();
        info.Environment["AGENTSERVER_STATE_ROOT"] = Path.Combine(directory, "state");
        info.Environment.Remove("FOUNDRY_HOSTING_ENVIRONMENT");
        info.Environment.Remove("APPLICATIONINSIGHTS_CONNECTION_STRING");
        info.Environment.Remove("OTEL_EXPORTER_OTLP_ENDPOINT");
        var process = new Process { StartInfo = info };
        var host = new LocalHost(process, Path.Combine(directory, $"host-{suffix}.log"));
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        try
        {
            var timer = Stopwatch.StartNew();
            while (timer.Elapsed < TimeSpan.FromSeconds(40))
            {
                if (process.HasExited) { throw new IOException($"Local host exited: {host.Logs}"); }
                try
                {
                    using var response = await http.GetAsync($"http://localhost:{18500 + scenario}/readiness");
                    if (response.IsSuccessStatusCode) { return host; }
                }
                catch (HttpRequestException ex) when (ex.InnerException is System.Net.Sockets.SocketException) { }
                await Task.Delay(100);
            }
            throw new TimeoutException($"Local host not ready: {host.Logs}");
        }
        catch { await host.DisposeAsync(); throw; }
    }

    public async ValueTask DisposeAsync()
    {
        if (disposed) { return; }
        disposed = true;
        if (!process.HasExited) { process.Kill(entireProcessTree: true); }
        await process.WaitForExitAsync();
        await File.WriteAllTextAsync(path, Logs);
        process.Dispose();
    }
}
