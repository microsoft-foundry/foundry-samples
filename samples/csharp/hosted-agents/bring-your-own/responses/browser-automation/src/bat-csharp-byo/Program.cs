// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using OpenAI.Responses;

namespace BrowserAutomation;

public class Program
{
    public static void Main(string[] args)
    {
        Env.NoClobber().TraversePath().Load();

        var endpoint = Environment.GetEnvironmentVariable(
                "FOUNDRY_PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException(
                "FOUNDRY_PROJECT_ENDPOINT environment variable is not set.");
        var deployment = Environment.GetEnvironmentVariable(
                "AZURE_AI_MODEL_DEPLOYMENT_NAME")
            ?? throw new InvalidOperationException(
                "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set.");
        var toolboxName = Environment.GetEnvironmentVariable("TOOLBOX_NAME")
            ?? Constants.DefaultToolboxName;

        var credential = new DefaultAzureCredential();
        var responsesClient = new AIProjectClient(
                new Uri(endpoint),
                credential)
            .ProjectOpenAIClient
            .GetProjectResponsesClientForModel(deployment);

        ResponsesServer.Run<BrowserAutomationHandler>(configure: builder =>
        {
            builder.Services.AddSingleton(responsesClient);
            builder.Services.AddSingleton(new ToolboxConfig(
                $"{endpoint.TrimEnd('/')}/toolboxes/{toolboxName}/mcp?api-version=v1",
                credential));
        });
    }
}

public record ToolboxConfig(
    string Endpoint,
    DefaultAzureCredential Credential);

public sealed record BrowserSessionState(
    string BrowserSessionId,
    string? LiveViewUrl);

public class BrowserAutomationHandler : ResponseHandler
{
    private readonly ProjectResponsesClient _responsesClient;
    private readonly ILogger<BrowserAutomationHandler> _logger;
    private static readonly ConcurrentDictionary<string, BrowserSessionState>
        ActiveSessions = new();
    private static string? _lastSession;
    private static readonly SemaphoreSlim SessionGate = new(1, 1);
    private static ToolboxClient? _toolbox;
    private static readonly object ToolboxLock = new();

    public BrowserAutomationHandler(
        ProjectResponsesClient responsesClient,
        ToolboxConfig toolboxConfig,
        ILogger<BrowserAutomationHandler> logger)
    {
        _responsesClient = responsesClient;
        _logger = logger;
        lock (ToolboxLock)
        {
            _toolbox ??= new ToolboxClient(
                toolboxConfig.Endpoint,
                toolboxConfig.Credential,
                logger);
        }
    }

