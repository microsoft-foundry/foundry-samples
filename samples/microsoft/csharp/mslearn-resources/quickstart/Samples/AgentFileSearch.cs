// <create_filesearch_agent>

using Azure;
using Azure.Identity;
using Azure.AI.Agents.Persistent;

// Creating the Client for agents and vector stores
var projectEndpoint = System.Environment.GetEnvironmentVariable("AZURE_AI_ENDPOINT");
var modelDeploymentName = System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL");
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

PersistentAgentFileInfo uploadedAgentFile = client.Files.UploadFile(
    filePath: "product_info_1.md",
    purpose: PersistentAgentFilePurpose.Agents);

// Create a vector store with the file and wait for it to be processed.
// If you do not specify a vector store, create_message will create a vector store with a default expiration policy of seven days after they were last active

Dictionary<string, string> fileIds = new()
{
    { uploadedAgentFile.Id, uploadedAgentFile.Filename }
};

PersistentAgentsVectorStore vectorStore = client.VectorStores.CreateVectorStore(
    name: "my_vector_store");

// Add file ID to vector store.
VectorStoreFile vctFile = client.VectorStores.CreateVectorStoreFile(
    vectorStoreId: vectorStore.Id,
    fileId: uploadedAgentFile.Id
);

Console.WriteLine($"Added file to vector store. The id file in the vector store is {vctFile.Id}.");

FileSearchToolResource fileSearchToolResource = new FileSearchToolResource();
fileSearchToolResource.VectorStoreIds.Add(vectorStore.Id);

// Create an Agent with toolResources and process Agent run
PersistentAgent agent = client.Administration.CreateAgent(
        model: modelDeploymentName,
        name: "SDK Test Agent - Retrieval",
        instructions: "You are a helpful agent that can help fetch data from files you know about.",
        tools: new List<ToolDefinition> { new FileSearchToolDefinition() },
        toolResources: new ToolResources() { FileSearch = fileSearchToolResource });

// Create thread for communication
PersistentAgentThread thread = client.Threads.CreateThread();

// Create message to thread
PersistentThreadMessage messageResponse = client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Can you give me information on how to mount the product?");

// Run the Agent
ThreadRun run = client.Runs.CreateRun(thread, agent);

// Wait for the run to complete
// This is a blocking call, so it will wait until the run is completed
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Create a list of messages in the thread and write them to the console.
Pageable<PersistentThreadMessage> messages = client.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
);
WriteMessages(messages, fileIds);

// Delete the thread and agent after use
client.VectorStores.DeleteVectorStore(vectorStore.Id);
client.Files.DeleteFile(uploadedAgentFile.Id);
client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);

// Helper method to write messages to the console
static void WriteMessages(IEnumerable<PersistentThreadMessage> messages, Dictionary<string, string> fileIds)
{
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
}

// Helper method to replace file references in the text
static string replaceReferences(Dictionary<string, string> fileIds, string fileID, string placeholder, string text)
{
    if (fileIds.TryGetValue(fileID, out string replacement))
        return text.Replace(placeholder, $" [{replacement}]");
    else
        return text.Replace(placeholder, $" [{fileID}]");
}

// </create_filesearch_agent>