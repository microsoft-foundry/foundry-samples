//<create_and_run_agent>
using Azure;
using Azure.Identity;
using Azure.AI.Agents.Persistent;

// Creating the Client for agents
var projectEndpoint = System.Environment.GetEnvironmentVariable("AZURE_AI_ENDPOINT");
var modelDeploymentName = System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL");
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

// Create an Agent with toolResources and process Agent run
PersistentAgent agent = client.Administration.CreateAgent(
        model: modelDeploymentName,
        name: "SDK Test Agent - Tutor",
        instructions: "You are a personal electronics tutor. Write and run code to answer questions.",
        tools: new List<ToolDefinition> { new CodeInterpreterToolDefinition() });

// Create thread for communication
PersistentAgentThread thread = client.Threads.CreateThread();

// Create message to thread
PersistentThreadMessage messageResponse = client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "I need to solve the equation `3x + 11 = 14`. Can you help me?");

// Run the Agent
ThreadRun run = client.Runs.CreateRun(thread, agent);

// Wait for the run to complete
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);
Pageable<PersistentThreadMessage> messages = client.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);
// Print the messages in the thread
WriteMessages(messages);

// Delete the thread and agent after use
client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);

// Temporary function to use a list of messages in the thread and write them to the console.
static void WriteMessages(IEnumerable<PersistentThreadMessage> messages)
{
    foreach (PersistentThreadMessage threadMessage in messages)
    {
        Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");
        foreach (MessageContent contentItem in threadMessage.ContentItems)
        {
            if (contentItem is MessageTextContent textItem)
            {
                Console.Write(textItem.Text);
            }
            else if (contentItem is MessageImageFileContent imageFileItem)
            {
                Console.Write($"<image from ID: {imageFileItem.FileId}");
            }
            Console.WriteLine();
        }
    }
}
//</create_and_run_agent>