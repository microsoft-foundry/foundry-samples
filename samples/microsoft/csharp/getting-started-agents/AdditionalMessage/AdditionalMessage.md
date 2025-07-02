# Sample for using additional messages while creating agent run in Azure.AI.Agents

1. Set up configuration, create an agent client, and create an agent. This step includes all necessary `using` directives.

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CommonSetup
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
```

Synchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CreateAgentSync
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "Math Tutor",
    instructions: "You are a personal electronics tutor. Write and run code to answer questions.",
    tools: [new CodeInterpreterToolDefinition()]);
```

Asynchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CreateAgentAsync
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "Math Tutor",
    instructions: "You are a personal electronics tutor. Write and run code to answer questions.",
    tools: [new CodeInterpreterToolDefinition()]);
```

1. Create the thread and add an initial message to it.

Synchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CreateThreadAndMessageSync
PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "What is the impedance formula?");
```

Asynchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CreateThreadAndMessageAsync
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "What is the impedance formula?");
```

1. Create the run with additional messages and poll for completion.
   In this example we add two extra messages to the thread when creating the run: one with the `MessageRole.Agent` role and another with the `MessageRole.User` role.

Synchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CreateAndPollRunSync
ThreadRun run = client.Runs.CreateRun(
    threadId: thread.Id,
    agent.Id,
    additionalMessages: [
        new ThreadMessageOptions(
            role: MessageRole.Agent,
            content: "E=mc^2"
        ),
        new ThreadMessageOptions(
            role: MessageRole.User,
            content: "What is the impedance formula?"
        ),
    ]
);

do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);
```

Asynchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CreateAndPollRunAsync
ThreadRun run = await client.Runs.CreateRunAsync(
    threadId: thread.Id,
    agent.Id,
    additionalMessages: [
        new ThreadMessageOptions(
            role: MessageRole.Agent,
            content: "E=mc^2"
        ),
        new ThreadMessageOptions(
            role: MessageRole.User,
            content: "What is the impedance formula?"
        ),
    ]
);

do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);
```

1. Print out all the messages to the console.

Synchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_PrintMessagesSync
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
```

Asynchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_PrintMessagesAsync
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
```

1. Finally, clean up resources (delete the thread and agent).

Synchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CleanupSync
client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);
```

Asynchronous sample:

```C# Snippet:Sample_PersistentAgent_AdditionalMessages_CleanupAsync
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);
```
