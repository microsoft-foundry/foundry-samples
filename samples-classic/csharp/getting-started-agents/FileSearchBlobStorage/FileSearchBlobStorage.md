# Sample enterprise file search with agent in Azure.AI.Agents.

In the enterprise file search, as opposed to regular file search, this sample assumes that user has uploaded the file to Azure Blob Storage and have registered it in the Azure AI Foundry. In the example below we will utilize the asset ID from Azure as a data source for the `VectorStore`.

1. First we need to create agent client and read the environment variables, which will be used in the next steps.
```C# Snippet:AgentsEnterpriseFileSearch_CreateProject

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];
var blobURI = configuration["AzureBlobUri"];

// Create the Agent Client
PersistentAgentsClient agentClient = new(
    projectEndpoint,
    new DefaultAzureCredential(),
    new PersistentAgentsAdministrationClientOptions(
        PersistentAgentsAdministrationClientOptions.ServiceVersion.V2025_05_01
    ));
```

2. To create agent capable of using Enterprise file search, we will create `VectorStoreDataSource` and will supply it to `VectorStore` constructor. The ID of the created vector store will be used in the `FileSearchToolResource` used for agent creation. 
Synchronous sample: 
```C# Snippet:AgentsEnterpriseFileSearch_CreateVectorStore
// Create the vector store used when creating the agent
var ds = new VectorStoreDataSource(
    assetIdentifier: blobURI,
    assetType: VectorStoreDataSourceAssetType.UriAsset
);

VectorStore vectorStore = agentClient.VectorStores.CreateVectorStore(
    name: "sample_vector_store",
    storeConfiguration: new VectorStoreConfiguration(
        dataSources: [ds]
    )
);

FileSearchToolResource fileSearchResource = new([vectorStore.Id], null);

List<ToolDefinition> tools = [new FileSearchToolDefinition()];

// Create the Agent leveraging the FileSearchTool
PersistentAgent agent = agentClient.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are helpful agent.",
    tools: tools,
    toolResources: new ToolResources() 
    { 
        FileSearch = fileSearchResource 
    }
);
```
Asynchronous sample:
```C# Snippet:AgentsEnterpriseFileSearchAsync_CreateVectorStore
// Create the vector store used when creating the agent
var ds = new VectorStoreDataSource(
    assetIdentifier: blobURI,
    assetType: VectorStoreDataSourceAssetType.UriAsset
);

VectorStore vectorStore = await agentClient.VectorStores.CreateVectorStoreAsync(
    name: "sample_vector_store",
    storeConfiguration: new VectorStoreConfiguration(
        dataSources: [ds]
    )
);

FileSearchToolResource fileSearchResource = new([vectorStore.Id], null);

List<ToolDefinition> tools = [new FileSearchToolDefinition()];

// Create the Agent leveraging the FileSearchTool
PersistentAgent agent = await agentClient.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are helpful agent.",
    tools: tools,
    toolResources: new ToolResources()
    {
        FileSearch = fileSearchResource
    }
);
```

3. In this example we will ask a question to the file contents and add it to the thread; we will create run and wait while it will terminate.

Synchronous sample:
```C# Snippet:AgentsEnterpriseFileSearch_CreateThreadMessage
PersistentAgentThread thread = agentClient.Threads.CreateThread();

// Create message and run the agent
ThreadMessage message = agentClient.Messages.CreateMessage(
    threadId: thread.Id,
    role: MessageRole.User,
    content: "What feature does Smart Eyewear offer?"
);
ThreadRun run = agentClient.Runs.CreateRun(thread.Id, agent.Id);

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
```C# Snippet:AgentsEnterpriseFileSearchAsync_CreateThreadMessage
PersistentAgentThread thread = await agentClient.Threads.CreateThreadAsync();

// Create message and run the agent
ThreadMessage message = await agentClient.Messages.CreateMessageAsync(
    threadId: thread.Id,
    role: MessageRole.User,
    content: "What feature does Smart Eyewear offer?"
);
ThreadRun run = await agentClient.Runs.CreateRunAsync(thread.Id, agent.Id);

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

4. When we create `VectorStore`, it ingests the contents of the Azure Blob, provided in the `VectorStoreDataSource` object and associates it with File ID. To provide the file name we will need to get the file name by ID, which in our case will be Azure Resource ID and take its last segment.

