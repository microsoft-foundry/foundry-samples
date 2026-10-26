// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using OpenAI.Files;

namespace OpenAIComputerToolHostedAgent;

/// <summary>
/// Result of running the multi-turn GA OpenAI Computer Tool loop inside the Hosted Agent.
/// </summary>
public sealed record CuaLoopResult(string FinalText, string OutputFile, IReadOnlyList<string> TurnLogs);

/// <summary>
/// Runs the multi-turn GA OpenAI Computer Tool (<c>{"type": "computer"}</c>) loop
/// against the Microsoft Foundry Responses API and executes every batched
/// <c>computer_call</c> action on the <see cref="VirtualPaintDesktop"/>.
/// </summary>
public static class AgentRunner
{
    public static async Task<CuaLoopResult> RunPaintSmileyLoopAsync(
        string? customPrompt = null,
        int maxTurns = 25,
        CancellationToken cancellationToken = default)
    {
        string endpoint = Settings.GetProjectEndpoint();
        string model = Settings.GetModelDeploymentName();
        string systemPrompt = Settings.GetSystemPrompt();

        string timestamp = DateTime.UtcNow.ToString("yyyyMMdd_HHmmss");
        string outputFile = Settings.GetWritableOutputPath($"paint_smiley_{timestamp}.png");
        VirtualPaintDesktop desktop = new(outputFile);

        string taskPrompt = string.IsNullOrWhiteSpace(customPrompt) ||
                            customPrompt.Contains("paint_smiley", StringComparison.OrdinalIgnoreCase)
            ? PaintSmileyScenario.BuildPaintPrompt(outputFile)
            : customPrompt;

        DefaultAzureCredential credential = new();
        AIProjectClient projectClient = new(new Uri(endpoint), credential);
        ProjectOpenAIClient openAIClient = projectClient.ProjectOpenAIClient;
        ProjectResponsesClient responsesClient = openAIClient.GetProjectResponsesClientForModel(model);
        OpenAIFileClient fileClient = openAIClient.GetOpenAIFileClient();

        List<string> turnLogs = [];
        List<string> uploadedFileIds = [];
        Console.WriteLine($"[HostedAgent] Model={model} | OutputFile={outputFile}");

        try
        {
            JsonNode currentInput = new JsonArray
            {
                new JsonObject
                {
                    ["role"] = "user",
                    ["content"] = taskPrompt,
                },
            };

            string? previousResponseId = null;
            string finalAssistantText = string.Empty;

            for (int turn = 1; turn <= maxTurns; turn++)
            {
                cancellationToken.ThrowIfCancellationRequested();

                using JsonDocument responseDoc = await SendResponseRequestAsync(
                    responsesClient,
                    model,
                    systemPrompt,
                    currentInput,
                    previousResponseId,
                    cancellationToken);
                JsonElement root = responseDoc.RootElement;

                previousResponseId = root.TryGetProperty("id", out JsonElement idProp)
                    ? idProp.GetString()
                    : null;

                List<(string CallId, List<JsonElement> Actions, List<JsonElement> PendingSafetyChecks)> computerCalls =
                    GetComputerCalls(root);
                List<string> assistantTexts = ExtractAssistantTexts(root);

                if (assistantTexts.Count > 0)
                {
                    finalAssistantText = string.Join("\n", assistantTexts);
                    Console.WriteLine($"[Turn {turn}] Agent: {finalAssistantText}");
                }

                if (computerCalls.Count == 0)
                {
                    desktop.SaveImage();
                    Console.WriteLine($"[Turn {turn}] Completed! Saved PNG: {outputFile}");
                    break;
                }

                JsonArray nextOutputs = [];

                foreach ((string callId, List<JsonElement> actions, List<JsonElement> safetyChecks) in computerCalls)
                {
                    EnsureNoPendingSafetyChecks(safetyChecks);

                    List<string> actionSummaries = [];
                    foreach (JsonElement action in actions)
                    {
                        string summary = FormatActionSummary(action);
                        actionSummaries.Add(summary);
                        Console.WriteLine($"[Turn {turn}]   -> {summary}");
                        desktop.HandleAction(action);
                    }

                    string turnSummary = $"[Turn {turn}] {string.Join(", ", actionSummaries)}";
                    turnLogs.Add(turnSummary);

                    string screenshotB64 = desktop.TakeScreenshotBase64();
                    JsonObject screenshotOutput = await BuildScreenshotOutputAsync(
                        fileClient,
                        screenshotB64,
                        uploadedFileIds);

                    JsonObject callOutput = new()
                    {
                        ["type"] = "computer_call_output",
                        ["call_id"] = callId,
                        ["output"] = screenshotOutput,
                    };

                    nextOutputs.Add(callOutput);
                }

                currentInput = nextOutputs;
            }

            if (!File.Exists(outputFile))
            {
                desktop.SaveImage();
            }

            if (string.IsNullOrWhiteSpace(finalAssistantText))
            {
                finalAssistantText = $"Completed drawing the yellow smiley face on the container Virtual Paint Desktop and saved to {outputFile}.";
            }

            return new CuaLoopResult(finalAssistantText, outputFile, turnLogs);
        }
        finally
        {
            await CleanupUploadedFilesAsync(fileClient, uploadedFileIds);
        }
    }

