using Azure.AI.AgentServer.Contracts.Generated.OpenAI;
using Azure.AI.AgentServer.Contracts.Generated.Responses;
using Azure.AI.AgentServer.Core.Common.Http.Json;
using Azure.AI.AgentServer.Core.Common.Id;
using Azure.AI.AgentServer.Responses.Invocation;
using Azure.Identity;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using OpenAIFunctionTool = OpenAI.Responses.FunctionTool;


public sealed class SystemUtilityAgentInvocation : IAgentInvocation
{
    private static readonly ActivitySource ActivitySource = new("SystemUtilityAgent");

    private static readonly object ApiClientLock = new();
    private static Azure.AI.OpenAI.AzureOpenAIClient? ApiClient;

    private static Azure.AI.OpenAI.AzureOpenAIClient GetOrCreateApiClient()
    {
        if (ApiClient is not null)
        {
            return ApiClient;
        }

        lock (ApiClientLock)
        {
            if (ApiClient is not null)
            {
                return ApiClient;
            }

            var aiProjectEndpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT");

            if (string.IsNullOrWhiteSpace(aiProjectEndpoint))
            {
                throw new InvalidOperationException("Missing required environment variable 'AZURE_AI_PROJECT_ENDPOINT'.");
            }

            var aoaiEndpoint = ToAzureOpenAIEndpoint(aiProjectEndpoint);
            var apiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");

            if (!string.IsNullOrWhiteSpace(apiKey))
            {
                var credential = new System.ClientModel.ApiKeyCredential(apiKey);
                ApiClient = new Azure.AI.OpenAI.AzureOpenAIClient(new Uri(aoaiEndpoint), credential);
            }
            else
            {
                var credential = new DefaultAzureCredential();
                ApiClient = new Azure.AI.OpenAI.AzureOpenAIClient(new Uri(aoaiEndpoint), credential);
            }

            return ApiClient;
        }
    }


