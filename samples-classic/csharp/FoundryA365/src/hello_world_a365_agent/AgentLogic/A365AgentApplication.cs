namespace HelloWorldA365.AgentLogic;

using HelloWorldA365.Models;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Core.Models;
using AgentNotification;
using Microsoft.Agents.A365.Notifications.Models;

/// <summary>
/// This is main handler for incoming activities, and is linked to Agent SDK infrastructure.
/// This will need to resolve the incoming activity to the correct agent instance.
/// </summary>
public class A365AgentApplication : AgentApplication
{
    private readonly AgentLogicServiceFactory _factory;
    private readonly IConfiguration _configuration;

    public A365AgentApplication(
        AgentApplicationOptions options,
        AgentLogicServiceFactory factory,
        IConfiguration configuration) : base(options)
    {
        _factory = factory ?? throw new ArgumentNullException(nameof(factory));
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        // Configure the agent to handle message activities
        ConfigureMessageHandling();
    }

    /// <summary>
    /// Configures message handling for the agent.
    /// </summary>
    private void ConfigureMessageHandling()
    {
        // Handle Email notifications using the AgentNotification extension
        this.OnAgenticEmailNotification(async (turnContext, turnState, agentNotificationActivity, cancellationToken) =>
        {
            var agent = await GetAgentFromRecipient(turnContext.Activity);
            var agentService = await _factory.GetService(agent, turnContext);
            if (agent.IsMessagingEnabled || true)
            {
                // Use the specific email notification handler
                await agentService.HandleEmailNotificationAsync(turnContext, turnState, agentNotificationActivity);
            }
            else
            {
                await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
            }
        });

        // Handle Word notifications
        this.OnAgenticWordNotification(async (turnContext, turnState, agentNotificationActivity, cancellationToken) =>
        {
            var agent = await GetAgentFromRecipient(turnContext.Activity);
            var agentService = await _factory.GetService(agent, turnContext);

            if (agent.IsMessagingEnabled)
            {
                // Use the specific comment notification handler for Word documents
                await agentService.HandleCommentNotificationAsync(turnContext, turnState, agentNotificationActivity);
            }
            else
            {
                await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
            }
        });

        // Handle Excel notifications
        this.OnAgenticExcelNotification(async (turnContext, turnState, agentNotificationActivity, cancellationToken) =>
        {
            var agent = await GetAgentFromRecipient(turnContext.Activity);
            var agentService = await _factory.GetService(agent, turnContext);

            if (agent.IsMessagingEnabled)
            {
                // Use the specific comment notification handler for Excel documents
                await agentService.HandleCommentNotificationAsync(turnContext, turnState, agentNotificationActivity);
            }
            else
            {
                await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
            }
        });

        // Handle PowerPoint notifications
        this.OnAgenticPowerPointNotification(async (turnContext, turnState, agentNotificationActivity, cancellationToken) =>
        {
            var agent = await GetAgentFromRecipient(turnContext.Activity);
            var agentService = await _factory.GetService(agent, turnContext);

            if (agent.IsMessagingEnabled)
            {
                // Use the specific comment notification handler for PowerPoint documents
                await agentService.HandleCommentNotificationAsync(turnContext, turnState, agentNotificationActivity);
            }
            else
            {
                await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
            }
        });
        
        OnActivity(ActivityTypes.Message, async (turnContext, turnState, cancellationToken) =>
        {
            // Based on the recipient, determine which agent to use
            var agent = await GetAgentFromRecipient(turnContext.Activity);

            // Get agent logic service from factory
            var agentService = await _factory.GetService(agent, turnContext);

            // Ignoring all other channel Ids to prevent duplicate notifications.
			if (agent.IsMessagingEnabled && turnContext.Activity.ChannelId != "msteams")
            {
                return;
            }

			// Execute logic
			await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
        });

        // Keep existing handlers for backward compatibility
        OnActivity(ActivityTypes.Event, async (turnContext, turnState, cancellationToken) =>
        {
            var agent = await GetAgentFromRecipient(turnContext.Activity);
            var agentService = await _factory.GetService(agent, turnContext);

            await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
        });

        OnActivity(ActivityTypes.InstallationUpdate, async (turnContext, turnState, cancellationToken) =>
        {
            var agent = await GetAgentFromRecipient(turnContext.Activity);
            var agentService = await _factory.GetService(agent, turnContext);

            if (agent.IsMessagingEnabled)
            {
				// Create AgentNotificationActivity for installation updates
				var agentNotificationActivity = new AgentNotificationActivity(turnContext.Activity);
				await agentService.HandleInstallationUpdateAsync(turnContext, turnState, agentNotificationActivity);
            }
            else
            {
                await agentService.NewActivityReceived(turnContext, turnState, cancellationToken);
			}
		});
    }

    private async Task<AgentMetadata> GetAgentFromRecipient(IActivity activity)
    {
        ChannelAccount recipient = activity.Recipient;
        ConversationAccount conversation = activity.Conversation;

        if (recipient == null)  
        {
            throw new ArgumentNullException(nameof(recipient), "Recipient cannot be null.");
        }

        // Recipient will have an ID, but this may not be sufficient to determine the agent.
        // ChannelAccount recipient currently has an AadObjectId, which we can try using to identify the user.
        // If activityProtocol and SDK is changed to pass a new field, we can update this code to use that instead.
        var aadObjectId = Guid.TryParse(recipient.AadObjectId, out var parsedId) ? parsedId : Guid.Empty;
        var id = recipient.Id;
        var tenantId = Guid.TryParse(conversation.TenantId, out var parsedTenantId) ? parsedTenantId : Guid.Empty;
        return ConstructAgentMetadataFromActivity(activity);
    }

    private AgentMetadata ConstructAgentMetadataFromActivity(IActivity activity)
    {
        if (activity == null)
        {
            throw new ArgumentNullException(nameof(activity), "Activity cannot be null.");
        }

        var recipient = activity.Recipient;
        var conversation = activity.Conversation;

        if (recipient == null || conversation == null)
        {
            throw new ArgumentException("Activity must have a recipient and conversation.");
        }

        var tenantId = Guid.TryParse(recipient.TenantId, out var parsedTenantId) ? parsedTenantId : Guid.Empty;

        // AAI
        var agenticAppId = Guid.TryParse(recipient.AgenticAppId, out var parsedAgenticAppId) ? parsedAgenticAppId : Guid.Empty;

        // This could be agentic user email?
        var agenticUserId = recipient.AgenticUserId ?? recipient.AadObjectId;



        return new AgentMetadata
        {
            UserId = Guid.Parse(agenticUserId),
            EmailId = recipient.Id.Contains('@') ? recipient.Id : recipient.Name,
            AgentId = agenticAppId,
            AgentApplicationId = recipient.Properties.TryGetValue("agenticAppBlueprintId", out var agentAppBlueprintId) ? Guid.Parse(agentAppBlueprintId.ToString()) : Guid.TryParse(recipient.Id, out var parsedId) ? parsedId : Guid.Empty,
            TenantId = tenantId,
            AgentFriendlyName = recipient.Name,
        };
    }
}
