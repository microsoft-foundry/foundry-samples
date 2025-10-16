# Sample using agents with streaming in Azure.AI.Agents.Persistent

In this example we will demonstrate the agent streaming support.

## Initialize

First we need to create agent client and read the environment variables that will be used in the next steps.

```csharp
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

We will create agent with the Interpreter tool support. It is needed to allow for writing mathematical formulas in [LaTeX](https://en.wikipedia.org/wiki/LaTeX) format.

Synchronous sample:

```csharp
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "My Friendly Test Agent",
    instructions: "You politely help with math questions. Use the code interpreter tool when asked to visualize numbers.",
    tools: [new CodeInterpreterToolDefinition()]
);
```

Asynchronous sample:

```csharp
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "My Friendly Test Agent",
    instructions: "You politely help with math questions. Use the code interpreter tool when asked to visualize numbers.",
    tools: [new CodeInterpreterToolDefinition()]
);
```

## Threads and Messages

Create thread with the message.

Synchronous sample:

```csharp
PersistentAgentThread thread = client.Threads.CreateThread();

PersistentThreadMessage message = client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Hi, Agent! Draw a graph for a line with a slope of 4 and y-intercept of 9.");
```

Asynchronous sample:

```csharp
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

PersistentThreadMessage message = await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "Hi, Agent! Draw a graph for a line with a slope of 4 and y-intercept of 9.");
```

## Streaming Updates

Read the output from the stream.

Synchronous sample:

```csharp
foreach (StreamingUpdate streamingUpdate in client.Runs.CreateRunStreaming(thread.Id, agent.Id))
{
    switch (streamingUpdate)
    {
        case MessageContentUpdate messageContentUpdate:
            Console.Write(messageContentUpdate.Text);
            if (messageContentUpdate.ImageFileId is not null)
            {
                Console.WriteLine($"[Image content file ID: {messageContentUpdate.ImageFileId}]");
                BinaryData imageContent = client.Files.GetFileContent(messageContentUpdate.ImageFileId);
                string tempFilePath = Path.Combine(AppContext.BaseDirectory, $"{Guid.NewGuid()}.png");
                File.WriteAllBytes(tempFilePath, imageContent.ToArray());

                ProcessStartInfo psi = new()
                {
                    FileName = tempFilePath,
                    UseShellExecute = true
                };
                Process.Start(psi);
                
                client.Files.DeleteFile(messageContentUpdate.ImageFileId);
            }
            break;
        case MessageStatusUpdate messageStatusUpdate:
            Console.WriteLine($"[Kind]: {messageStatusUpdate.UpdateKind}");
            break;
    }
}
```

Asynchronous sample:

```csharp
await foreach (StreamingUpdate streamingUpdate in client.Runs.CreateRunStreamingAsync(thread.Id, agent.Id))
{
    switch (streamingUpdate)
    {
        case MessageContentUpdate messageContentUpdate:
            Console.Write(messageContentUpdate.Text);
            if (messageContentUpdate.ImageFileId is not null)
            {
                Console.WriteLine($"[Image content file ID: {messageContentUpdate.ImageFileId}]");
                BinaryData imageContent = await client.Files.GetFileContentAsync(messageContentUpdate.ImageFileId);
                string tempFilePath = Path.Combine(AppContext.BaseDirectory, $"{Guid.NewGuid()}.png");
                File.WriteAllBytes(tempFilePath, imageContent.ToArray());

                ProcessStartInfo psi = new()
                {
                    FileName = tempFilePath,
                    UseShellExecute = true
                };
                Process.Start(psi);

                await client.Files.DeleteFileAsync(messageContentUpdate.ImageFileId);
            }
            break;
        case MessageStatusUpdate messageStatusUpdate:
            Console.WriteLine($"[Kind]: {messageStatusUpdate.UpdateKind}");
            break;
    }
}
```

## Cleanup Resources

Finally, we delete all the resources we have created in this sample.

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
