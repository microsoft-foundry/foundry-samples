namespace HelloWorldA365.AgentLogic.SemanticKernel;

using HelloWorldA365.AgentLogic.AuthCache;
using HelloWorldA365.Services;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.State;
using Microsoft.Agents.Core.Models;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.ChatCompletion;
using System;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using AgentMetadata = HelloWorldA365.Models.AgentMetadata;
using Microsoft.Agents.A365.Tooling.Extensions.SemanticKernel.Services;
using Microsoft.Agents.A365.Observability.Runtime.Common;
using Microsoft.Agents.A365.Observability.Extensions.SemanticKernel;
using Microsoft.Agents.A365.Notifications.Models;
using Microsoft.Agents.A365.Observability.Common;

/// <summary>
/// Semantic Kernel-based implementation of AgentLogicService.
/// This contains all core business logic for a agent instance using Semantic Kernel.
/// </summary>
public class SemanticKernelAgentLogicService : IAgentLogicService
{
    private readonly Kernel _kernel;
    private readonly AgentMetadata _agentMetadata;
    private readonly ChatCompletionAgent _chatCompletionAgent;
    private readonly ILogger _logger;

    public SemanticKernelAgentLogicService(
        AgentTokenHelper tokenHelper,
        AgentMetadata agent,
        Kernel kernel,
        string certificateData,
        IConfiguration config,
        ILogger logger,
        IMcpToolRegistrationService mcpToolRegistrationService,
        IAgentTokenCache tokenCache)
    {
        _agentMetadata = agent ?? throw new ArgumentNullException(nameof(agent));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));

        // Register observability-only credential (separate instance to isolate caching if needed)
        var observabilityCredential = new AgentTokenCredential(tokenHelper, agent, certificateData);
        var obsScopes = EnvironmentUtils.GetObservabilityAuthenticationScope();
        tokenCache.RegisterObservability(agent.AgentId.ToString(), agent.TenantId.ToString(), observabilityCredential, obsScopes);

        var deployment = config["ModelDeployment"] ?? throw new ArgumentNullException("ModelDeployment");
        var endpoint = config["AzureOpenAIEndpoint"];
        var mem0Token = config["Mem0ApiToken"];
        if (string.IsNullOrWhiteSpace(deployment) || string.IsNullOrWhiteSpace(endpoint))
        {
            throw new InvalidOperationException("ModelDeployment and AzureOpenAIEndpoint must be configured.");
        }

        // Create an HttpClient for the Mem0 service if key is provided
        if (!string.IsNullOrWhiteSpace(mem0Token))
        {
            var httpClient = new HttpClient()
            {
                BaseAddress = new Uri("https://api.mem0.ai")
            };
            httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", mem0Token);
        }

        var instructions = AgentInstructions.GetInstructions(agent);
        _kernel = kernel;
        _chatCompletionAgent = new ChatCompletionAgent
        {
            // NOTE: This ID should match the agent ID for which the token is registered on L48-51 above
            Id = agent.AgentId.ToString(),
            Name = agent.EmailId,
            Instructions = instructions,
            Kernel = _kernel,
            Arguments = new KernelArguments(new PromptExecutionSettings()
            {
                FunctionChoiceBehavior = FunctionChoiceBehavior.Auto()
            }),
        }.WithTracing();
    }

    /// <summary>
    /// This processes message from activity protocol, aka ABS (Azure Bot Service).
    /// </summary>
    public async Task NewActivityReceived(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken)
    {
        var baggageScope = new BaggageBuilder()
            .FromTurnContext(turnContext)
            .CorrelationId(turnContext.Activity.RequestId)
            .Build();

        var incomingText = turnContext.Activity.Text;
        _logger.LogInformation("New activity received (Semantic Kernel): {IncomingText}", incomingText);

        // Log target recipient
        var recipient = turnContext.Activity.Recipient;
        var json = recipient != null ? JsonSerializer.Serialize(recipient) : "null";
        _logger.LogInformation("Target Recipient: {Recipient}", json);

        // Log sender information
        var sender = turnContext.Activity.From;
        var jsonSender = sender != null ? JsonSerializer.Serialize(sender) : "null";
        _logger.LogInformation("Sender: {Sender}", jsonSender);

        bool skipResponse = false;
        if (turnContext.Activity.ChannelId == "email" || turnContext.Activity.ChannelId == "agents:email")
        {
            var subject = string.Empty;
            if (turnContext.Activity.ChannelData is JsonElement jsonElement && jsonElement.TryGetProperty("subject", out var subjectProperty))
            {
                subject = subjectProperty.GetString() ?? string.Empty;
            }

            _logger.LogInformation("Extracted subject: {Subject}", subject);
            incomingText = $"Please respond to this email From: {sender!.Id}\nSubject: {subject}\nMessage: {incomingText}";
            if (!string.IsNullOrEmpty(sender?.Id) && sender.Id.Contains("MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109"))
            {
                _logger.LogWarning("Non delivery response from MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109 skipping further response to prevent infinite loop of email storm");
                skipResponse = true;
            }
        }
        else if (turnContext.Activity.ChannelId == "msteams")
        {
            // name and email missing in teams channel data
            incomingText = $"Respond to this chat message with chat id {turnContext.Activity.Conversation.Id} " +
                           $"From: {sender?.Name} ({sender?.Id})\n" +
                           $"Message: {incomingText}";
        }
        else if (turnContext.Activity.Type == ActivityTypes.InstallationUpdate)
        {
            incomingText = $"You were just added as a digital worker. Please send an email to {sender!.Id} with a information on what you can do.";
        }

        if (!skipResponse)
        {
            await foreach (var responseItem in InvokeAgentAsync(incomingText))
            {
                try
                {
                    var responseText = responseItem.Message.Content ?? string.Empty;
                    _logger.LogInformation("Sending response: {ResponseText}", responseText);

                    await turnContext.SendActivityAsync(MessageFactory.Text(responseText), cancellationToken);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error sending response: {ResponseText}", responseItem.Message.Content);
                }
            }
        }

        await Task.CompletedTask;
    }

    public async Task<string> NewEmailReceived(string fromEmail, string subject, string messageBody)
    {
        using var baggageScope = new BaggageBuilder()
            .TenantId(_agentMetadata.TenantId.ToString())
            .AgentId(_agentMetadata.AgentId.ToString())
            .Build();

        try
        {
            ChatHistoryAgentThread agentThread = new();

            var formattedMessage = $"Please respond to this email From: {fromEmail}\nSubject: {subject}\nMessage: {messageBody}";

            var responseText = new StringBuilder();
            await foreach (var responseItem in InvokeAgentAsync(formattedMessage, agentThread))
            {
                responseText.Append(responseItem.Message.Content ?? string.Empty);
            }

            return responseText.ToString();
        }
        catch (Exception ex)
        {
            throw new Exception($"Error processing message: {ex.Message}", ex);
        }
    }

    public async Task<string> NewChatReceived(string chatId, string fromUser, string messageBody)
    {
        using var baggageScope = new BaggageBuilder()
            .TenantId(_agentMetadata.TenantId.ToString())
            .AgentId(_agentMetadata.AgentId.ToString())
            .Build();

        try
        {
            ChatHistoryAgentThread agentThread = new();

            // Create context and user messages
            var contextMessage = new ChatMessageContent(AuthorRole.System, $"You are chatting with {fromUser} via Teams - ChatId {chatId}");
            var userMessage = new ChatMessageContent(AuthorRole.User, messageBody);
            var messages = new List<ChatMessageContent> { contextMessage, userMessage };

            var responseText = new StringBuilder();
            await foreach (var responseItem in _chatCompletionAgent.InvokeAsync(messages, agentThread))
            {
                responseText.Append(responseItem.Message.Content ?? string.Empty);
            }

            // Reset status message and set presence to Available before returning

            return responseText.ToString();
        }
        catch (Exception ex)
        {
            throw new Exception($"Error processing chat message: {ex.Message}", ex);
        }
    }


    #region IAgentLogicService Event Handler Methods

    /// <summary>
    /// Handles email notification events from Messaging
    /// </summary>
    public async Task HandleEmailNotificationAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity emailEvent)
    {
        _logger.LogInformation("Processing email notification - NotificationType: {NotificationType}",
            emailEvent.NotificationType);

        var emailContent = emailEvent.Text ?? string.Empty;

        // Collect all agent responses into a single text
        var responseText = new StringBuilder();
        await foreach (var responseItem in InvokeAgentAsync(emailContent))
        {
            responseText.Append(responseItem.Message.Content ?? string.Empty);
        }

        // var responseActivity =  Microsoft.Agents.A365.Notifications.Models.EmailResponse.CreateEmailResponseActivity(responseText.ToString());
        // Create email response with the collected content
        var responseActivity2 = MessageFactory.Text("a");
        responseActivity2.Entities.Add(new EmailResponse(responseText.ToString()));
        await turnContext.SendActivityAsync(responseActivity2);

    }

    /// <summary>
    /// Handles document comment notification events (Word, Excel, PowerPoint) from Messaging
    /// </summary>
    public async Task HandleCommentNotificationAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity commentEvent)
    {
        _logger.LogInformation("Processing comment notification - NotificationType: {NotificationType}",
            commentEvent.NotificationType);

        // For now returning a static response - can be enhanced with actual AI processing
        var responseText = "Hello this is a response to a comment notification received through Messaging.";
        var commentActivity = MessageFactory.Text(responseText);
        turnContext.SendActivityAsync(commentActivity);
    }

    /// <summary>
    /// Handles Teams message events from Messaging
    /// </summary>
    public async Task HandleTeamsMessageAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity teamsEvent)
    {
        _logger.LogInformation("Processing Teams message event - From: {FromUser}",
            teamsEvent.From?.Name);

        var formattedMessage = $"Respond to this chat message with chat id {teamsEvent.Conversation?.Id} " +
                              $"From: {teamsEvent.From?.Name} ({teamsEvent.From?.Id})\n" +
                              $"Message: {teamsEvent.Text}";

        // For now returning a static response - can be enhanced with actual AI processing
        var responseText = "Hello this is a response to a Teams message received through Messaging.";

        _logger.LogInformation("Teams message response prepared: {ResponseText}", responseText);
    }

    /// <summary>
    /// Handles installation update events from Messaging
    /// </summary>
    public async Task HandleInstallationUpdateAsync(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity installationEvent)
    {
        _logger.LogInformation("Processing installation update event for {SenderId}", installationEvent.From?.Id);

        var formattedMessage = $"You were just added as a digital worker. Please send an email to {installationEvent.From?.Id} with information on what you can do.";

        // For now returning a static response - can be enhanced with actual AI processing
        var responseText = "Hello this is a response to an installation update received through Messaging.";

        _logger.LogInformation("Installation update response prepared: {ResponseText}", responseText);
    }

    /// <summary>
    /// Handles generic activity events that don't fit other categories
    /// </summary>
    public async Task NewActivityReceived(ITurnContext turnContext, ITurnState turnState, AgentNotificationActivity genericEvent)
    {
        _logger.LogInformation("Processing generic activity event - NotificationType: {NotificationType}",
            genericEvent.NotificationType);

        // For generic events, provide basic processing
        // For now, just return a static response
        var responseText = "Hello this is a response to a generic activity received through Messaging.";

        _logger.LogInformation("Generic activity response prepared: {ResponseText}", responseText);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Invokes the agent with the specified input text and returns the response stream.
    /// The caller is responsible for handling the responses (e.g., sending via turn context or collecting as string).
    /// </summary>
    /// <param name="incomingText">The input text to send to the agent</param>
    /// <param name="agentThread">Optional agent thread to use. If null, creates a new empty thread.</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>An async enumerable of agent response items</returns>
    private IAsyncEnumerable<AgentResponseItem<ChatMessageContent>> InvokeAgentAsync(
        string incomingText,
        ChatHistoryAgentThread? agentThread = null,
        CancellationToken cancellationToken = default)
    {
        // NOTE: This won't retain history from previous messages in the thread currently
        //       This could be added at a later time
        //       For now, just always use new empty thread unless one is provided
        agentThread ??= new ChatHistoryAgentThread();

        var content = new ChatMessageContent
        {
            Role = AuthorRole.User,
            Content = incomingText,
        };

        return _chatCompletionAgent.InvokeAsync(content, agentThread, cancellationToken: cancellationToken);
    }

    #endregion
}