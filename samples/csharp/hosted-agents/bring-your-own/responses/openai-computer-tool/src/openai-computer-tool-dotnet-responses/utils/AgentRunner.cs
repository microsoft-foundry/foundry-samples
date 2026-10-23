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
        ProjectResponsesClient responsesClient =
            projectClient.ProjectOpenAIClient.GetProjectResponsesClientForModel(model);

        List<string> turnLogs = [];
        Console.WriteLine($"[HostedAgent] Model={model} | OutputFile={outputFile}");

        // Send initial screenshot + prompt so the model immediately sees the 1280x800 Virtual Paint Desktop
        string initialScreenshotB64 = desktop.TakeScreenshotBase64();
        JsonNode currentInput = new JsonArray
        {
            new JsonObject
            {
                ["role"] = "user",
                ["content"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["type"] = "input_text",
                        ["text"] = taskPrompt,
                    },
                    new JsonObject
                    {
                        ["type"] = "input_image",
                        ["image_url"] = $"data:image/png;base64,{initialScreenshotB64}",
                        ["detail"] = "original",
                    },
                },
            },
        };

        string? previousResponseId = null;
        string finalAssistantText = string.Empty;

        for (int turn = 1; turn <= maxTurns; turn++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            JsonObject payload = new()
            {
                ["model"] = model,
                ["instructions"] = systemPrompt,
                ["tools"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["type"] = "computer",
                    },
                },
                ["input"] = currentInput.DeepClone(),
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
            using JsonDocument responseDoc = JsonDocument.Parse(rawResponse.Content.ToMemory());
            JsonElement root = responseDoc.RootElement;

            previousResponseId = root.TryGetProperty("id", out JsonElement idProp)
                ? idProp.GetString()
                : null;

            List<(string CallId, List<JsonElement> Actions, List<JsonElement> PendingSafetyChecks)> computerCalls = [];
            List<string> assistantTexts = [];

            if (root.TryGetProperty("output", out JsonElement outputArray) &&
                outputArray.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement item in outputArray.EnumerateArray())
                {
                    string itemType = item.TryGetProperty("type", out JsonElement tProp)
                        ? tProp.GetString() ?? string.Empty
                        : string.Empty;

                    if (itemType == "computer_call")
                    {
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
                    else if (itemType == "message" &&
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
            }

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

                JsonObject callOutput = new()
                {
                    ["type"] = "computer_call_output",
                    ["call_id"] = callId,
                    ["output"] = new JsonObject
                    {
                        ["type"] = "computer_screenshot",
                        ["image_url"] = $"data:image/png;base64,{screenshotB64}",
                        ["detail"] = "original",
                    },
                };

                if (safetyChecks.Count > 0)
                {
                    JsonArray ackChecks = [];
                    foreach (JsonElement sc in safetyChecks)
                    {
                        ackChecks.Add(new JsonObject
                        {
                            ["id"] = sc.TryGetProperty("id", out JsonElement scId) ? scId.GetString() : string.Empty,
                            ["code"] = sc.TryGetProperty("code", out JsonElement scCode) ? scCode.GetString() : string.Empty,
                            ["message"] = sc.TryGetProperty("message", out JsonElement scMsg) ? scMsg.GetString() : string.Empty,
                        });
                    }

                    callOutput["acknowledged_safety_checks"] = ackChecks;
                }

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
