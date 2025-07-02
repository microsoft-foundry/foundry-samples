# Sample using agents with Image URL as an input in Azure.AI.Agents

This sample demonstrates examples of sending an image URL (along with optional text) as a structured content block in a single message. The examples shows how to create an agent, open a thread,  post content blocks combining text and image inputs, and then run the agent to see how it interprets the multimedia input.

1. First we need to set up configuration, create an agent client, and create an agent. This step includes all necessary `using` directives.

```C# Snippet:AgentImageUrlSetupCommon
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

```C# Snippet:AgentImageUrlCreateAgentSync
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "Image Understanding Agent",
    instructions: "You are an image-understanding agent. Analyze images and provide textual descriptions."
);
```

Asynchronous sample:

```C# Snippet:AgentImageUrlCreateAgentAsync
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "Image Understanding Agent",
    instructions: "You are an image-understanding agent. Analyze images and provide textual descriptions."
);
```

2. Next, create a thread.

Synchronous sample:

```C# Snippet:AgentImageUrlCreateThreadSync
PersistentAgentThread thread = client.Threads.CreateThread();
```

Asynchronous sample:

```C# Snippet:AgentImageUrlCreateThreadAsync
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();
```

3. Then, create a message using multiple content blocks. Here we combine a short text and an image URL in a single user message.

```C# Snippet:AgentImageUrlCreateMessageCommon
MessageImageUrlParam imageUrlParam = new(
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
)
{
    Detail = ImageDetailLevel.High
};

var contentBlocks = new List<MessageInputContentBlock>
{
    new MessageInputTextBlock("Could you describe this image?"),
    new MessageInputImageUrlBlock(imageUrlParam)
};
```

Synchronous sample:

```C# Snippet:AgentImageUrlCreateMessageSync
client.Messages.CreateMessage(
    threadId: thread.Id,
    role: MessageRole.User,
    contentBlocks: contentBlocks
);
```

Asynchronous sample:

```C# Snippet:AgentImageUrlCreateMessageAsync
await client.Messages.CreateMessageAsync(
    threadId: thread.Id,
    role: MessageRole.User,
    contentBlocks: contentBlocks
);
```

4. Now, create and run the agent against the thread that now has an image to analyze, and wait for the run to complete.

Synchronous sample:

```C# Snippet:AgentImageUrlCreateRunAndPollSync
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
```

Asynchronous sample:

```C# Snippet:AgentImageUrlCreateRunAndPollAsync
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
```

5. After the run completes, retrieve all messages (including how the agent responds) and print their contents.

Synchronous sample:

```C# Snippet:AgentImageUrlReviewMessagesSync
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

```C# Snippet:AgentImageUrlReviewMessagesAsync
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

            case MessageImageFileContent fileItem:
                Console.WriteLine($"[{threadMessage.Role}]: Image File (internal ID): {fileItem.FileId}");
                break;
        }
    }
}
```

6. Finally, delete all the resources created in this sample.

Synchronous sample:

```C# Snippet:AgentImageUrlCleanupSync
client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);
```

Asynchronous sample:

```C# Snippet:AgentImageUrlCleanupAsync
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);
```
