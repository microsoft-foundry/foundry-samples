# Sample for basic use of an agent in Azure.AI.Agents

In this example we will demonstrate creation and basic use of an agent step by step.

## Initialize

First, we set up the configuration using `appsettings.json` to read necessary parameters like the project endpoint and model deployment name. Then, we initialize the `PersistentAgentsClient` using these settings and default Azure credentials. With the client ready, we create a 'Math Tutor' agent, providing it with instructions on its role and capabilities.

```csharp
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

```csharp
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "Math Tutor",
    instructions: "You are a personal math tutor. Write and run code to answer math questions."
);
```

Asynchronous sample:

```csharp
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "Math Tutor",
    instructions: "You are a personal math tutor. Write and run code to answer math questions."
);
```

## Threads and Messages

Next, we create a new thread to serve as the conversation context.

Synchronous sample:

```csharp
PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "I need to solve the equation `3x + 11 = 14`. Can you help me?");

ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id,
    additionalInstructions: "Please address the user as Jane Doe. The user has a premium account.");
```

Asynchronous sample:

```csharp
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "I need to solve the equation `3x + 11 = 14`. Can you help me?");

ThreadRun run = await client.Runs.CreateRunAsync(
    thread.Id,
    agent.Id,
    additionalInstructions: "Please address the user as Jane Doe. The user has a premium account.");
```

## Start Run and Polling

Agent execution can take some time. We first poll the run's status by repeatedly fetching it until it reaches a terminal state, waiting for it to no longer be `RunStatus.Queued`, `RunStatus.InProgress`, or `RunStatus.RequiresAction`.

Synchronous sample:

```csharp
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

Pageable<PersistentThreadMessage> messages = client.Messages.GetMessages(
    thread.Id,
    order: ListSortOrder.Ascending);

foreach (PersistentThreadMessage threadMessage in messages)
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

```csharp
do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

## View Messages

Once the run is complete, we retrieve all messages from the thread in ascending order and print the text content of each message to the console, prefixed by its role (e.g., User, Assistant).

AsyncPageable<PersistentThreadMessage> messages = client.Messages.GetMessagesAsync(
    thread.Id,
    order: ListSortOrder.Ascending);

await foreach (PersistentThreadMessage threadMessage in messages)
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

## Cleanup Resources

Finally, to ensure proper resource management and avoid orphaned entities in the Azure service, we delete the thread and the agent that were created for this interaction.

Synchronous sample:

```csharp
client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);
```

Asynchronous sample:

```csharp
await client.Threads.DeleteThreadAsync(thread.Id);
await client.Administration.DeleteAgentAsync(agent.Id);
   ```
