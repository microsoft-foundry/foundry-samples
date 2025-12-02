# Sample using agents with Azure AI Search tool in Azure.AI.Agents.

Azure AI Search is an enterprise search system for high-performance applications.
It integrates with Azure OpenAI Service and Azure Machine Learning, offering advanced
search technologies like vector search and full-text search. Ideal for knowledge base
insights, information discovery, and automation. Creating an agent with Azure AI
Search requires an existing Azure AI Search Index. For more information and setup
guides, see [Azure AI Search Tool Guide](https://learn.microsoft.com/azure/ai-services/agents/how-to/tools/azure-ai-search).
In this example we will use the existing Azure AI Search Index as a tool for an agent.

1. First we need to create an agent and read the configuration, which will be used in the next steps.
```C# Snippet:AgentsAzureAISearchExample_CreateProjectClient
var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];
var azureAiSearchConnectionId = configuration["AzureAiSearchConnectionId"];
```

2. Create an agent with `AzureAISearchToolDefinition` and `ToolResources` with the only member `AzureAISearchToolResource` to be able to perform search. We will use `azureAiSearchConnectionId` to get the Azure AI Search resource.

Synchronous sample:
```C# Snippet:AgentsCreateAgentWithAzureAISearchTool_Sync
AzureAISearchToolResource searchResource = new(
    indexConnectionId: azureAiSearchConnectionId,
    indexName: "camping-index",
    topK: 5,
    filter: "category eq 'sleeping bag'",
    queryType: AzureAISearchQueryType.Simple
);

ToolResources toolResource = new() { AzureAISearch = searchResource };

// Create the Agent Client
PersistentAgentsClient agentClient = new(projectEndpoint, new DefaultAzureCredential());

// Create an agent with Tools and Tool Resources
PersistentAgent agent = agentClient.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "Use the index provided to answer questions.",
    tools: [new AzureAISearchToolDefinition()],
    toolResources: toolResource
);
```

Asynchronous sample:
```C# Snippet:AgentsCreateAgentWithAzureAISearchTool
AzureAISearchToolResource searchResource = new(
    indexConnectionId: azureAiSearchConnectionId,
    indexName: "sample_index",
    topK: 5,
    filter: "category eq 'sleeping bag'",
    queryType: AzureAISearchQueryType.Simple
);

ToolResources toolResource = new() { AzureAISearch = searchResource };

// Create the Agent Client
PersistentAgentsClient agentClient = new(projectEndpoint,new DefaultAzureCredential());

// Create an agent with Tools and Tool Resources
PersistentAgent agent = await agentClient.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "Use the index provided to answer questions.",
    tools: [new AzureAISearchToolDefinition()],
    toolResources: toolResource);
```

3. Now we will create a `PersistentAgentThread`, add a `PersistentThreadMessage` and `ThreadRun` to run the agent, then wait until the run completes. If the run will not be successful, we will print the last error.

Synchronous sample:
```C# Snippet:AgentsAzureAISearchExample_CreateRun_Sync
// Create thread for communication
PersistentAgentThread thread = agentClient.Threads.CreateThread();

// Create message and run the agent
PersistentThreadMessage message = agentClient.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "What is the temperature rating of the cozynights sleeping bag?");
ThreadRun run = agentClient.Runs.CreateRun(thread, agent);

// Wait for the agent to finish running
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = agentClient.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}
```

Asynchronous sample:
```C# Snippet:AgentsAzureAISearchExample_CreateRun
// Create thread for communication
PersistentAgentThread thread = await agentClient.Threads.CreateThreadAsync();

// Create message and run the agent
PersistentThreadMessage message = await agentClient.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "What is the temperature rating of the cozynights sleeping bag?");
ThreadRun run = await agentClient.Runs.CreateRunAsync(thread, agent);

// Wait for the agent to finish running
do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await agentClient.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}
```

4. In our search we have used an index containing "embedding", "token", "category" and also "title" fields. This allowed us to get reference title and url. In the code below, we iterate messages in chronological order and replace the reference placeholders by url and title.

Synchronous sample:
```C# Snippet:AgentsPopulateReferencesAgentWithAzureAISearchTool_Sync
// Retrieve the messages from the agent client
Pageable<PersistentThreadMessage> messages = agentClient.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

// Process messages in order
foreach (PersistentThreadMessage threadMessage in messages)
{
    Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");
    foreach (MessageContent contentItem in threadMessage.ContentItems)
    {
        if (contentItem is MessageTextContent textItem)
        {
            // We need to annotate only Agent messages.
            if (threadMessage.Role == MessageRole.Agent && textItem.Annotations.Count > 0)
            {
                string annotatedText = textItem.Text;

                // If we have Text URL citation annotations, reformat the response to show title & URL for citations
                foreach (MessageTextAnnotation annotation in textItem.Annotations)
                {
                    if (annotation is MessageTextUriCitationAnnotation urlAnnotation)
                    {
                        annotatedText = annotatedText.Replace(
                            urlAnnotation.Text,
                            $" [see {urlAnnotation.UriCitation.Title}] ({urlAnnotation.UriCitation.Uri})");
                    }
                }
                Console.Write(annotatedText);
            }
            else
            {
                Console.Write(textItem.Text);
            }
        }
        else if (contentItem is MessageImageFileContent imageFileItem)
        {
            Console.Write($"<image from ID: {imageFileItem.FileId}");
        }
        Console.WriteLine();
    }
}

// Retrieve the run steps used by the agent and print those to the console
Console.WriteLine("Run Steps used by Agent:");
Pageable<RunStep> runSteps = agentClient.Runs.GetRunSteps(run);

foreach (var step in runSteps)
{
    Console.WriteLine($"Step ID: {step.Id}, Total Tokens: {step.Usage.TotalTokens}, Status: {step.Status}, Type: {step.Type}");

    if (step.StepDetails is RunStepMessageCreationDetails messageCreationDetails)
    {
        Console.WriteLine($"   Message Creation Id: {messageCreationDetails.MessageCreation.MessageId}");
    }
    else if (step.StepDetails is RunStepToolCallDetails toolCallDetails)
    {
        // We know this agent only has the AI Search tool, so we can cast it directly
        foreach (RunStepAzureAISearchToolCall toolCall in toolCallDetails.ToolCalls)
        {
            Console.WriteLine($"   Tool Call Details: {toolCall.GetType()}");

            foreach (var result in toolCall.AzureAISearch)
            { 
                Console.WriteLine($"      {result.Key}: {result.Value}");
            }
        }
    }
}
```

Asynchronous sample:
```C# Snippet:AgentsPopulateReferencesAgentWithAzureAISearchTool
// Retrieve the messages from the agent client
AsyncPageable<PersistentThreadMessage> messages = agentClient.Messages.GetMessagesAsync(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

// Process messages in order
await foreach (PersistentThreadMessage threadMessage in messages)
{
    Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");
    foreach (MessageContent contentItem in threadMessage.ContentItems)
    {
        if (contentItem is MessageTextContent textItem)
        {
            // We need to annotate only Agent messages.
            if (threadMessage.Role == MessageRole.Agent && textItem.Annotations.Count > 0)
            {
                string annotatedText = textItem.Text;

                // If we have Text URL citation annotations, reformat the response to show title & URL for citations
                foreach (MessageTextAnnotation annotation in textItem.Annotations)
                {
                    if (annotation is MessageTextUriCitationAnnotation urlAnnotation)
                    {
                        annotatedText = annotatedText.Replace(
                            urlAnnotation.Text,
                            $" [see {urlAnnotation.UriCitation.Title}] ({urlAnnotation.UriCitation.Uri})");
                    }
                }
                Console.Write(annotatedText);
            }
            else
            {
                Console.Write(textItem.Text);
            }
        }
        else if (contentItem is MessageImageFileContent imageFileItem)
        {
            Console.Write($"<image from ID: {imageFileItem.FileId}");
        }
        Console.WriteLine();
    }
}

// Retrieve the run steps used by the agent and print those to the console
Console.WriteLine("Run Steps used by Agent:");
AsyncPageable<RunStep> runSteps = agentClient.Runs.GetRunStepsAsync(run);

await foreach (var step in runSteps)
{
    Console.WriteLine($"Step ID: {step.Id}, Total Tokens: {step.Usage.TotalTokens}, Status: {step.Status}, Type: {step.Type}");

    if (step.StepDetails is RunStepMessageCreationDetails messageCreationDetails)
    {
        Console.WriteLine($"   Message Creation Id: {messageCreationDetails.MessageCreation.MessageId}");
    }
    else if (step.StepDetails is RunStepToolCallDetails toolCallDetails)
    {
        // We know this agent only has the AI Search tool, so we can cast it directly
        foreach (RunStepAzureAISearchToolCall toolCall in toolCallDetails.ToolCalls)
        {
            Console.WriteLine($"   Tool Call Details: {toolCall.GetType()}");

            foreach (var result in toolCall.AzureAISearch)
            {
                Console.WriteLine($"      {result.Key}: {result.Value}");
            }
        }
    }
}
```

5. Finally, we delete all the resources, we have created in this sample.

Synchronous sample:
```C# Snippet:AgentsAzureAISearchExample_Cleanup_Sync
// Clean up resources
agentClient.Threads.DeleteThread(thread.Id);
agentClient.Administration.DeleteAgent(agent.Id);
```

Asynchronous sample:
```C# Snippet:AgentsAzureAISearchExample_Cleanup
// Clean up resources
await agentClient.Threads.DeleteThreadAsync(thread.Id);
await agentClient.Administration.DeleteAgentAsync(agent.Id);
```