    public override IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        CancellationToken cancellationToken) =>
        new TextResponse(
            context,
            request,
            createTextStream: ct => ProcessAsync(
                request,
                context,
                ct));

    private async IAsyncEnumerable<string> ProcessAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var userInput = await context.GetInputTextAsync(
            cancellationToken: cancellationToken) ?? "";
        if (string.IsNullOrWhiteSpace(userInput))
        {
            yield return "No input provided.";
            yield break;
        }

        var verbose = userInput.TrimStart().StartsWith(
            "/verbose",
            StringComparison.OrdinalIgnoreCase);
        if (verbose)
            userInput = userInput.Replace(
                "/verbose",
                "",
                StringComparison.OrdinalIgnoreCase).TrimStart();

        var inputItems = new List<ResponseItem>();
        try
        {
            var history = await context.GetHistoryAsync(cancellationToken);
            foreach (var item in history.OfType<OutputItemMessage>())
            {
                foreach (var content in item.Content ?? [])
                {
                    if (content is MessageContentOutputTextContent
                        { Text: { } assistantText })
                        inputItems.Add(
                            ResponseItem.CreateAssistantMessageItem(
                                assistantText));
                    else if (content is MessageContentInputTextContent
                        { Text: { } userText })
                        inputItems.Add(
                            ResponseItem.CreateUserMessageItem(userText));
                }
            }
        }
        catch (Exception exception)
        {
            _logger.LogWarning(
                "get_history failed; continuing without: {Error}",
                exception.Message);
        }

        if (!ActiveSessions.IsEmpty)
        {
            inputItems.Add(ResponseItem.CreateUserMessageItem(
                "[Active sessions: "
                + JsonSerializer.Serialize(ActiveSessions.ToDictionary(
                    pair => pair.Key,
                    pair => pair.Value.BrowserSessionId))
                + $", default: {_lastSession}]"));
        }
        inputItems.Add(ResponseItem.CreateUserMessageItem(userInput));

        var instructions = Constants.GetSystemPrompt(Skills.ListSkills());
        var tools = await BuildToolsAsync(cancellationToken);
        var usedSessions = new HashSet<string>();
        string finalReply = "";

        for (var round = 0; round < 20; round++)
        {
            var options = new CreateResponseOptions
            {
                Instructions = instructions,
            };
            foreach (var tool in tools)
                options.Tools.Add(tool);
            foreach (var item in inputItems)
                options.InputItems.Add(item);

            var response = await _responsesClient.CreateResponseAsync(
                options,
                cancellationToken);
            var calls = response.Value.OutputItems
                .OfType<FunctionCallResponseItem>()
                .ToList();
            if (calls.Count == 0)
            {
                finalReply = response.Value.GetOutputText()
                    ?? "(No response)";
                break;
            }

            foreach (var call in calls)
            {
                var result = await HandleToolCallAsync(
                    call.FunctionName,
                    call.FunctionArguments,
                    usedSessions,
                    cancellationToken);
                if (result.LiveViewUrl is not null)
                {
                    yield return $"🔴 Created **{result.SessionName}**: "
                        + $"[Live View]({result.LiveViewUrl})\n";
                }
                if (verbose)
                    yield return $"🔧 `{call.FunctionName}`\n";

                inputItems.Add(ResponseItem.CreateFunctionCallItem(
                    call.CallId,
                    call.FunctionName,
                    call.FunctionArguments));
                inputItems.Add(ResponseItem.CreateFunctionCallOutputItem(
                    call.CallId,
                    result.IsError
                        ? $"Tool error: {result.Output}"
                        : result.Output));
            }
        }

        if (string.IsNullOrEmpty(finalReply))
            finalReply = "Tool-call limit reached before the task completed.";
        yield return finalReply;

        var links = ActiveSessions
            .Select(pair =>
                $"- **{pair.Key}**: "
                + (string.IsNullOrEmpty(pair.Value.LiveViewUrl)
                    ? "(no live view)"
                    : $"[Live View]({pair.Value.LiveViewUrl})"))
            .ToList();
        if (links.Count > 0)
        {
            yield return "\n\n---\n**Active Browser Sessions:**\n"
                + string.Join("\n", links);
            if (usedSessions.Count > 0)
                yield return "\n\n_Used Sessions in this response: "
                    + string.Join(", ", usedSessions.Order())
                    + "_";
        }
    }

    private async Task<ToolboxCallResult> HandleToolCallAsync(
        string functionName,
        BinaryData arguments,
        HashSet<string> usedSessions,
        CancellationToken cancellationToken)
    {
        try
        {
            _logger.LogInformation(
                "[tool] name={Name} arguments={Arguments}",
                functionName,
                Redaction.Redact(arguments.ToString()));

            if (functionName == "load_skill")
            {
                using var document = JsonDocument.Parse(arguments);
                var name = document.RootElement.GetProperty("name").GetString()
                    ?? "";
                var skill = Skills.LoadSkill(name);
                var output = skill is null
                    ? JsonSerializer.Serialize(new
                    {
                        error = $"Skill '{name}' not found.",
                    })
                    : JsonSerializer.Serialize(new
                    {
                        skill = name,
                        instructions = skill,
                    });
                return new ToolboxCallResult(
                    output,
                    null,
                    null,
                    skill is null);
            }

            await SessionGate.WaitAsync(cancellationToken);
            try
            {
                return await HandleBrowserToolAsync(
                    functionName,
                    arguments,
                    usedSessions,
                    cancellationToken);
            }
            finally
            {
                SessionGate.Release();
            }
        }
        catch (Exception exception)
        {
            _logger.LogError(
                exception,
                "Tool '{Name}' failed",
                functionName);
            return new ToolboxCallResult(
                $"Tool call failed: {exception.Message}",
                null,
                null,
                true);
        }
    }

    private static KeyValuePair<string, BrowserSessionState> ResolveSession(
        string? reference)
    {
        var name = string.IsNullOrEmpty(reference) ? _lastSession : reference;
        if (name is not null && ActiveSessions.TryGetValue(name, out var state))
            return new(name, state);
        foreach (var pair in ActiveSessions)
        {
            if (pair.Value.BrowserSessionId == name)
                return pair;
        }
        throw new InvalidOperationException(
            $"Session '{name}' not found. Available: "
            + string.Join(", ", ActiveSessions.Keys));
    }

    private static async Task<ToolboxTool> GetBrowserToolAsync(
        string shortName,
        CancellationToken cancellationToken) =>
        (await _toolbox!.ListToolsAsync(cancellationToken)).Single(tool =>
            tool.Name.Split("___").Last() == shortName);

    private static async Task<ToolboxCallResult> CreateSessionAsync(
        string? name,
        JsonObject arguments,
        CancellationToken cancellationToken,
        string? toolName = null)
    {
        if (name is null)
        {
            var number = 1;
            while (ActiveSessions.ContainsKey($"session-{number}"))
                number++;
            name = $"session-{number}";
        }
        if (string.IsNullOrWhiteSpace(name) || name == "all")
            throw new ArgumentException(
                "A non-empty session name other than 'all' is required.");
        if (ActiveSessions.TryGetValue(name, out var existing))
            return new ToolboxCallResult(
                JsonSerializer.Serialize(new
                {
                    status = "already_exists",
                    session = name,
                    browserSessionId = existing.BrowserSessionId,
                }),
                existing.BrowserSessionId,
                null,
                false,
                name);

        toolName ??= (await GetBrowserToolAsync(
            "create_browser_session", cancellationToken)).Name;
        var result = await _toolbox!.CallToolAsync(
            toolName,
            BinaryData.FromString(arguments.ToJsonString()),
            cancellationToken);
        if (result.IsError)
            return result;
        if (string.IsNullOrEmpty(result.BrowserSessionId))
            throw new InvalidOperationException(
                "Browser creation returned no browserSessionId.");

        ActiveSessions[name] = new BrowserSessionState(
            result.BrowserSessionId, result.LiveViewUrl);
        _lastSession = name;
        return result with
        {
            SessionName = name,
            Output = JsonSerializer.Serialize(new
            {
                status = "created",
                session = name,
                browserSessionId = result.BrowserSessionId,
                result = result.Output,
            }),
        };
    }

    private static async Task<ToolboxCallResult> CloseSessionAsync(
        string? reference,
        JsonObject arguments,
        CancellationToken cancellationToken,
        string? toolName = null)
    {
        var session = ResolveSession(reference);
        var tool = toolName is null
            ? await GetBrowserToolAsync("close_browser_session", cancellationToken)
            : (await _toolbox!.ListToolsAsync(cancellationToken))
                .Single(tool => tool.Name == toolName);
        var schema = JsonNode.Parse(tool.InputSchema.ToString())!.AsObject();
        var properties = schema["properties"]!.AsObject();
        var sessionParameter = properties.ContainsKey("browserSessionId")
            ? "browserSessionId"
            : "browser_session_id";
        arguments[sessionParameter] = session.Value.BrowserSessionId;
        var result = await _toolbox!.CallToolAsync(
            tool.Name,
            BinaryData.FromString(arguments.ToJsonString()),
            cancellationToken);
        if (!result.IsError)
        {
            ActiveSessions.TryRemove(session.Key, out _);
            if (_lastSession == session.Key)
                _lastSession = ActiveSessions.Keys.FirstOrDefault();
        }
        return result with { SessionName = session.Key };
    }

    private static async Task<ToolboxCallResult> HandleBrowserToolAsync(
        string functionName,
        BinaryData arguments,
        HashSet<string> usedSessions,
        CancellationToken cancellationToken)
    {
        var args = JsonNode.Parse(arguments.ToString())!.AsObject();
        if (functionName == "list_sessions")
            return new ToolboxCallResult(
                JsonSerializer.Serialize(new
                {
                    sessions = ActiveSessions.ToDictionary(
                        pair => pair.Key,
                        pair => new
                        {
                            browserSessionId = pair.Value.BrowserSessionId,
                            connected = true,
                        }),
                    @default = _lastSession,
                }), null, null, false);
        if (functionName == "create_session")
            return await CreateSessionAsync(
                args["name"]!.GetValue<string>(), new(), cancellationToken);
        if (functionName == "end_session")
        {
            var reference = args["name"]!.GetValue<string>();
            if (string.IsNullOrWhiteSpace(reference))
                throw new ArgumentException("A non-empty session name is required.");
            if (reference != "all")
                return await CloseSessionAsync(reference, new(), cancellationToken);
            var results = new Dictionary<string, string>();
            var isError = false;
            foreach (var name in ActiveSessions.Keys.ToList())
            {
                var result = await CloseSessionAsync(name, new(), cancellationToken);
                results[name] = result.Output;
                isError |= result.IsError;
            }
            return new ToolboxCallResult(
                JsonSerializer.Serialize(new
                {
                    status = isError ? "close_failed" : "ended_all",
                    results,
                    remaining = ActiveSessions.Keys.ToList(),
                }), null, null, isError);
        }

        var shortName = functionName.Split("___").Last();
        if (shortName == "create_browser_session")
            return await CreateSessionAsync(
                null, args, cancellationToken, functionName);
        var tool = (await _toolbox!.ListToolsAsync(cancellationToken))
            .Single(tool => tool.Name == functionName);
        var schema = JsonNode.Parse(tool.InputSchema.ToString())!.AsObject();
        var properties = schema["properties"] as JsonObject;
        var sessionParameter = properties?.ContainsKey("browserSessionId") == true
            ? "browserSessionId"
            : properties?.ContainsKey("browser_session_id") == true
                ? "browser_session_id"
                : null;
        if (sessionParameter is null)
            return await _toolbox.CallToolAsync(
                functionName, arguments, cancellationToken);

        var requestedSession = args[sessionParameter]?.GetValue<string>();
        ToolboxCallResult? created = null;
        if (string.IsNullOrEmpty(requestedSession)
            && ActiveSessions.IsEmpty
            && shortName != "close_browser_session")
        {
            created = await CreateSessionAsync("default", new(), cancellationToken);
            if (created.IsError)
                return created;
        }
        var session = ResolveSession(requestedSession);
        args[sessionParameter] = session.Value.BrowserSessionId;
        if (shortName == "close_browser_session")
            return await CloseSessionAsync(
                session.Key, args, cancellationToken, functionName);
        _lastSession = session.Key;
        usedSessions.Add(session.Key);
        var callResult = await _toolbox.CallToolAsync(
            functionName,
            BinaryData.FromString(args.ToJsonString()),
            cancellationToken);
        return callResult with
        {
            SessionName = session.Key,
            LiveViewUrl = created?.LiveViewUrl ?? callResult.LiveViewUrl,
        };
    }

    private async Task<List<ResponseTool>> BuildToolsAsync(
        CancellationToken cancellationToken)
    {
        var definitions = new List<JsonElement>();
        using (var localDocument = JsonDocument.Parse(
                   Constants.LoadSkillDefinition))
        {
            definitions.Add(localDocument.RootElement.Clone());
        }
        using (var sessionDocument = JsonDocument.Parse(
                   Constants.SessionToolDefinitions))
        {
            definitions.AddRange(sessionDocument.RootElement.EnumerateArray()
                .Select(definition => definition.Clone()));
        }

        var tools = new List<ResponseTool>();
        foreach (var local in definitions)
        {
            tools.Add(ResponseTool.CreateFunctionTool(
                functionName: local.GetProperty("name").GetString()!,
                functionDescription: local.GetProperty("description").GetString()!,
                functionParameters: BinaryData.FromString(
                    local.GetProperty("parameters").GetRawText()),
                strictModeEnabled: false));
        }

        foreach (var tool in await _toolbox!.ListToolsAsync(cancellationToken))
        {
            var schema = JsonNode.Parse(tool.InputSchema.ToString())!.AsObject();
            foreach (var key in new[] { "browserSessionId", "browser_session_id" })
            {
                if (schema["properties"]?[key] is not JsonObject property)
                    continue;
                property["description"] =
                    "Friendly session name or service browserSessionId. "
                    + "Omit to use the default browser session.";
                if (schema["required"] is JsonArray required)
                {
                    for (var index = required.Count - 1; index >= 0; index--)
                    {
                        if (required[index]?.GetValue<string>() == key)
                            required.RemoveAt(index);
                    }
                }
            }
            tools.Add(ResponseTool.CreateFunctionTool(
                functionName: tool.Name,
                functionDescription: tool.Description,
                functionParameters: BinaryData.FromString(schema.ToJsonString()),
                strictModeEnabled: false));
        }
        return tools;
    }
}
