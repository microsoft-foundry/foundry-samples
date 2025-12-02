namespace HelloWorldA365.AgentLogic;

using Microsoft.Agents.A365.Notifications.Models;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.State;

public interface IAgentLogicService
{
    /// <summary>
    /// Processes a new message received by the agent. 
    /// Returns a simple string response.
    /// This is invoked by background service and is alternate way to process emails that don't leverage SDK activities.
    /// </summary>
    Task<string> NewEmailReceived(string fromEmail, string subject, string messageBody);

    /// <summary>
    /// Processes a new chat message received by the agent.
    /// Returns a simple string response.
    /// This is invoked by background service and is alternate way to process chat messages that don't leverage SDK activities.
    /// </summary>
    Task<string> NewChatReceived(string chatId, string fromUser, string messageBody);

    /// <summary>
    /// Handles email notification events
    /// </summary>
    Task HandleEmailNotificationAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity emailEvent);

    /// <summary>
    /// Handles document comment notification events (Word, Excel, PowerPoint)
    /// </summary>
    Task HandleCommentNotificationAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity commentEvent);

    /// <summary>
    /// Handles Teams message events
    /// </summary>
    Task HandleTeamsMessageAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity teamsEvent);

    /// <summary>
    /// Handles installation update events
    /// </summary>
    Task HandleInstallationUpdateAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity installationEvent);

    /// <summary>
    /// Handles a standard activity protocol message
    /// </summary>
    /// <returns></returns>
    Task NewActivityReceived(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken);
}