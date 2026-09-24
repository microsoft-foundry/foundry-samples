// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample opens a short realtime voice agent session with conversation storage
// enabled, then inspects the resulting conversation through the Conversation REST API:
// fetching the conversation, listing/fetching its items and model responses. See
// realtime-text-and-tools and realtime-audio for streaming a live session without
// inspecting it afterward.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using OpenAI.Realtime;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Text.Json;

string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string modelName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_MODEL")?.Trim() ?? "gpt-realtime";
string agentName = GetOptionalEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME", $"voice-conversations-{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}");

AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());
AgentAdministrationClient agentsClient = projectClient.AgentAdministrationClient;
bool created = await EnsureVoiceAgentAsync();

try
{
    string conversationId = await RunStoredConversationAsync();
    BetaVoiceAgentsConversations conversationsClient = agentsClient.GetBetaVoiceAgentEndpointConversations();

    Console.WriteLine($"\nFetching conversation {conversationId}...");
    ClientResult<VoiceConversation> conversationResult =
        await conversationsClient.GetAgentConversationAsync(agentName, conversationId);
    VoiceConversation conversation = conversationResult;
    Console.WriteLine($"[REST] GET conversation -> {(int)conversationResult.GetRawResponse().Status}");
    Console.WriteLine(
        $"Status: {conversation.Status}, created: {conversation.CreatedOn:O}"
        + (conversation.CompletedOn is { } completedOn ? $", completed: {completedOn:O}" : string.Empty));

    Console.WriteLine("\nMost recent conversations for this agent:");
    int recentCount = 0;
    await foreach (VoiceConversation listed in conversationsClient.GetAgentConversationsAsync(agentName, limit: 5))
    {
        recentCount++;
        Console.WriteLine($"  - {listed.Id} ({listed.Status}){(listed.Id == conversationId ? "  <- ours" : string.Empty)}");
    }
    Console.WriteLine($"Listed {recentCount} conversation(s).");

    Console.WriteLine("\nConversation transcript (from GetAgentConversationItems):");
    List<RealtimeItem> items = new();
    await foreach (RealtimeItem item in conversationsClient.GetAgentConversationItemsAsync(agentName, conversationId))
    {
        items.Add(item);
        Console.WriteLine($"  {SummarizeItem(item)}");
    }

    if (items.Count > 0)
    {
        string firstItemId = GetItemId(items[0]);
        Console.WriteLine($"\nFetching item {firstItemId} directly...");
        ClientResult<RealtimeItem> fetchedItemResult =
            await conversationsClient.GetAgentConversationItemAsync(agentName, conversationId, firstItemId);
        Console.WriteLine($"[REST] GET conversation item -> {(int)fetchedItemResult.GetRawResponse().Status}");
        Console.WriteLine($"  {SummarizeItem(fetchedItemResult.Value)}");
    }

    Console.WriteLine("\nModel responses (from GetAgentConversationResponses):");
    List<VoiceResponse> responses = new();
    await foreach (VoiceResponse response in conversationsClient.GetAgentConversationResponsesAsync(agentName, conversationId))
    {
        responses.Add(response);
        Console.WriteLine($"  - {response.Id} ({response.Output.Count} output item(s))");
    }

    if (responses.Count > 0)
    {
        VoiceResponse firstResponse = responses[0];
        Console.WriteLine($"\nFetching response {firstResponse.Id} directly...");
        ClientResult<VoiceResponse> fetchedResponseResult =
            await conversationsClient.GetAgentConversationResponseAsync(agentName, conversationId, firstResponse.Id);
        Console.WriteLine($"[REST] GET conversation response -> {(int)fetchedResponseResult.GetRawResponse().Status}");
        Console.WriteLine($"  Output item(s): {fetchedResponseResult.Value.Output.Count}");

        Console.WriteLine($"\nItems produced by response {firstResponse.Id} (from GetAgentConversationResponseItems)...");
        await foreach (RealtimeItem item in conversationsClient.GetAgentConversationResponseItemsAsync(agentName, conversationId, firstResponse.Id))
        {
            Console.WriteLine($"  {SummarizeItem(item)}");
        }
    }

    // This sample uses a text-only session, so there is no recorded audio to fetch. For voice
    // conversations, the same conversationsClient also exposes GetAgentConversationAudioAsync,
    // GetAgentConversationAudioItemAsync, and GetAgentConversationGeneratedAudioItemAsync (see
    // realtime-audio for producing spoken responses).

    Console.WriteLine("\nDeleting the conversation...");
    ClientResult deleteConversationResult = await conversationsClient.DeleteAgentConversationAsync(agentName, conversationId);
    Console.WriteLine($"[REST] DELETE conversation -> {(int)deleteConversationResult.GetRawResponse().Status}");
}
finally
{
    if (created)
    {
        Console.WriteLine("\nDeleting the agent...");
        ClientResult deleteResult = await agentsClient.DeleteAgentAsync(agentName);
        Console.WriteLine($"[REST] DELETE agent -> {(int)deleteResult.GetRawResponse().Status}");
    }
}

