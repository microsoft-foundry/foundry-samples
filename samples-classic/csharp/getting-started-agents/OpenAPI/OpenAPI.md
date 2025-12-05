# Sample file search on agent with message attachment and code interpreter in Azure.AI.Agents

In this example we demonstrate, how to use file search with `MessageAttachment`.

1. First, we set up the configuration, create the `PersistentAgentsClient`, define a local file, create an agent, and upload the local file for the agent to use. The necessary `using` directives from the source files are included in the common setup.

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step1_CommonSetup
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using System.IO;

IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];

PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

string fileName = "sample_file_for_upload.txt";
string fullPath = Path.Combine(AppContext.BaseDirectory, fileName);

File.WriteAllText(
    path: fullPath,
    contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457.");
```

Synchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step1_CreateAgentAndUploadFile_Sync
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are a helpful agent that can help fetch data from files you know about.",
    tools: [new CodeInterpreterToolDefinition()]);

PersistentAgentFileInfo uploadedAgentFile = client.Files.UploadFile(
    filePath: fullPath,
    purpose: PersistentAgentFilePurpose.Agents);
```

Asynchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step1_CreateAgentAndUploadFile_Async
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are a helpful agent that can help fetch data from files you know about.",
    tools: [new CodeInterpreterToolDefinition()]);

PersistentAgentFileInfo uploadedAgentFile = await client.Files.UploadFileAsync(
    filePath: "sample_file_for_upload.txt",
    purpose: PersistentAgentFilePurpose.Agents);
```

2. Next, we create a message attachment using the `PersistentAgentFileInfo.Id` from the uploaded file, create a new agent thread, and add a user message to this thread, including the attachment.

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step2_CommonMessageAttachment
MessageAttachment attachment = new(
    fileId: uploadedAgentFile.Id,
    tools: [new CodeInterpreterToolDefinition()]);
```

Synchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step2_CreateThreadAndMessage_Sync
PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    threadId: thread.Id,
    role: MessageRole.User,
    content: "Can you give me the documented codes for 'banana' and 'orange'?",
    attachments: [attachment]);
```

Asynchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step2_CreateThreadAndMessage_Async
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    threadId: thread.Id,
    role: MessageRole.User,
    content: "Can you give me the documented codes for 'banana' and 'orange'?",
    attachments: [attachment]);
```

3. Then, we create a `ThreadRun` to process the message with the agent and poll its status until it is no longer queued, in progress, or requires action.

Synchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step3_CreateAndPollRun_Sync
ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id);

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

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step3_CreateAndPollRun_Async
ThreadRun run = await client.Runs.CreateRunAsync(
    thread.Id,
    agent.Id);

do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);
```

4. After the run completes, we retrieve all messages from the thread in ascending order and print their content to the console.

Synchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step4_PrintMessages_Sync
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

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step4_PrintMessages_Async
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

5. Finally, we clean up the resources created during this sample, including the uploaded file, the agent thread, and the agent itself.

Synchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step5_Cleanup_Sync
client.Files.DeleteFile(uploadedAgentFile.Id);
client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);
```

Asynchronous sample:

```C# Snippet:AgentsCodeInterpreterFileAttachment_Step5_Cleanup_Async
await client.Files.DeleteFileAsync(uploadedAgentFile.Id);
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);
```