    private static async Task<JsonDocument> SendResponseRequestAsync(
        ProjectResponsesClient responsesClient,
        string model,
        string instructions,
        JsonNode input,
        string? previousResponseId,
        CancellationToken cancellationToken)
    {
        JsonObject payload = new()
        {
            ["model"] = model,
            ["instructions"] = instructions,
            ["tools"] = new JsonArray
            {
                new JsonObject
                {
                    ["type"] = "computer",
                },
            },
            ["input"] = input.DeepClone(),
        };

        if (!string.IsNullOrEmpty(previousResponseId))
        {
            payload["previous_response_id"] = previousResponseId;
        }

        using BinaryContent requestContent = BinaryContent.Create(
            BinaryData.FromString(payload.ToJsonString()));
        ClientResult rawResult = await Task.Run(
            () => responsesClient.CreateResponse(requestContent, (RequestOptions?)null),
            cancellationToken);

        PipelineResponse rawResponse = rawResult.GetRawResponse();
        return JsonDocument.Parse(rawResponse.Content.ToMemory());
    }

    private static async Task<JsonObject> BuildScreenshotOutputAsync(
        OpenAIFileClient fileClient,
        string screenshotBase64,
        List<string> uploadedFileIds)
    {
        if (screenshotBase64.Length <= 250_000)
        {
            return new JsonObject
            {
                ["type"] = "computer_screenshot",
                ["image_url"] = $"data:image/png;base64,{screenshotBase64}",
            };
        }

        try
        {
            byte[] pngBytes = Convert.FromBase64String(screenshotBase64);
            using MemoryStream stream = new(pngBytes);
            ClientResult<OpenAIFile> uploaded = await fileClient.UploadFileAsync(
                stream,
                "screenshot.png",
                FileUploadPurpose.Assistants);

            uploadedFileIds.Add(uploaded.Value.Id);
            return new JsonObject
            {
                ["type"] = "computer_screenshot",
                ["file_id"] = uploaded.Value.Id,
            };
        }
        catch (ClientResultException)
        {
            return new JsonObject
            {
                ["type"] = "computer_screenshot",
                ["image_url"] = $"data:image/png;base64,{screenshotBase64}",
            };
        }
    }

    private static async Task CleanupUploadedFilesAsync(
        OpenAIFileClient fileClient,
        List<string> uploadedFileIds)
    {
        foreach (string fileId in uploadedFileIds)
        {
            try
            {
                await fileClient.DeleteFileAsync(fileId);
            }
            catch
            {
                // Ignore best-effort cleanup errors.
            }
        }
    }

