# Sample enterprise file search on agent with message attachment and code interpreter in Azure AI Agents

In this example we demonstrate, how the Azure Blob can be utilized for enterprize file search with `MessageAttachment`.

## Initialize

First, we set up the application configuration to retrieve necessary endpoints and credentials, and then initialize the `PersistentAgentsClient`. This step includes all necessary `using` directives from the authoritative C# files.

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
var blobURI = configuration["AzureBlobUri"];

PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());
```

## Threads and Messages

Next, we define the tools for our agent (in this case, a `CodeInterpreterToolDefinition`) and create the `PersistentAgent`.

Common tools definition:

```csharp
List<ToolDefinition> tools = [new CodeInterpreterToolDefinition()];
```

Synchronous sample:

```csharp
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are helpful agent.",
    tools: tools
);
```

Asynchronous sample:

```csharp
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are helpful agent.",
    tools: tools
);
```

A `PersistentAgentThread` is created to manage the conversation.

Synchronous sample:

```csharp
PersistentAgentThread thread = client.Threads.CreateThread();
```

Asynchronous sample:

```csharp
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();
```

We prepare a `MessageAttachment` using a `VectorStoreDataSource` that points to an Azure Blob URI. This attachment, along with the tools, is then included in a user message sent to the thread.

Common attachment preparation:

```csharp
var vectorStoreDataSource = new VectorStoreDataSource(
    assetIdentifier: blobURI,
    assetType: VectorStoreDataSourceAssetType.UriAsset
);

var attachment = new MessageAttachment(
    ds: vectorStoreDataSource,
    tools: tools
);
```

Synchronous sample:

```csharp
client.Messages.CreateMessage(
    threadId: thread.Id,
    role: MessageRole.User,
    content: "What does the attachment say?",
    attachments: [attachment]
);
```

Asynchronous sample:

```csharp
await client.Messages.CreateMessageAsync(
    threadId: thread.Id,
    role: MessageRole.User,
    content: "What does the attachment say?",
    attachments: [attachment]
);
```

## Start Run and Polling

A `ThreadRun` is initiated for the agent to process the message. We then poll the run's status until it is no longer queued, in progress, or requires action.

Synchronous sample:

```csharp
ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id
);

do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);
```

Asynchronous sample:

```csharp
ThreadRun run = await client.Runs.CreateRunAsync(
    thread.Id,
    agent.Id
);

do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);
```

## View Messages

After the run completes, we retrieve all messages from the thread in ascending order and display their content.

Synchronous sample:

```csharp
Pageable<PersistentThreadMessage> messages = client.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

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
AsyncPageable<PersistentThreadMessage> messages = client.Messages.GetMessagesAsync(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

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

Finally, we clean up the created resources by deleting the thread and the agent.

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