    private const string SystemPrompt =
        "You are a System Utility Agent.\n" +
        "You can inspect the runtime environment using tools (processes, ports, resources, DNS, environment variables).\n" +
        "Important:\n" +
        "- Call capability_report early when user questions depend on host vs container visibility.\n" +
        "- Never claim you can see host-wide processes/ports unless capability_report indicates it.\n" +
        "- Prefer using tools over guessing.\n" +
        "- Keep outputs clear and actionable.";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false
    };

    public Task<Response> InvokeAsync(CreateResponseRequest request, AgentInvocationContext context,
        CancellationToken cancellationToken = default)
    {
         return InvokeAsyncInternal(request, context, cancellationToken);
    }

    private async Task<Response> InvokeAsyncInternal(CreateResponseRequest request, AgentInvocationContext context,
        CancellationToken cancellationToken)
    {
        var activity = Activity.Current;

        var inputText = GetInputText(request);
        activity?.SetTag("gen_ai.conversation.id", context.ConversationId);

        var responseText = await RunAgentLoopAsync(inputText, context.ConversationId, cancellationToken).ConfigureAwait(false);

        IList<ItemContent> contents =
                [new ItemContentOutputText(text: responseText, annotations: [])];

        IList<ItemResource> outputs =
        [
            new ResponsesAssistantMessageItemResource(
                id: Guid.NewGuid().ToString(),
                status: ResponsesMessageItemResourceStatus.Completed,
                content: contents
            )
        ];

        return ToResponse(request, context, output: outputs);
    }

    public async IAsyncEnumerable<ResponseStreamEvent> InvokeStreamAsync(CreateResponseRequest request,
        AgentInvocationContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var activity = Activity.Current;
        activity?.SetTag("gen_ai.conversation.id", context.ConversationId);


        var seq = -1;

        yield return new ResponseCreatedEvent(++seq,
            ToResponse(request, context, status: ResponseStatus.InProgress));

        var itemId = context.IdGenerator.GenerateMessageId();
        yield return new ResponseOutputItemAddedEvent(++seq, 0,
            item: new ResponsesAssistantMessageItemResource(
                id: itemId,
                status: ResponsesMessageItemResourceStatus.InProgress,
                content: []
            )
        );

        yield return new ResponseContentPartAddedEvent(++seq, itemId, 0, 0,
            new ItemContentOutputText(text: "", annotations: [])
        );

        var inputText = GetInputText(request);

        var responseText = await RunAgentLoopAsync(inputText, context.ConversationId, cancellationToken).ConfigureAwait(false);

        foreach (var part in responseText.Split(" "))
        {
            await Task.Delay(20, cancellationToken).ConfigureAwait(false);
            yield return new ResponseTextDeltaEvent(++seq, itemId, 0, 0, part + " ");
        }

        yield return new ResponseTextDoneEvent(++seq, itemId, 0, 0, responseText);

        var content = new ItemContentOutputText(text: responseText, annotations: []);
        yield return new ResponseContentPartDoneEvent(++seq, itemId, 0, 0, content);

        var item = new ResponsesAssistantMessageItemResource(id: itemId, ResponsesMessageItemResourceStatus.Completed,
            content: [content]);
        yield return new ResponseOutputItemDoneEvent(++seq, 0, item);

        yield return new ResponseCompletedEvent(++seq,
            ToResponse(request, context, status: ResponseStatus.Completed, output: [item]));
    }

    private static async Task<string> RunAgentLoopAsync(string userInput, string conversationId, CancellationToken cancellationToken)
    {
        var maxTurns = GetIntEnv("AGENT_MAX_TURNS", 10);

        // Build initial inputs in OpenAI Responses input format.
        var inputs = new List<OpenAI.Responses.ResponseItem>
        {
            OpenAI.Responses.ResponseItem.CreateSystemMessageItem(SystemPrompt),
            OpenAI.Responses.ResponseItem.CreateUserMessageItem(userInput)
        };

        // This check conversation existence will always return false, before Azure.AI.Projects supports conversation client.
        var conversationExists = false;
        if (!string.IsNullOrWhiteSpace(conversationId))
        {
            var conversationClient = GetOrCreateApiClient().GetConversationClient();
            try
            {
                var conversation = await conversationClient.GetConversationAsync(conversationId);
                conversationExists = conversation is not null;
            }
            catch (Exception ex)
            {
                conversationExists = false;
            }
        }

        var totalInputTokens = 0;
        var totalOutputTokens = 0;
        for (var turn = 0; turn < maxTurns; turn++)
        {
            using var iter = ActivitySource.StartActivity("SystemUtilityAgent.agent_run_iteration", ActivityKind.Internal);

            iter?.SetTag("current_iteration", turn);

            var response = await CallAzureOpenAIResponsesAsync(inputs, conversationExists ? conversationId : null, cancellationToken).ConfigureAwait(false);

            var usage = response.Usage;
            if (usage is not null)
            {
                totalInputTokens += usage?.InputTokenCount ?? 0;
                totalOutputTokens += usage?.OutputTokenCount ?? 0;
                iter?.SetTag("gen_ai.usage.input_tokens", usage?.InputTokenCount ?? 0);
                iter?.SetTag("gen_ai.usage.output_tokens", usage?.OutputTokenCount ?? 0);
            }

            var calledAny = false;
            var assistantTextChunks = new List<string>();
            foreach (var outputItem in response.OutputItems)
            {
                inputs.Add(outputItem);
                if (outputItem is OpenAI.Responses.FunctionCallResponseItem)
                {
                    using var functionCalActivity = ActivitySource.StartActivity("SystemUtilityAgent.tool_call_execution", ActivityKind.Internal);
                    var functionResponse = outputItem as OpenAI.Responses.FunctionCallResponseItem;
                    var functionName = functionResponse.FunctionName;
                    var arguments = ParseArguments(functionResponse.FunctionArguments);
                    var functionResult = InvokeTool(functionName, arguments, cancellationToken);
                    calledAny = true;
                    inputs.Add(OpenAI.Responses.ResponseItem.CreateFunctionCallOutputItem(
                        functionResponse.CallId,
                        JsonSerializer.Serialize(functionResult, JsonOptions)));
                    functionCalActivity?.SetTag("gen_ai.tool.name", functionName);
                    functionCalActivity?.SetTag("gen_ai.tool.type", "function");
                    functionCalActivity?.SetTag("gen_ai.tool.call.arguments", Truncate(functionResponse.FunctionArguments?.ToString() ?? "", 1024));
                    functionCalActivity?.SetTag("gen_ai.tool.call.result", JsonSerializer.Serialize(functionResult, JsonOptions));
                }
                else if (outputItem is OpenAI.Responses.MessageResponseItem)
                {
                    var messageResponse = outputItem as OpenAI.Responses.MessageResponseItem;
                    foreach (var c in messageResponse.Content)
                    {
                        assistantTextChunks.Add(c.Text);
                    }
                }

                if (conversationExists)
                {
                    inputs.Clear();
                }
            }
            if (!calledAny)
            {
                var finalText = string.Join("", assistantTextChunks).Trim();
                return string.IsNullOrWhiteSpace(finalText)
                    ? "(No assistant text returned.)"
                    : finalText;
            }
        }

        var activity = Activity.Current;
        activity?.SetTag("gen_ai.usage.input_tokens", totalInputTokens);
        activity?.SetTag("gen_ai.usage.output_tokens", totalOutputTokens);
        return $"I hit the {maxTurns} max turn limit for this request. Try rephrasing.";
    }

    private static async Task<OpenAI.Responses.ResponseResult> CallAzureOpenAIResponsesAsync(
        List<OpenAI.Responses.ResponseItem> inputs,
        string? conversationId,
        CancellationToken cancellationToken)
    {
        var activity = Activity.Current;

        var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")?? "gpt-5";
        var chatHistoryLength = GetIntEnv("AGENT_CHAT_HISTORY_LENGTH", 20);

        activity?.SetTag("gen_ai.request.model", deploymentName);

        var apiClient = GetOrCreateApiClient();

        var createResponseOptions = new OpenAI.Responses.CreateResponseOptions
        {
            StreamingEnabled = false
        };

        if (!string.IsNullOrWhiteSpace(conversationId))
        {
            createResponseOptions.ConversationOptions = new OpenAI.Responses.ResponseConversationOptions(conversationId);
        }

        foreach (var item in inputs.TakeLast(chatHistoryLength))
        {
            createResponseOptions.InputItems.Add(item);
        }

        var tools = ToolDefinitions();
        foreach (var tool in tools)
        {
            createResponseOptions.Tools.Add(tool);
        }

        var responseClient = apiClient.GetResponsesClient(deploymentName);
        activity.SetTag("gen_ai.input.messages", JsonSerializer.Serialize(createResponseOptions.InputItems));
        var response = await responseClient
            .CreateResponseAsync(createResponseOptions)
            .ConfigureAwait(false);

        return response;
    }

    private static OpenAIFunctionTool ToolDef(string name, string description, object parameters)
    {
        return OpenAIFunctionTool.CreateFunctionTool(
            name,
            BinaryData.FromObjectAsJson(parameters),
            false,
            description);
    }

    private static OpenAIFunctionTool[] ToolDefinitions()
    {
        return
        [
            ToolDef("capability_report", "Report what the agent can likely observe (host vs container scope).", new { type = "object", properties = new { }, required = Array.Empty<string>() }),
            ToolDef("system_info", "Return OS/runtime metadata.", new { type = "object", properties = new { }, required = Array.Empty<string>() }),
            ToolDef("resource_snapshot", "Return process + GC + disk snapshot.", new { type = "object", properties = new { }, required = Array.Empty<string>() }),
            ToolDef("list_processes", "List running processes (best-effort).", new { type = "object", properties = new { }, required = Array.Empty<string>() }),
            ToolDef("process_details", "Get details for a PID.", new { type = "object", properties = new { pid = new { type = "integer" } }, required = new[] { "pid" } }),
            ToolDef("check_port", "Check whether a TCP port is reachable.", new { type = "object", properties = new { host = new { type = "string" }, port = new { type = "integer" } }, required = new[] { "host", "port" } }),
            ToolDef("dns_lookup", "Resolve a hostname.", new { type = "object", properties = new { host = new { type = "string" } }, required = new[] { "host" } }),
            ToolDef("list_environment_variables", "List environment variables. Supports redaction.", new { type = "object", properties = new { redact = new { type = "boolean" } }, required = Array.Empty<string>() })
        ];
    }

    private static Dictionary<string, JsonElement> ParseArguments(BinaryData? data)
    {
        if (data is null)
        {
            return new Dictionary<string, JsonElement>(StringComparer.OrdinalIgnoreCase);
        }

        using var doc = JsonDocument.Parse(data.ToString());
        if (doc.RootElement.ValueKind != JsonValueKind.Object)
        {
            return new Dictionary<string, JsonElement>(StringComparer.OrdinalIgnoreCase);
        }

        return doc.RootElement.EnumerateObject()
            .ToDictionary(p => p.Name, p => p.Value.Clone(), StringComparer.OrdinalIgnoreCase);
    }

    private static object InvokeTool(string name, Dictionary<string, JsonElement> args, CancellationToken cancellationToken)
    {
        return name switch
        {
            "capability_report" => new { supported = true, reason = (string?)null, data = CapabilityReport() },
            "system_info" => new { supported = true, reason = (string?)null, data = SystemInfo() },
            "resource_snapshot" => new { supported = true, reason = (string?)null, data = ResourceSnapshot() },
            "list_processes" => new { supported = true, reason = (string?)null, data = ListProcesses() },
            "process_details" => ProcessDetailsTool(args),
            "check_port" => CheckPortTool(args, cancellationToken),
            "dns_lookup" => DnsLookupTool(args),
            "list_environment_variables" => ListEnvTool(args),
            _ => new { supported = false, reason = $"Unknown tool: {name}", data = (object?)null }
        };
    }

    private static object ProcessDetailsTool(Dictionary<string, JsonElement> args)
    {
        if (!args.TryGetValue("pid", out var pidEl) || !pidEl.TryGetInt32(out var pid) || pid <= 0)
        {
            return new { supported = false, reason = "Missing/invalid 'pid'", data = (object?)null };
        }

        try
        {
            return new { supported = true, reason = (string?)null, data = ProcessDetails(pid) };
        }
        catch (Exception ex)
        {
            return new { supported = false, reason = $"{ex.GetType().Name}: {ex.Message}", data = (object?)null };
        }
    }

    private static object CheckPortTool(Dictionary<string, JsonElement> args, CancellationToken cancellationToken)
    {
        var host = args.TryGetValue("host", out var hostEl) ? hostEl.GetString() : null;
        var port = 0;
        var portOk = args.TryGetValue("port", out var portEl) && portEl.TryGetInt32(out port);
        if (string.IsNullOrWhiteSpace(host) || !portOk || port <= 0 || port > 65535)
        {
            return new { supported = false, reason = "Missing/invalid 'host' or 'port'", data = (object?)null };
        }

        return new { supported = true, reason = (string?)null, data = CheckPort(host!, port, cancellationToken) };
    }

    private static object DnsLookupTool(Dictionary<string, JsonElement> args)
    {
        var host = args.TryGetValue("host", out var hostEl) ? hostEl.GetString() : null;
        if (string.IsNullOrWhiteSpace(host))
        {
            return new { supported = false, reason = "Missing/invalid 'host'", data = (object?)null };
        }

        return new { supported = true, reason = (string?)null, data = DnsLookup(host!) };
    }

    private static object ListEnvTool(Dictionary<string, JsonElement> args)
    {
        var redact = true;
        if (args.TryGetValue("redact", out var r) && r.ValueKind is JsonValueKind.True or JsonValueKind.False)
        {
            redact = r.GetBoolean();
        }

        return new { supported = true, reason = (string?)null, data = ListEnvironmentVariables(redact) };
    }

    private static int GetIntEnv(string name, int fallback)
        => int.TryParse(Environment.GetEnvironmentVariable(name), out var v) ? v : fallback;

    private static object CapabilityReport()
    {
        var os = RuntimeInformation.OSDescription;
        var isLinux = RuntimeInformation.IsOSPlatform(OSPlatform.Linux);

        var inContainer = isLinux && (File.Exists("/.dockerenv") || CGroupLooksContainerized());
        var scope = inContainer ? "container" : "host";

        return new
        {
            supported = true,
            scope,
            data = new
            {
                os,
                framework = RuntimeInformation.FrameworkDescription,
                in_container = inContainer,
                process_visibility = new
                {
                    supported = true,
                    scope,
                    notes = "In containers, you usually only see container processes (PID namespace)."
                },
                network_visibility = new
                {
                    supported = true,
                    scope,
                    notes = "In containers, ports reflect the container network namespace unless using host networking."
                }
            }
        };
    }

    private static bool CGroupLooksContainerized()
    {
        try
        {
            var path = "/proc/1/cgroup";
            if (!File.Exists(path)) return false;
            var txt = File.ReadAllText(path);
            return txt.Contains("docker", StringComparison.OrdinalIgnoreCase)
                   || txt.Contains("containerd", StringComparison.OrdinalIgnoreCase)
                   || txt.Contains("kubepods", StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static object SystemInfo()
    {
        return new
        {
            os = RuntimeInformation.OSDescription,
            framework = RuntimeInformation.FrameworkDescription,
            process_arch = RuntimeInformation.ProcessArchitecture.ToString(),
            machine_name = Environment.MachineName,
            user = Environment.UserName,
            uptime = Environment.TickCount64 / 1000.0,
            processors = Environment.ProcessorCount
        };
    }

    private static object ResourceSnapshot()
    {
        var proc = Process.GetCurrentProcess();
        var memInfo = GC.GetGCMemoryInfo();

        var drives = DriveInfo.GetDrives()
            .Where(d => d.IsReady)
            .Select(d => new
            {
                name = d.Name,
                format = d.DriveFormat,
                total_bytes = d.TotalSize,
                free_bytes = d.TotalFreeSpace
            })
            .ToList();

        return new
        {
            process = new
            {
                pid = proc.Id,
                working_set_bytes = proc.WorkingSet64,
                private_memory_bytes = proc.PrivateMemorySize64,
                threads = proc.Threads.Count
            },
            gc = new
            {
                heap_size_bytes = GC.GetTotalMemory(forceFullCollection: false),
                total_available_memory_bytes = memInfo.TotalAvailableMemoryBytes,
                high_memory_load_threshold_bytes = memInfo.HighMemoryLoadThresholdBytes,
                memory_load_bytes = memInfo.MemoryLoadBytes
            },
            disks = drives
        };
    }

    private static object ListProcesses()
    {
        var processes = Process.GetProcesses()
            .OrderBy(p => p.ProcessName)
            .Take(200)
            .Select(p => new
            {
                pid = p.Id,
                name = p.ProcessName
            })
            .ToList();

        return new
        {
            count = processes.Count,
            sample = processes,
            notes = "Process visibility can be limited in containers."
        };
    }

    private static object ProcessDetails(int pid)
    {
        if (pid <= 0) throw new ArgumentException("Provide a PID (e.g., 'process_details 1234').");
        var p = Process.GetProcessById(pid);

        DateTimeOffset? start = null;
        try { start = p.StartTime; } catch { }

        return new
        {
            pid = p.Id,
            name = p.ProcessName,
            start_time = start,
            working_set_bytes = Safe(() => p.WorkingSet64),
            private_memory_bytes = Safe(() => p.PrivateMemorySize64),
            total_processor_time = Safe(() => p.TotalProcessorTime)
        };
    }

    private static object CheckPort(string host, int port, CancellationToken cancellationToken)
    {
        if (port <= 0 || port > 65535) throw new ArgumentException("Provide a TCP port between 1 and 65535.");

        using var client = new TcpClient();
        var connectTask = client.ConnectAsync(host, port, cancellationToken);

        try
        {
            connectTask.GetAwaiter().GetResult();
            return new { host, port, reachable = true };
        }
        catch (Exception ex)
        {
            return new { host, port, reachable = false, reason = $"{ex.GetType().Name}: {ex.Message}" };
        }
    }

    private static object DnsLookup(string host)
    {
        if (string.IsNullOrWhiteSpace(host)) throw new ArgumentException("Provide a hostname.");
        var addrs = Dns.GetHostAddresses(host);
        return new
        {
            host,
            addresses = addrs.Select(a => a.ToString()).ToArray()
        };
    }

    private static object ListEnvironmentVariables(bool redact)
    {
        var vars = Environment.GetEnvironmentVariables();
        var dict = new SortedDictionary<string, string?>(StringComparer.OrdinalIgnoreCase);

        foreach (var keyObj in vars.Keys)
        {
            var key = keyObj?.ToString() ?? "";
            if (string.IsNullOrWhiteSpace(key))
            {
                continue;
            }
            var val = Environment.GetEnvironmentVariable(key);
            dict[key] = redact ? RedactIfSensitive(key, val) : val;
        }

        return new
        {
            redact,
            count = dict.Count,
            variables = dict
        };
    }

    private static string? RedactIfSensitive(string key, string? val)
    {
        if (val is null) return null;
        var upper = key.ToUpperInvariant();
        var sensitive = upper.Contains("KEY")
                        || upper.Contains("SECRET")
                        || upper.Contains("TOKEN")
                        || upper.Contains("PASSWORD")
                        || upper.Contains("CONNECTION")
                        || upper.Contains("SAS");

        return sensitive ? "***REDACTED***" : val;
    }

    private static T? Safe<T>(Func<T> f)
    {
        try { return f(); } catch { return default; }
    }

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..max];

    private static string GetInputText(CreateResponseRequest request)
    {
        var items = request.Input.ToObject<IList<ItemParam>>();
        if (items is { Count: > 0 })
        {
            return items.Select(item =>
                {
                    return item switch
                    {
                        ResponsesUserMessageItemParam userMessage => userMessage.Content
                            .ToObject<IList<ItemContentInputText>>()?
                            .FirstOrDefault()?
                            .Text ?? "",
                        _ => ""
                    };
                })
                .FirstOrDefault() ?? "";
        }

        // implicit user message of text input
        return request.Input.ToString();
    }

    private static Response ToResponse(CreateResponseRequest request, AgentInvocationContext context,
        ResponseStatus status = ResponseStatus.Completed,
        IEnumerable<ItemResource>? output = null)
    {
        return request.ToResponse(context: context, output: output, status: status);
    }

    private static string ToAzureOpenAIEndpoint(string projectEndpoint)
    {
        if (string.IsNullOrWhiteSpace(projectEndpoint))
            throw new ArgumentException("URL cannot be null or empty.", nameof(projectEndpoint));

        var uri = new Uri(projectEndpoint);

        // Expect something like: {resource}.services.ai.azure.com
        var hostParts = uri.Host.Split('.');
        if (hostParts.Length < 5 || hostParts[1] != "services" || hostParts[2] != "ai")
            throw new ArgumentException("Input URL is not a valid Azure AI Services URL.", nameof(projectEndpoint));

        var resourceName = hostParts[0];

        return $"https://{resourceName}.openai.azure.com/openai/v1/";
    }

}
