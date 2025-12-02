using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using System;
using System.Threading;
using System.Threading.Tasks;

// Get Connection information from App Configuration
IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];
var bingConnectionId = configuration["BingConnectionId"];

// Create the Agent Client
PersistentAgentsClient agentClient = new(projectEndpoint, new DefaultAzureCredential());

BingGroundingSearchConfiguration searchConfig = new BingGroundingSearchConfiguration(bingConnectionId)
{ 
    Count = 5,
    Freshness = "Week"
};

// Create the BingGroundingToolDefinition object used when creating the agent
BingGroundingToolDefinition bingGroundingTool = new BingGroundingToolDefinition(
    new BingGroundingSearchToolParameters(
        [
            searchConfig
        ]
    )
);

// Create the Agent
PersistentAgent agent = await agentClient.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "Use the bing grounding tool to answer questions.",
    tools: [bingGroundingTool]
);

PersistentAgentThread thread = await agentClient.Threads.CreateThreadAsync();

// Create message and run the agent
PersistentThreadMessage message = await agentClient.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "How does wikipedia explain Euler's Identity?");
ThreadRun run = await agentClient.Runs.CreateRunAsync(thread, agent);

// Wait for the agent to finish running
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = await agentClient.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}

// Retrieve all messages from the agent client
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
            string response = textItem.Text;

            // If we have Text URL citation annotations, reformat the response to show title & URL for citations
            if (textItem.Annotations != null)
            {
                foreach (MessageTextAnnotation annotation in textItem.Annotations)
                {
                    if (annotation is MessageTextUriCitationAnnotation urlAnnotation)
                    {
                        response = response.Replace(urlAnnotation.Text, $" [{urlAnnotation.UriCitation.Title}] ({urlAnnotation.UriCitation.Uri})");
                    }
                }
            }
            Console.Write($"Agent response: {response}");
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
        // We know this agent only has the Bing Grounding tool, so we can cast it directly
        foreach (RunStepBingGroundingToolCall toolCall in toolCallDetails.ToolCalls)
        {
            Console.WriteLine($"   Tool Call Details: {toolCall.GetType()}");

            foreach (var result in toolCall.BingGrounding)
            {
                Console.WriteLine($"      {result.Key}: {result.Value}");
            }
        }
    }
}

// Delete thread and agent
agentClient.Threads.DeleteThread(threadId: thread.Id);
agentClient.Administration.DeleteAgent(agentId: agent.Id);
