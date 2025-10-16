using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;

// Load configuration from appsettings.json.
IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];
// Azure Blob Storage URI for the vector store data source.
var blobURI = configuration["AzureBlobUri"];

// Create a PersistentAgentsClient.
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

// Tool definitions.
List<ToolDefinition> tools = [new CodeInterpreterToolDefinition()];

// Create a PersistentAgent with tools.
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are helpful agent.",
    tools: tools
);

// Create a thread.
PersistentAgentThread thread = client.Threads.CreateThread();

// Create a vector store data source attachment.
var vectorStoreDataSource = new VectorStoreDataSource(
    assetIdentifier: blobURI,
    assetType: VectorStoreDataSourceAssetType.UriAsset
);

// Create a message attachment with the vector store data source and tools.
var attachment = new MessageAttachment(
    ds: vectorStoreDataSource,
    tools: tools
);

// Create a message and include the attachment.
client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    content: "What does the attachment say?",
    attachments: [attachment]
);

// Start run.
ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id
);

// Poll until finished.
do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Get messages.
Pageable<PersistentThreadMessage> messages = client.Messages.GetMessages(
    thread.Id,
    order: ListSortOrder.Ascending
);

// Print messages.
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

// Cleanup resources
client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);