Synchronous sample:
```C# Snippet:AgentsEnterpriseFileSearch_EnableMapFileIds
// Build the map of file IDs to file names.
Dictionary<string, string> filesMap = [];

var storeFiles = agentClient.VectorStoreFiles.GetVectorStoreFiles(vectorStore.Id);

// Build the map of file IDs to file names (used in updating messages)
foreach (VectorStoreFile storeFile in storeFiles )
{
    PersistentAgentFileInfo agentFile = agentClient.Files.GetFile(storeFile.Id);
    Uri uriFile = new(agentFile.Filename);
    filesMap.Add(storeFile.Id, uriFile.Segments[uriFile.Segments.Length - 1]);
}

// Helper method for replacing references
static string replaceReferences(Dictionary<string, string> fileIds, string fileID, string placeholder, string text)
{
    if (fileIds.TryGetValue(fileID, out string replacement))
        return text.Replace(placeholder, $" [{replacement}]");
    else
        return text.Replace(placeholder, $" [{fileID}]");
}
```

Asynchronous sample:
```C# Snippet:AgentsEnterpriseFileSearchAsync_EnableMapFileIds
// Build the map of file IDs to file names.
Dictionary<string, string> filesMap = [];

var storeFiles = agentClient.VectorStoreFiles.GetVectorStoreFilesAsync(vectorStore.Id);

// Build the map of file IDs to file names (used in updating messages)
await foreach (VectorStoreFile storeFile in storeFiles)
{
    PersistentAgentFileInfo agentFile = agentClient.Files.GetFile(storeFile.Id);
    Uri uriFile = new(agentFile.Filename);
    filesMap.Add(storeFile.Id, uriFile.Segments[uriFile.Segments.Length - 1]);
}

// Helper method for replacing references
static string replaceReferences(Dictionary<string, string> fileIds, string fileID, string placeholder, string text)
{
    if (fileIds.TryGetValue(fileID, out string replacement))
        return text.Replace(placeholder, $" [{replacement}]");
    else
        return text.Replace(placeholder, $" [{fileID}]");
}

```

5. Print the agent messages to console in chronological order (including formatting URL citations). To properly render the file names we call the `replaceReferences` method to replace reference placeholders by file IDs or by file names.

Synchronous sample:
```C# Snippet:AgentsEnterpriseFileSearch_WriteMessages
// Retrieve all messages from the agent client
Pageable<ThreadMessage> messages = agentClient.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);

foreach (ThreadMessage threadMessage in messages)
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
                        strMessage = replaceReferences(filesMap, pathAnnotation.FileId, pathAnnotation.Text, strMessage);
                    }
                    else if (annotation is MessageTextFileCitationAnnotation citationAnnotation)
                    {
                        strMessage = replaceReferences(filesMap, citationAnnotation.FileId, citationAnnotation.Text, strMessage);
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
```C# Snippet:AgentsEnterpriseFileSearchAsync_WriteMessages
        // Retrieve all messages from the agent client
        AsyncPageable<ThreadMessage> messages = agentClient.Messages.GetMessagesAsync(
            threadId: thread.Id,
            order: ListSortOrder.Ascending
        );

        await foreach (ThreadMessage threadMessage in messages)
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
                                strMessage = replaceReferences(filesMap, pathAnnotation.FileId, pathAnnotation.Text, strMessage);
                            }
                            else if (annotation is MessageTextFileCitationAnnotation citationAnnotation)
                            {
                                strMessage = replaceReferences(filesMap, citationAnnotation.FileId, citationAnnotation.Text, strMessage);
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

6. Finally, we delete all the resources, we have created in this sample.

Synchronous sample:
```C# Snippet:AgentsEnterpriseFileSearch_Cleanup
// Clean up resources
VectorStoreDeletionStatus delTask = agentClient.VectorStores.DeleteVectorStore(vectorStore.Id);
if (delTask.Deleted)
{
    Console.WriteLine($"Deleted vector store {vectorStore.Id}");
}
else
{
    Console.WriteLine($"Unable to delete vector store {vectorStore.Id}");
}
agentClient.Threads.DeleteThread(thread.Id);
agentClient.Administration.DeleteAgent(agent.Id);
```

Asynchronous sample:
```C# Snippet:AgentsEnterpriseFileSearchAsync_Cleanup
// Clean up resources
VectorStoreDeletionStatus delTask = await agentClient.VectorStores.DeleteVectorStoreAsync(vectorStore.Id);
if (delTask.Deleted)
{
    Console.WriteLine($"Deleted vector store {vectorStore.Id}");
}
else
{
    Console.WriteLine($"Unable to delete vector store {vectorStore.Id}");
}
await agentClient.Threads.DeleteThreadAsync(thread.Id);
await agentClient.Administration.DeleteAgentAsync(agent.Id);
```