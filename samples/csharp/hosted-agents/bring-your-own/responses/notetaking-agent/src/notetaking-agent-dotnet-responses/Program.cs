// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Responses;

// Load environment variables from a .env file if present (for local development).
Env.NoClobber().TraversePath().Load();

if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING")))
    Console.Error.WriteLine(
        "[WARNING] APPLICATIONINSIGHTS_CONNECTION_STRING not set — traces will not be sent " +
        "to Application Insights. Set it to enable local telemetry. " +
        "(This variable is auto-injected in hosted Foundry containers — do not declare it in agent.manifest.yaml.)");

var foundryEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT environment variable is not set.");
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set.");

var projectClient = new AIProjectClient(new Uri(foundryEndpoint), new DefaultAzureCredential());

// Use the Responses API via the Foundry project client — replaces the legacy
// Azure.AI.OpenAI / AzureOpenAIClient pattern.
var responsesClient = projectClient.ProjectOpenAIClient
    .GetProjectResponsesClientForModel(deployment);

ResponsesServer.Run<NoteTakingHandler>(configure: builder =>
{
    builder.Services.AddSingleton(responsesClient);
});

// ──────────────────────────────────────────────────────────────────
// Handler
// ──────────────────────────────────────────────────────────────────

public class NoteTakingHandler : ResponseHandler
{
    // Maximum number of tool-call rounds before giving up. Bounds API cost and
    // request latency if the model gets stuck in a tool-call feedback loop.
    private const int MaxToolRounds = 5;

    private const string SystemPrompt =
        "You are a helpful note-taking assistant. You can save notes and retrieve them. " +
        "When the user asks to save a note, extract the note content and call save_note. " +
        "When the user asks to see their notes, call get_notes. " +
        "Always respond in a friendly, concise manner.";

    private static readonly OpenAI.Responses.FunctionTool s_saveNoteTool = ResponseTool.CreateFunctionTool(
        functionName: "save_note",
        functionDescription: "Save a note with the current timestamp. Use this when the user asks to save, add, or create a note.",
        functionParameters: BinaryData.FromString("""
        {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note text to save"
                }
            },
            "required": ["note"]
        }
        """),
        strictModeEnabled: false);

    private static readonly OpenAI.Responses.FunctionTool s_getNotesTool = ResponseTool.CreateFunctionTool(
        functionName: "get_notes",
        functionDescription: "Retrieve all saved notes. Use this when the user asks to get, list, show, or view their notes.",
        functionParameters: BinaryData.FromString("""
        {
            "type": "object",
            "properties": {},
            "required": []
        }
        """),
        strictModeEnabled: false);

    private readonly ProjectResponsesClient _responsesClient;

    public NoteTakingHandler(ProjectResponsesClient responsesClient) => _responsesClient = responsesClient;

    public override IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        CancellationToken cancellationToken)
    {
        return new TextResponse(context, request,
            createTextStream: ct => ProcessAsync(request, context, ct));
    }

    private async IAsyncEnumerable<string> ProcessAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var userMessage = await context.GetInputTextAsync(cancellationToken: cancellationToken) ?? "";
        // Hosted sessions may omit agent_session_id from the body; the platform
        // supplies the session ID through FOUNDRY_AGENT_SESSION_ID instead.
        var sessionId = FirstNonEmpty(
            request.AgentSessionId,
            Environment.GetEnvironmentVariable("FOUNDRY_AGENT_SESSION_ID"),
            "default");

        var options = new CreateResponseOptions { Instructions = SystemPrompt };
        options.Tools.Add(s_saveNoteTool);
        options.Tools.Add(s_getNotesTool);
        options.InputItems.Add(ResponseItem.CreateUserMessageItem(userMessage));

        // Function-call loop: keep asking the model until it returns a final
        // assistant message with no further function calls. Each round, append
        // the model's output items and any tool results to InputItems so the
        // next call has the full context.
        for (int round = 0; round < MaxToolRounds; round++)
        {
            var result = await _responsesClient.CreateResponseAsync(options, cancellationToken);
            bool functionCalled = false;

            foreach (var responseItem in result.Value.OutputItems)
            {
                options.InputItems.Add(responseItem);
                if (responseItem is FunctionCallResponseItem functionCall)
                {
                    var toolOutput = ExecuteToolCall(
                        functionCall.FunctionName,
                        functionCall.FunctionArguments,
                        sessionId);
                    options.InputItems.Add(
                        ResponseItem.CreateFunctionCallOutputItem(functionCall.CallId, toolOutput));
                    functionCalled = true;
                }
            }

            if (!functionCalled)
            {
                yield return result.Value.GetOutputText() ?? "";
                yield break;
            }
        }

        yield return $"(Tool-call loop exceeded {MaxToolRounds} rounds without producing a final response.)";
    }

    private static string FirstNonEmpty(params string?[] values) =>
        values.First(value => !string.IsNullOrWhiteSpace(value))!;

    private static string ExecuteToolCall(string functionName, BinaryData arguments, string sessionId)
    {
        try
        {
            if (functionName == "save_note")
            {
                var args = JsonSerializer.Deserialize<JsonElement>(arguments);
                if (!args.TryGetProperty("note", out var noteProp))
                    return JsonSerializer.Serialize(new { error = "Missing required 'note' argument" });

                var noteText = noteProp.GetString() ?? "";
                var entry = NoteStore.SaveNote(sessionId, noteText);
                return JsonSerializer.Serialize(new { status = "saved", note = entry.Note, timestamp = entry.Timestamp });
            }
            else if (functionName == "get_notes")
            {
                var notes = NoteStore.GetNotes(sessionId);
                return JsonSerializer.Serialize(new { count = notes.Count, notes = notes.Select(n => new { n.Note, n.Timestamp }) });
            }
            return JsonSerializer.Serialize(new { error = $"Unknown function: {functionName}" });
        }
        catch (JsonException ex)
        {
            return JsonSerializer.Serialize(new { error = $"Invalid tool arguments: {ex.Message}" });
        }
    }
}
