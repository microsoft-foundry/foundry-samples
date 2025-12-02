using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;

IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "Math Tutor",
    instructions: "You are a personal math tutor. Write and run code to answer math questions."
);

PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "I need to solve the equation `3x + 11 = 14`. Can you help me?");

ThreadRun run = await client.Runs.CreateRunAsync(
    thread.Id,
    agent.Id,
    additionalInstructions: "Please address the user as Jane Doe. The user has a premium account.");

do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);

AsyncPageable<ThreadMessage> messages = client.Messages.GetMessagesAsync(
    threadId: thread.Id,
    order: ListSortOrder.Ascending);

await foreach (ThreadMessage threadMessage in messages)
{
    foreach (MessageContent content in threadMessage.ContentItems)
    {
        switch (content)
        {
            case MessageTextContent textItem:
                Console.WriteLine($"[{threadMessage.Role}]: {textItem.Text}");
                break;
        }
    }
}

await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);