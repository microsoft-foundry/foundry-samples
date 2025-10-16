# Sample using agents with Image File as an input in Azure.AI.Agents

Demonstrates examples of sending an image file (along with optional text) as a structured content block in a single message. The examples shows how to create an agent, open a thread, post content blocks combining text and image inputs, and then run the agent to see how it interprets the multimedia input.

## Initialize

First, we need to set up the configuration, create a `PersistentAgentsClient`, upload the image file, and create an agent. This initial step also includes all necessary `using` directives for the samples.

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
// Get a local image file with full path.
var filePath = configuration["FileNameWithCompletePath"];

PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());
```

Synchronous sample:

```csharp
PersistentAgentFileInfo uploadedFile = client.Files.UploadFile(
    filePath: filePath,
    purpose: PersistentAgentFilePurpose.Agents
);

PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "File Image Understanding Agent",
    instructions: "Analyze images from internally uploaded files."
);
```

Asynchronous sample:

```csharp
PersistentAgentFileInfo uploadedFile = await client.Files.UploadFileAsync(
    filePath: filePath,
    purpose: PersistentAgentFilePurpose.Agents
);

PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "File Image Understanding Agent",
    instructions: "Analyze images from internally uploaded files."
);
```

## Threads and Messages

Next, create a thread and add a message to it. The message will contain both text and a reference to the uploaded image file.

```csharp
var contentBlocks = new List<MessageInputContentBlock>
{
    new MessageInputTextBlock("Here is an uploaded file. Please describe it:"),
    new MessageInputImageFileBlock(new MessageImageFileParam(uploadedFile.Id))
};
```

Synchronous sample:

```csharp
PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    contentBlocks: contentBlocks
);
```

Asynchronous sample:

```csharp
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    contentBlocks: contentBlocks);
```

## Runs, Additional Messages and Polling

Then, create a run for the agent on the thread and poll its status until it completes or requires action.

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
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);
```

## View Messages

After the run is complete, retrieve all messages from the thread to see the agent's response and print them to the console.

Synchronous sample:

```csharp
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

Finally, clean up all created resources, including the thread, the agent, and the uploaded file.

Synchronous sample:

```csharp
client.Files.DeleteFile(uploadedFile.Id);
client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);
```

Asynchronous sample:

```csharp
await client.Files.DeleteFileAsync(uploadedFile.Id);
await client.Threads.DeleteThreadAsync(thread.Id);
await client.Administration.DeleteAgentAsync(agent.Id);
```
