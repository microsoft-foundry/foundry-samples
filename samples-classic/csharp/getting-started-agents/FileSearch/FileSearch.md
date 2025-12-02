# Sample file search with agent in Azure.AI.Agents.

In this example we will create the local file, upload it to the newly created `PersistentAgentsVectorStore`, which will be used in the file search.

1. First we need to create agent client and read the environment variables that will be used in the next steps.
```C# Snippet:AgentsFileSearch_CreateClient
var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];

// Create the Agent Client
PersistentAgentsClient agentClient = new(projectEndpoint, new DefaultAzureCredential());
```

2. Now we will create a local file and upload it to the data store.

Synchronous sample:
```C# Snippet:AgentsFileSearch_UploadAgentFiles
// Create a local sample file
System.IO.File.WriteAllText(
    path: "sample_file_for_upload.txt",
    contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457."
);

// Upload local sample file to the agent
PersistentAgentFileInfo uploadedAgentFile = agentClient.Files.UploadFile(
    filePath: "sample_file_for_upload.txt",
    purpose: PersistentAgentFilePurpose.Agents
);

// Setup dictionary with list of File IDs for the vector store
Dictionary<string, string> fileIds = new()
{
    { uploadedAgentFile.Id, uploadedAgentFile.Filename }
};
```

Asynchronous sample:
```C# Snippet:AgentsFileSearchAsync_UploadAgentFiles
// Create a local sample file
await System.IO.File.WriteAllTextAsync(
    path: "sample_file_for_upload.txt",
    contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457."
);

// Upload local sample file to the agent
PersistentAgentFileInfo uploadedAgentFile = await agentClient.Files.UploadFileAsync(
    filePath: "sample_file_for_upload.txt",
    purpose: PersistentAgentFilePurpose.Agents
);

// Setup dictionary with list of File IDs for the vector store
Dictionary<string, string> fileIds = new()
{
    { uploadedAgentFile.Id, uploadedAgentFile.Filename }
};
```

3.  To create agent capable of using file search, we will create `PersistentAgentsVectorStore`, with the ID of uploaded file.

Synchronous sample:
```C# Snippet:AgentsFileSearch_CreateVectorStore
// Create a vector store with the file and wait for it to be processed.
// If you do not specify a vector store, CreateMessage will create a vector
// store with a default expiration policy of seven days after they were last active
PersistentAgentsVectorStore vectorStore = agentClient.VectorStores.CreateVectorStore(
    fileIds: new List<string> { uploadedAgentFile.Id },
    name: "my_vector_store");

```

Asynchronous sample:
```C# Snippet:AgentsFileSearchAsync_CreateVectorStore
// Create a vector store with the file and wait for it to be processed.
// If you do not specify a vector store, CreateMessage will create a vector
// store with a default expiration policy of seven days after they were last active
PersistentAgentsVectorStore vectorStore = await agentClient.VectorStores.CreateVectorStoreAsync(
    fileIds: new List<string> { uploadedAgentFile.Id },
    name: "my_vector_store");

```

4.  Create the `FileSearchToolResource` using the Id of the created vector store and then create the agent

Synchronous sample:
```C# Snippet:AgentsFileSearch_CreateAgentWithFiles
// Create tool definition for File Search
FileSearchToolResource fileSearchToolResource = new FileSearchToolResource();
fileSearchToolResource.VectorStoreIds.Add(vectorStore.Id);

// Create an agent with Tools and Tool Resources
PersistentAgent agent = agentClient.Administration.CreateAgent(
        model: modelDeploymentName,
        name: "SDK Test Agent - Retrieval",
        instructions: "You are a helpful agent that can help fetch data from files you know about.",
        tools: new List<ToolDefinition> { new FileSearchToolDefinition() },
        toolResources: new ToolResources() { FileSearch = fileSearchToolResource });
```

Asynchronous sample:
```C# Snippet:AgentsFileSearchAsync_CreateAgentWithFiles
// Create tool definition for File Search
FileSearchToolResource fileSearchToolResource = new FileSearchToolResource();
fileSearchToolResource.VectorStoreIds.Add(vectorStore.Id);

// Create an agent with Tools and Tool Resources
PersistentAgent agent = await agentClient.Administration.CreateAgentAsync(
        model: modelDeploymentName,
        name: "SDK Test Agent - Retrieval",
        instructions: "You are a helpful agent that can help fetch data from files you know about.",
        tools: new List<ToolDefinition> { new FileSearchToolDefinition() },
        toolResources: new ToolResources() { FileSearch = fileSearchToolResource });
```

5. Now we will create the thread, add the message containing a question for agent related to the file contents and start the run.

Synchronous sample:
```C# Snippet:AgentsFileSearch_CreateThreadAndRun
// Create the agent thread for communication
PersistentAgentThread thread = agentClient.Threads.CreateThread();

// Create message and run the agent
PersistentThreadMessage messageResponse = agentClient.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Can you give me the documented codes for 'banana' and 'orange'?");

ThreadRun run = agentClient.Runs.CreateRun(thread, agent);

// Wait for the agent to finish running
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = agentClient.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}

```