    private static List<(string CallId, List<JsonElement> Actions, List<JsonElement> PendingSafetyChecks)> GetComputerCalls(
        JsonElement root)
    {
        List<(string CallId, List<JsonElement> Actions, List<JsonElement> PendingSafetyChecks)> computerCalls = [];
        if (!root.TryGetProperty("output", out JsonElement outputArray) ||
            outputArray.ValueKind != JsonValueKind.Array)
        {
            return computerCalls;
        }

        foreach (JsonElement item in outputArray.EnumerateArray())
        {
            string itemType = item.TryGetProperty("type", out JsonElement tProp)
                ? tProp.GetString() ?? string.Empty
                : string.Empty;

            if (itemType != "computer_call")
            {
                continue;
            }

            string callId = item.GetProperty("call_id").GetString() ?? string.Empty;
            List<JsonElement> actions = [];

            if (item.TryGetProperty("actions", out JsonElement actionsProp) &&
                actionsProp.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement act in actionsProp.EnumerateArray())
                {
                    actions.Add(act.Clone());
                }
            }
            else if (item.TryGetProperty("action", out JsonElement singleActProp) &&
                     singleActProp.ValueKind == JsonValueKind.Object)
            {
                actions.Add(singleActProp.Clone());
            }

            List<JsonElement> safetyChecks = [];
            if (item.TryGetProperty("pending_safety_checks", out JsonElement safetyProp) &&
                safetyProp.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement sc in safetyProp.EnumerateArray())
                {
                    safetyChecks.Add(sc.Clone());
                }
            }

            computerCalls.Add((callId, actions, safetyChecks));
        }

        return computerCalls;
    }

    private static List<string> ExtractAssistantTexts(JsonElement root)
    {
        List<string> assistantTexts = [];
        if (!root.TryGetProperty("output", out JsonElement outputArray) ||
            outputArray.ValueKind != JsonValueKind.Array)
        {
            return assistantTexts;
        }

        foreach (JsonElement item in outputArray.EnumerateArray())
        {
            string itemType = item.TryGetProperty("type", out JsonElement tProp)
                ? tProp.GetString() ?? string.Empty
                : string.Empty;

            if (itemType == "message" &&
                item.TryGetProperty("content", out JsonElement contentArray) &&
                contentArray.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement part in contentArray.EnumerateArray())
                {
                    if (part.TryGetProperty("text", out JsonElement textProp))
                    {
                        string? text = textProp.GetString();
                        if (!string.IsNullOrWhiteSpace(text))
                        {
                            assistantTexts.Add(text);
                        }
                    }
                }
            }
        }

        return assistantTexts;
    }

    private static void EnsureNoPendingSafetyChecks(List<JsonElement> safetyChecks)
    {
        if (safetyChecks.Count == 0)
        {
            return;
        }

        List<string> descriptions = [];
        foreach (JsonElement sc in safetyChecks)
        {
            string code = sc.TryGetProperty("code", out JsonElement scCode) ? scCode.GetString() ?? "unknown" : "unknown";
            string message = sc.TryGetProperty("message", out JsonElement scMsg) ? scMsg.GetString() ?? string.Empty : string.Empty;
            descriptions.Add($"{code}: {message}");
        }

        throw new InvalidOperationException(
            $"Refusing to execute computer_call with pending safety checks: {string.Join(", ", descriptions)}");
    }

    private static string FormatActionSummary(JsonElement action)
    {
        string type = action.TryGetProperty("type", out JsonElement t) ? t.GetString() ?? "unknown" : "unknown";
        return type switch
        {
            "click" or "double_click" or "move" =>
                $"{type}({GetInt(action, "x")}, {GetInt(action, "y")})",
            "drag" => FormatDragSummary(action),
            "type" => $"type(\"{(action.TryGetProperty("text", out JsonElement txt) ? txt.GetString() : string.Empty)}\")",
            "keypress" => $"keypress({(action.TryGetProperty("keys", out JsonElement k) ? k.GetRawText() : "[]")})",
            _ => type,
        };
    }

    private static string FormatDragSummary(JsonElement action)
    {
        if (!action.TryGetProperty("path", out JsonElement pathProp) ||
            pathProp.ValueKind != JsonValueKind.Array ||
            pathProp.GetArrayLength() == 0)
        {
            return "drag([])";
        }

        StringBuilder sb = new("drag([");
        int idx = 0;
        foreach (JsonElement pt in pathProp.EnumerateArray())
        {
            if (idx > 0)
            {
                sb.Append(" -> ");
            }

            sb.Append($"({GetInt(pt, "x")},{GetInt(pt, "y")})");
            idx++;
        }

        sb.Append("])");
        return sb.ToString();
    }

    private static int GetInt(JsonElement el, string prop) =>
        el.TryGetProperty(prop, out JsonElement val) && val.ValueKind == JsonValueKind.Number
            ? val.GetInt32()
            : 0;
}
