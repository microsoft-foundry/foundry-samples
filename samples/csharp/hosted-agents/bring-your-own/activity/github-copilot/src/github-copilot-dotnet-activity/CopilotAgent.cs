// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Builder.State;
using Microsoft.Agents.Core.Models;

namespace CopilotSample;

public sealed class CopilotAgent : AgentApplication
{
    private readonly IAssistant _assistant;
    private readonly TaskStore _store;
    private readonly FileTransfers _files;

    public CopilotAgent(
        AgentApplicationOptions options, IAssistant assistant, TaskStore store,
        FileTransfers files, ILogger<CopilotAgent> logger) : base(options)
    {
        _assistant = assistant;
        _store = store;
        _files = files;
        OnActivity(ActivityTypes.Message, OnMessageAsync);
        OnActivity(ActivityTypes.Invoke, OnInvokeAsync);
        OnConversationUpdate(ConversationUpdateEvents.MembersAdded, OnMembersAddedAsync);
        OnTurnError(async (context, state, exception, cancellationToken) =>
        {
            logger.LogError(exception, "Copilot turn failed");
            const string message = "Sorry, I couldn't complete that request. Please try again.";
            if (context.StreamingResponse.IsStreamingChannel)
            {
                context.StreamingResponse.QueueTextChunk("\n" + message);
                await context.StreamingResponse.EndStreamAsync(cancellationToken);
            }
            else
            {
                await context.SendActivityAsync(message, cancellationToken: cancellationToken);
            }
        });
    }

    private async Task OnMessageAsync(ITurnContext context, ITurnState state, CancellationToken cancellationToken)
    {
        var conversationId = ConversationId(context);
        var attachments = await _files.DownloadAsync(context, conversationId, cancellationToken);
        var prompt = context.Activity.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(prompt))
        {
            if (attachments.Count == 0)
            {
                return;
            }
            prompt = "Read the shared files and give me their key insights and a short summary.";
        }

        var stream = context.StreamingResponse;
        var updates = Channel.CreateUnbounded<(bool IsProgress, string Text)>(new() { SingleReader = true });
        var text = new StringBuilder();
        var pump = PumpAsync();
        AssistantResult result;
        try
        {
            result = await _assistant.ReplyAsync(conversationId, prompt, attachments,
                chunk => updates.Writer.TryWrite((false, chunk)),
                progress => updates.Writer.TryWrite((true, progress)), cancellationToken);
        }
        finally
        {
            updates.Writer.TryComplete();
            await pump;
        }

        var outgoing = new List<Attachment>();
        if (result.ShowTasks)
        {
            if (context.Activity.ChannelId == "msteams")
            {
                outgoing.Add(TaskCards.Attachment(_store.List(conversationId)));
            }
            else
            {
                var tasks = _store.List(conversationId);
                var listing = tasks.Count == 0 ? "\nNo tasks yet." : "\n" + string.Join("\n",
                    tasks.Select(task => $"{(task.Done ? "[x]" : "[ ]")} {task.Title} ({task.Id})"));
                text.Append(listing);
                if (stream.IsStreamingChannel)
                {
                    stream.QueueTextChunk(listing);
                }
            }
        }
        foreach (var file in result.Files)
        {
            if (context.Activity.ChannelId == "msteams" && context.Activity.Conversation?.ConversationType == "personal")
            {
                outgoing.Add(await _files.CreateConsentAsync(conversationId, file, cancellationToken));
            }
            else
            {
                const string explanation = "\nFile downloads require a Microsoft Teams personal chat.";
                text.Append(explanation);
                if (stream.IsStreamingChannel)
                {
                    stream.QueueTextChunk(explanation);
                }
            }
        }

        if (stream.IsStreamingChannel)
        {
            stream.FinalMessage = new Activity { Type = ActivityTypes.Message, Text = text.ToString(), Attachments = outgoing };
            await stream.EndStreamAsync(cancellationToken);
        }
        else
        {
            await context.SendActivityAsync(new Activity
            {
                Type = ActivityTypes.Message, Text = text.ToString(), Attachments = outgoing
            }, cancellationToken);
        }

        async Task PumpAsync()
        {
            await foreach (var update in updates.Reader.ReadAllAsync(cancellationToken))
            {
                if (update.IsProgress)
                {
                    if (stream.IsStreamingChannel)
                    {
                        await stream.QueueInformativeUpdateAsync(update.Text, cancellationToken);
                    }
                }
                else
                {
                    text.Append(update.Text);
                    if (stream.IsStreamingChannel)
                    {
                        stream.QueueTextChunk(update.Text);
                    }
                }
            }
        }
    }

    private async Task OnInvokeAsync(ITurnContext context, ITurnState state, CancellationToken cancellationToken)
    {
        var conversationId = ConversationId(context);
        if (context.Activity.Name == "fileConsent/invoke")
        {
            await _files.HandleConsentAsync(context, conversationId, cancellationToken);
            await InvokeResponseAsync(context, 200, null, cancellationToken);
            return;
        }
        if (context.Activity.Name != "adaptiveCard/action")
        {
            await InvokeResponseAsync(context, 501, null, cancellationToken);
            return;
        }
        var action = JsonSerializer.SerializeToElement(context.Activity.Value).GetProperty("action");
        var verb = action.GetProperty("verb").GetString();
        var data = action.TryGetProperty("data", out var actionData) ? actionData : default;
        switch (verb)
        {
            case "add_task":
                _store.Add(conversationId, data.GetProperty("newTask").GetString() ?? "");
                break;
            case "complete_task":
                _store.Complete(conversationId, data.GetProperty("taskId").GetString() ?? "");
                break;
            case "delete_task":
                _store.Delete(conversationId, data.GetProperty("taskId").GetString() ?? "");
                break;
            case "refresh_tasks":
                break;
            default:
                await InvokeResponseAsync(context, 400, null, cancellationToken);
                return;
        }
        await InvokeResponseAsync(context, 200, new
        {
            statusCode = 200, type = TaskCards.ContentType, value = TaskCards.Build(_store.List(conversationId))
        }, cancellationToken);
    }

    private static async Task OnMembersAddedAsync(ITurnContext context, ITurnState state, CancellationToken cancellationToken)
    {
        foreach (var member in context.Activity.MembersAdded ?? [])
        {
            if (member.Id != context.Activity.Recipient?.Id)
            {
                await context.SendActivityAsync("Hello! I can chat, manage your to-dos, and work with shared files.",
                    cancellationToken: cancellationToken);
            }
        }
    }

    private static string ConversationId(ITurnContext context) =>
        !string.IsNullOrWhiteSpace(context.Activity.Conversation?.Id)
            ? context.Activity.Conversation.Id
            : throw new InvalidDataException("An activity must include a conversation ID.");

    private static Task<ResourceResponse> InvokeResponseAsync(
        ITurnContext context, int status, object? body, CancellationToken cancellationToken) =>
        context.SendActivityAsync(new Activity
        {
            Type = ActivityTypes.InvokeResponse, Value = new InvokeResponse { Status = status, Body = body }
        }, cancellationToken);
}