Asynchronous sample:
```C# Snippet:AgentsFileSearchAsync_CreateThreadAndRun
// Create the agent thread for communication
PersistentAgentThread thread = await agentClient.Threads.CreateThreadAsync();

// Create message and run the agent
PersistentThreadMessage messageResponse = await agentClient.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "Can you give me the documented codes for 'banana' and 'orange'?");

ThreadRun run = await agentClient.Runs.CreateRunAsync(thread, agent);

// Wait for the agent to finish running
do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await agentClient.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Confirm that the run completed successfully
if (run.Status != RunStatus.Completed)
{
    throw new Exception("Run did not complete successfully, error: " + run.LastError?.Message);
}

```

6. Print the agent messages to console in chronological order (including formatting file citations).

Synchronous sample:
```C# Snippet:AgentsFileSearch_Print
// Retrieve all messages from the agent client
Pageable<PersistentThreadMessage> messages = agentClient.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

// Helper method for replacing references
static string replaceReferences(Dictionary<string, string> fileIds, string fileID, string placeholder, string text)
{
    if (fileIds.TryGetValue(fileID, out string replacement))
        return text.Replace(placeholder, $" [{replacement}]");
    else
        return text.Replace(placeholder, $" [{fileID}]");
}

// Process messages in order
foreach (PersistentThreadMessage threadMessage in messages)
{
    Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");

    foreach (MessageContent contentItem in threadMessage.ContentItems)
    {
        if (contentItem is MessageTextContent textItem)
        {
            if (threadMessage.Role == MessageRole.Agent && textItem.Annotations.Count > 0)
            {
                string strMessage = textItem.Text;

                // If we file path or file citation annotations - rewrite the 'source' FileId with the file name
                foreach (MessageTextAnnotation annotation in textItem.Annotations)
                {
                    if (annotation is MessageTextFilePathAnnotation pathAnnotation)
                    {
                        strMessage = replaceReferences(fileIds, pathAnnotation.FileId, pathAnnotation.Text, strMessage);
                    }
                    else if (annotation is MessageTextFileCitationAnnotation citationAnnotation)
                    {
                        strMessage = replaceReferences(fileIds, citationAnnotation.FileId, citationAnnotation.Text, strMessage);
                    }
                }
                Console.Write(strMessage);
            }
            else
            {
                Console.Write(textItem.Text);
            }
        }
        else if (contentItem is MessageImageFileContent imageFileItem)
        {
            Console.Write($"<image from ID: {imageFileItem.FileId}");
        }
        Console.WriteLine();
    }
}

```

Asynchronous sample:
```C# Snippet:AgentsFileSearchAsync_Print
// Retrieve all messages from the agent client
AsyncPageable<PersistentThreadMessage> messages = agentClient.Messages.GetMessagesAsync(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

// Helper method for replacing references
static string replaceReferences(Dictionary<string, string> fileIds, string fileID, string placeholder, string text)
{
    if (fileIds.TryGetValue(fileID, out string replacement))
        return text.Replace(placeholder, $" [{replacement}]");
    else
        return text.Replace(placeholder, $" [{fileID}]");
}

// Process messages in order
await foreach (PersistentThreadMessage threadMessage in messages)
{
    Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");

    foreach (MessageContent contentItem in threadMessage.ContentItems)
    {
        if (contentItem is MessageTextContent textItem)
        {
            if (threadMessage.Role == MessageRole.Agent && textItem.Annotations.Count > 0)
            {
                string strMessage = textItem.Text;

                // If we file path or file citation annotations - rewrite the 'source' FileId with the file name
                foreach (MessageTextAnnotation annotation in textItem.Annotations)
                {
                    if (annotation is MessageTextFilePathAnnotation pathAnnotation)
                    {
                        strMessage = replaceReferences(fileIds, pathAnnotation.FileId, pathAnnotation.Text, strMessage);
                    }
                    else if (annotation is MessageTextFileCitationAnnotation citationAnnotation)
                    {
                        strMessage = replaceReferences(fileIds, citationAnnotation.FileId, citationAnnotation.Text, strMessage);
                    }
                }
                Console.Write(strMessage);
            }
            else
            {
                Console.Write(textItem.Text);
            }
        }
        else if (contentItem is MessageImageFileContent imageFileItem)
        {
            Console.Write($"<image from ID: {imageFileItem.FileId}");
        }
        Console.WriteLine();
    }
}
```

7. Finally, we delete all the resources created in this sample.

Synchronous sample:
```C# Snippet:AgentsFileSearch_Cleanup
// Clean up resources
agentClient.VectorStores.DeleteVectorStore(vectorStore.Id);
agentClient.Files.DeleteFile(uploadedAgentFile.Id);
agentClient.Threads.DeleteThread(thread.Id);
agentClient.Administration.DeleteAgent(agent.Id);
```

Asynchronous sample:
```C# Snippet:AgentsFileSearchAsync_Cleanup
// Clean up resources
await agentClient.VectorStores.DeleteVectorStoreAsync(vectorStore.Id);
await agentClient.Files.DeleteFileAsync(uploadedAgentFile.Id);
await agentClient.Threads.DeleteThreadAsync(thread.Id);
await agentClient.Administration.DeleteAgentAsync(agent.Id);
```