async Task<string> RunStoredConversationAsync()
{
    Console.WriteLine("Opening a realtime session with conversation storage enabled...");
    using ProjectsRealtimeSessionClient session = (ProjectsRealtimeSessionClient)
        await projectClient.ProjectsRealtimeClient.StartSessionAsync(
            agentName,
            intent: null,
            options: new RealtimeSessionClientOptions { QueryString = "store=true" });

    await session.AddItemAsync(RealtimeItem.CreateUserMessageItem("In one short sentence, what can you help me with?"));
    await session.StartResponseAsync();

    string? conversationId = null;
    await foreach (RealtimeServerUpdate update in session.ReceiveUpdatesAsync())
    {
        if (update is RealtimeServerUpdateResponseOutputTextDelta textDelta)
        {
            Console.Write(textDelta.Delta);
        }
        else if (update is RealtimeServerUpdateError errorUpdate)
        {
            throw new InvalidOperationException($"{errorUpdate.Error.Code ?? "voice_agent_error"}: {errorUpdate.Error.Message}");
        }
        else if (update is RealtimeServerUpdateResponseDone doneUpdate)
        {
            if (doneUpdate.Response.Status != RealtimeResponseStatus.Completed)
            {
                throw new InvalidOperationException($"Voice response ended with status: {doneUpdate.Response.Status}");
            }
            conversationId = doneUpdate.Response.ConversationId;
            break;
        }
    }
    Console.WriteLine();

    return conversationId
        ?? throw new InvalidOperationException("The session did not report a conversation ID; was storage enabled?");
}

static string GetOptionalEnvironmentVariable(string name, string fallback)
{
    string? value = Environment.GetEnvironmentVariable(name)?.Trim();
    return string.IsNullOrEmpty(value) ? fallback : value;
}

async Task<bool> EnsureVoiceAgentAsync()
{
    try
    {
        await agentsClient.GetAgentAsync(agentName);
        return false;
    }
    catch (ClientResultException ex) when (ex.Status == 404)
    {
        VoiceAgentDefinition definition = new()
        {
            ModelType = VoiceModelType.SelfDeployed,
            Model = modelName,
            Instructions = "You are a helpful voice assistant. Keep answers to one short sentence.",
        };
        definition.OutputModalities.Add(VoiceOutputModality.Text);
        await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(definition));
        return true;
    }
}

// RealtimeItem only exposes its Kind as a typed property; every other field (role, text content,
// transcript, etc.) is a JsonPatch-backed extension property, so the safe, supported way to read
// them for display purposes is to write the model back to JSON and inspect that directly.
static string SummarizeItem(RealtimeItem item)
{
    BinaryData json = ModelReaderWriter.Write(item, ModelReaderWriterOptions.Json);
    using JsonDocument document = JsonDocument.Parse(json);
    JsonElement root = document.RootElement;

    if (item.Kind == RealtimeItemKind.Message && root.TryGetProperty("content", out JsonElement content))
    {
        string role = root.TryGetProperty("role", out JsonElement roleElement) ? roleElement.GetString() ?? "?" : "?";
        List<string> textParts = new();
        foreach (JsonElement part in content.EnumerateArray())
        {
            if (part.TryGetProperty("text", out JsonElement textElement) && textElement.GetString() is string text)
            {
                textParts.Add(text);
            }
            else if (part.TryGetProperty("transcript", out JsonElement transcriptElement) && transcriptElement.GetString() is string transcript)
            {
                textParts.Add(transcript);
            }
        }
        string joined = textParts.Count > 0 ? string.Join(" ", textParts) : "(no text content)";
        return $"[{role}] {joined}";
    }
    return $"[{item.Kind}]";
}

static string GetItemId(RealtimeItem item)
{
    BinaryData json = ModelReaderWriter.Write(item, ModelReaderWriterOptions.Json);
    using JsonDocument document = JsonDocument.Parse(json);
    return document.RootElement.TryGetProperty("id", out JsonElement idElement) ? idElement.GetString() ?? string.Empty : string.Empty;
}
