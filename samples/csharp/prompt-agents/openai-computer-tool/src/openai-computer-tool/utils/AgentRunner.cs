// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using System.ClientModel;
using System.Text.Json;
using System.Text.Json.Nodes;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using OpenAI.Files;

namespace OpenAIComputerTool.Utils;

/// <summary>
/// Shared multi-turn execution loop for the Azure AI Foundry Prompt Agent + OpenAI Computer Tool.
/// Invokes the provisioned Prompt Agent with a user prompt, dispatches each action in
/// <c>computer_call.actions</c> to the local desktop automation helper, and returns a desktop
/// screenshot in <c>computer_call_output</c> until the task completes.
/// </summary>
public static class AgentRunner
{
    public static async Task<string> RunCuaLoopAsync(
        string prompt,
        Action<JsonElement> handleAction,
        Func<string> takeScreenshot,
        string? agentName = null,
        int maxTurns = 10)
    {
        string resolvedAgentName = agentName ?? Settings.AgentName;
        string model = Settings.GetModelDeploymentName();
        List<string> uploadedFileIds = [];

        Console.WriteLine($"Invoking Prompt Agent '{resolvedAgentName}' (model={model})");
        Console.WriteLine($"User Prompt: {prompt}\n");

        AIProjectClient projectClient = Settings.GetProjectClient();
        ProjectOpenAIClient openAIClient = projectClient.ProjectOpenAIClient;
        ProjectResponsesClient responsesClient = openAIClient.GetProjectResponsesClientForAgent(resolvedAgentName);
        OpenAIFileClient fileClient = openAIClient.GetOpenAIFileClient();

        try
        {
            JsonObject initialPayload = new()
            {
                ["input"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["type"] = "message",
                        ["role"] = "user",
                        ["content"] = prompt,
                    },
                },
                ["agent_reference"] = new JsonObject
                {
                    ["type"] = "agent_reference",
                    ["name"] = resolvedAgentName,
                },
            };

            using JsonDocument initialResponseDoc = await SendResponseRequestAsync(responsesClient, initialPayload);
            JsonElement responseRoot = initialResponseDoc.RootElement.Clone();

            for (int turn = 1; turn <= maxTurns; turn++)
            {
                List<JsonElement> computerCalls = GetComputerCalls(responseRoot);
                if (computerCalls.Count == 0)
                {
                    string finalText = ExtractOutputText(responseRoot);
                    Console.WriteLine($"\nAgent Final Response:\n{finalText}");
                    return finalText;
                }

                JsonElement call = computerCalls[0];
                EnsureNoPendingSafetyChecks(call);

                string callId = call.GetProperty("call_id").GetString()
                    ?? throw new InvalidOperationException("computer_call item is missing call_id.");
                List<JsonElement> actions = GetActions(call);

                Console.WriteLine($"[Turn {turn}] Executing {actions.Count} action(s) (call_id={callId}):");

                foreach (JsonElement action in actions)
                {
                    Console.WriteLine($"  -> {action.GetRawText()}");
                    handleAction(action);

                    string actionType = action.TryGetProperty("type", out JsonElement typeProp)
                        ? typeProp.GetString() ?? string.Empty
                        : string.Empty;
                    if (!string.Equals(actionType, "screenshot", StringComparison.OrdinalIgnoreCase))
                    {
                        Thread.Sleep(350);
                    }
                }

                JsonObject screenshotOutput = await BuildScreenshotOutputAsync(
                    fileClient,
                    takeScreenshot(),
                    uploadedFileIds);

                string previousResponseId = responseRoot.GetProperty("id").GetString()
                    ?? throw new InvalidOperationException("Response is missing id.");

                JsonObject followUpPayload = new()
                {
                    ["previous_response_id"] = previousResponseId,
                    ["input"] = new JsonArray
                    {
                        new JsonObject
                        {
                            ["type"] = "computer_call_output",
                            ["call_id"] = callId,
                            ["output"] = screenshotOutput,
                        },
                    },
                    ["agent_reference"] = new JsonObject
                    {
                        ["type"] = "agent_reference",
                        ["name"] = resolvedAgentName,
                    },
                };

                using JsonDocument nextResponseDoc = await SendResponseRequestAsync(responsesClient, followUpPayload);
                responseRoot = nextResponseDoc.RootElement.Clone();
            }

            if (GetComputerCalls(responseRoot).Count > 0)
            {
                throw new InvalidOperationException(
                    $"Reached maxTurns={maxTurns} with pending computer_call actions still remaining.");
            }

            string outputText = ExtractOutputText(responseRoot);
            Console.WriteLine($"\nAgent Final Response:\n{outputText}");
            return outputText;
        }
        finally
        {
            await CleanupUploadedFilesAsync(fileClient, uploadedFileIds);
        }
    }

    private static async Task<JsonDocument> SendResponseRequestAsync(
        ProjectResponsesClient responsesClient,
        JsonObject payload)
    {
        using BinaryContent content = BinaryContent.Create(BinaryData.FromString(payload.ToJsonString()));
        ClientResult result = await responsesClient.CreateResponseAsync(content);
        BinaryData responseBytes = result.GetRawResponse().Content;
        return JsonDocument.Parse(responseBytes);
    }

    private static async Task<JsonObject> BuildScreenshotOutputAsync(
        OpenAIFileClient fileClient,
        string screenshotBase64,
        List<string> uploadedFileIds)
    {
        if (screenshotBase64.Length <= 64_000)
        {
            return new JsonObject
            {
                ["type"] = "computer_screenshot",
                ["image_url"] = $"data:image/png;base64,{screenshotBase64}",
            };
        }

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

    private static List<JsonElement> GetComputerCalls(JsonElement responseRoot)
    {
        List<JsonElement> calls = [];
        if (!responseRoot.TryGetProperty("output", out JsonElement outputArray) ||
            outputArray.ValueKind != JsonValueKind.Array)
        {
            return calls;
        }

        foreach (JsonElement item in outputArray.EnumerateArray())
        {
            if (item.TryGetProperty("type", out JsonElement typeProp) &&
                string.Equals(typeProp.GetString(), "computer_call", StringComparison.Ordinal))
            {
                calls.Add(item);
            }
        }

        return calls;
    }

    private static List<JsonElement> GetActions(JsonElement computerCall)
    {
        List<JsonElement> actions = [];
        if (computerCall.TryGetProperty("actions", out JsonElement actionsProp) &&
            actionsProp.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement action in actionsProp.EnumerateArray())
            {
                actions.Add(action);
            }
        }
        else if (computerCall.TryGetProperty("action", out JsonElement singleAction) &&
                 singleAction.ValueKind == JsonValueKind.Object)
        {
            actions.Add(singleAction);
        }

        return actions;
    }

    private static void EnsureNoPendingSafetyChecks(JsonElement computerCall)
    {
        if (!computerCall.TryGetProperty("pending_safety_checks", out JsonElement checksProp) ||
            checksProp.ValueKind != JsonValueKind.Array ||
            checksProp.GetArrayLength() == 0)
        {
            return;
        }

        List<string> descriptions = [];
        foreach (JsonElement check in checksProp.EnumerateArray())
        {
            string code = check.TryGetProperty("code", out JsonElement codeProp) ? codeProp.GetString() ?? "unknown" : "unknown";
            string message = check.TryGetProperty("message", out JsonElement msgProp) ? msgProp.GetString() ?? string.Empty : string.Empty;
            descriptions.Add($"{code}: {message}");
        }

        throw new InvalidOperationException(
            $"Refusing to execute computer_call with pending safety checks: {string.Join(", ", descriptions)}");
    }

    private static string ExtractOutputText(JsonElement responseRoot)
    {
        if (responseRoot.TryGetProperty("output_text", out JsonElement outputTextProp) &&
            outputTextProp.ValueKind == JsonValueKind.String)
        {
            return outputTextProp.GetString() ?? string.Empty;
        }

        List<string> segments = [];
        if (responseRoot.TryGetProperty("output", out JsonElement outputArray) &&
            outputArray.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in outputArray.EnumerateArray())
            {
                if (!item.TryGetProperty("content", out JsonElement contentArray) ||
                    contentArray.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foreach (JsonElement content in contentArray.EnumerateArray())
                {
                    if (content.TryGetProperty("text", out JsonElement textProp) &&
                        textProp.ValueKind == JsonValueKind.String)
                    {
                        segments.Add(textProp.GetString() ?? string.Empty);
                    }
                }
            }
        }

        return string.Join("\n", segments);
    }
}
