# Sample using agents with Image File as an input in Azure.AI.Agents

Demonstrates examples of sending an image file (along with optional text) as a structured content block in a single message. The examples shows how to create an agent, open a thread, post content blocks combining text and image inputs, and then run the agent to see how it interprets the multimedia input.

1. First, we need to set up the configuration, create a `PersistentAgentsClient`, upload the image file, and create an agent. This initial step also includes all necessary `using` directives for the samples.

```C# Snippet:AgentsImageFileStep1Common_SetupClient
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
var filePath = configuration["FileNameWithCompletePath"];
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());
```

Synchronous sample:

```C# Snippet:AgentsImageFileStep1Sync_UploadCreateAgent
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

```C# Snippet:AgentsImageFileStep1Async_UploadCreateAgent
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

2. Next, create a thread and add a message to it. The message will contain both text and a reference to the uploaded image file.

```C# Snippet:AgentsImageFileStep2Common_ContentBlocks
var contentBlocks = new List<MessageInputContentBlock>
{
    new MessageInputTextBlock("Here is an uploaded file. Please describe it:"),
    new MessageInputImageFileBlock(new MessageImageFileParam(uploadedFile.Id))
};
```

Synchronous sample:

```C# Snippet:AgentsImageFileStep2Sync_CreateThreadMessage
PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    threadId: thread.Id,
    role: MessageRole.User,
    contentBlocks: contentBlocks
);
```

Asynchronous sample:

```C# Snippet:AgentsImageFileStep2Async_CreateThreadMessage
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    contentBlocks: contentBlocks);
```

3. Then, create a run for the agent on the thread and poll its status until it completes or requires action.

Synchronous sample:

```C# Snippet:AgentsImageFileStep3Sync_CreatePollRun
ThreadRun run = client.Runs.CreateRun(
    threadId: thread.Id,
    assistantId: agent.Id
);

do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}
```

Asynchronous sample:

```C# Snippet:AgentsImageFileStep3Async_CreatePollRun
ThreadRun run = await client.Runs.CreateRunAsync(
    threadId: thread.Id,
    assistantId: agent.Id
);

do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}
```

**Comprehensive Error Handling:**

For debugging purposes, you may want to capture more detailed error information when a run fails. Here's how to get comprehensive error details:

Synchronous sample:

```C# Snippet:AgentsImageFileStep3ErrorHandlingSync
if (run.Status != RunStatus.Completed)
{
    Console.WriteLine($"Run failed with status: {run.Status}");
    Console.WriteLine($"Failed at: {run.FailedAt}");
    Console.WriteLine($"Error message: {run.LastError?.Message}");
    Console.WriteLine($"Error code: {run.LastError?.Code}");
    
    // Throw exception with comprehensive error information
    throw new Exception($"Run did not complete successfully. Status: {run.Status}, " +
                       $"Failed at: {run.FailedAt}, Error: {run.LastError?.Message}");
}
```

Asynchronous sample:

```C# Snippet:AgentsImageFileStep3ErrorHandlingAsync
if (run.Status != RunStatus.Completed)
{
    Console.WriteLine($"Run failed with status: {run.Status}");
    Console.WriteLine($"Failed at: {run.FailedAt}");
    Console.WriteLine($"Error message: {run.LastError?.Message}");
    Console.WriteLine($"Error code: {run.LastError?.Code}");
    
    // Throw exception with comprehensive error information
    throw new Exception($"Run did not complete successfully. Status: {run.Status}, " +
                       $"Failed at: {run.FailedAt}, Error: {run.LastError?.Message}");
}
```

4. After the run is complete, retrieve all messages from the thread to see the agent's response and print them to the console.

Synchronous sample:

```C# Snippet:AgentsImageFileStep4Sync_RetrieveProcessMessages
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

            case MessageImageFileContent fileItem:
                Console.WriteLine($"[{threadMessage.Role}]: Image File (internal ID): {fileItem.FileId}");
                break;
        }
    }
}
```

Asynchronous sample:

```C# Snippet:AgentsImageFileStep4Async_RetrieveProcessMessages
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

5. Finally, clean up all created resources, including the thread, the agent, and the uploaded file.

Synchronous sample:

```C# Snippet:AgentsImageFileStep5Sync_Cleanup
client.Files.DeleteFile(uploadedFile.Id);
client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);
```

Asynchronous sample:

```C# Snippet:AgentsImageFileStep5Async_Cleanup
await client.Files.DeleteFileAsync(uploadedFile.Id);
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);
```
