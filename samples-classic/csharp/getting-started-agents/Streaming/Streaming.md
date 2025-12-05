# Sample using agents with streaming in Azure.AI.Agents

In this example we will demonstrate the agent streaming support.

1. First, we set up configuration using `appsettings.json`, create a `PersistentAgentsClient`, and then create a `PersistentAgent` with the Code Interpreter tool.

```C# Snippet:AgentsStreaming_Step1_Common_SetupClientAndConfig
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using System.Diagnostics;

IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];

PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());
```

Synchronous sample:

```C# Snippet:AgentsStreaming_Step1_Sync_CreateAgent
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "My Friendly Test Agent",
    instructions: "You politely help with math questions. Use the code interpreter tool when asked to visualize numbers.",
    tools: [new CodeInterpreterToolDefinition()]
);
```

Asynchronous sample:

```C# Snippet:AgentsStreaming_Step1_Async_CreateAgent
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "My Friendly Test Agent",
    instructions: "You politely help with math questions. Use the code interpreter tool when asked to visualize numbers.",
    tools: [new CodeInterpreterToolDefinition()]
);
```

2. Next, we create a `PersistentAgentThread` and add a user message to it.

Synchronous sample:

```C# Snippet:AgentsStreaming_Step2_Sync_CreateThreadAndMessage
PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Hi, Agent! Draw a graph for a line with a slope of 4 and y-intercept of 9.");
```

Asynchronous sample:

```C# Snippet:AgentsStreaming_Step2_Async_CreateThreadAndMessage
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "Hi, Agent! Draw a graph for a line with a slope of 4 and y-intercept of 9.");
```

3. Then, we create a `ThreadRun` for the thread and agent, providing any additional instructions. We poll the run's status until it is no longer queued, in progress, or requires action.

Synchronous sample:

```C# Snippet:AgentsStreaming_Step3_Sync_CreateAndPollRun
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
```

Asynchronous sample:

```C# Snippet:AgentsStreaming_Step3_Async_CreateAndPollRun
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
```

4. Once the run is finished, we retrieve all messages from the thread. We then iterate through the messages to display text content and handle any image files by saving them locally and opening them.

Synchronous sample:

```C# Snippet:AgentsStreaming_Step4_Sync_ProcessMessages
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
            case MessageImageFileContent imageFileContent:
                Console.WriteLine($"[{threadMessage.Role}]: Image content file ID = {imageFileContent.FileId}");
                BinaryData imageContent = client.Files.GetFileContent(imageFileContent.FileId);
                string tempFilePath = Path.Combine(AppContext.BaseDirectory, $"{Guid.NewGuid()}.png");
                File.WriteAllBytes(tempFilePath, imageContent.ToArray());
                client.Files.DeleteFile(imageFileContent.FileId);

                ProcessStartInfo psi = new()
                {
                    FileName = tempFilePath,
                    UseShellExecute = true
                };
                Process.Start(psi);
                break;
        }
    }
}
```

Asynchronous sample:

```C# Snippet:AgentsStreaming_Step4_Async_ProcessMessages
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
            case MessageImageFileContent imageFileContent:
                Console.WriteLine($"[{threadMessage.Role}]: Image content file ID = {imageFileContent.FileId}");
                BinaryData imageContent = await client.Files.GetFileContentAsync(imageFileContent.FileId);
                string tempFilePath = Path.Combine(AppContext.BaseDirectory, $"{Guid.NewGuid()}.png");
                File.WriteAllBytes(tempFilePath, imageContent.ToArray());
                await client.Files.DeleteFileAsync(imageFileContent.FileId);

                ProcessStartInfo psi = new()
                {
                    FileName = tempFilePath,
                    UseShellExecute = true
                };
                Process.Start(psi);
                break;
        }
    }
}
```

5. Finally, we delete the thread and the agent to clean up the resources created in this sample.

Synchronous sample:

```C# Snippet:AgentsStreaming_Step5_Sync_Cleanup
client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);
```

Asynchronous sample:

```C# Snippet:AgentsStreaming_Step5_Async_Cleanup
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);
```
