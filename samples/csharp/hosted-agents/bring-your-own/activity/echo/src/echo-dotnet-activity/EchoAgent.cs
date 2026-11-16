// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Builder.State;
using Microsoft.Agents.Core.Models;

namespace EchoSample;

public sealed class EchoAgent : AgentApplication
{
    public EchoAgent(AgentApplicationOptions options, ILogger<EchoAgent> logger) : base(options)
    {
        OnActivity(ActivityTypes.Message, OnMessageAsync);
        OnConversationUpdate(ConversationUpdateEvents.MembersAdded, OnMembersAddedAsync);
        OnTurnError(async (context, state, exception, cancellationToken) =>
        {
            logger.LogError(exception, "Echo turn failed");
            await context.SendActivityAsync("Sorry, something went wrong.", cancellationToken: cancellationToken);
        });
    }

    private static async Task OnMessageAsync(ITurnContext context, ITurnState state, CancellationToken cancellationToken)
    {
        var text = context.Activity.Text?.Trim();
        if (!string.IsNullOrEmpty(text))
        {
            await context.SendActivityAsync($"Echo: {text}", cancellationToken: cancellationToken);
        }
    }

    private static async Task OnMembersAddedAsync(ITurnContext context, ITurnState state, CancellationToken cancellationToken)
    {
        foreach (var member in context.Activity.MembersAdded ?? [])
        {
            if (member.Id != context.Activity.Recipient?.Id)
            {
                await context.SendActivityAsync("Welcome! Send a message and I'll echo it back.", cancellationToken: cancellationToken);
            }
        }
    }
}
