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

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "I need to solve the equation `3x + 11 = 14`. Can you help me?");

ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id,
    additionalInstructions: "Please address the user as Jane Doe. The user has a premium account.");

do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);

Pageable<ThreadMessage> messages = client.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending);

foreach (ThreadMessage threadMessage in messages)
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

client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);