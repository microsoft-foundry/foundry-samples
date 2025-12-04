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

PersistentAgentFileInfo uploadedFile = client.Files.UploadFile(
    filePath: filePath,
    purpose: PersistentAgentFilePurpose.Agents
);

PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "File Image Understanding Agent",
    instructions: "Analyze images from internally uploaded files."
);

PersistentAgentThread thread = client.Threads.CreateThread();

var contentBlocks = new List<MessageInputContentBlock>
{
    new MessageInputTextBlock("Here is an uploaded file. Please describe it:"),
    new MessageInputImageFileBlock(new MessageImageFileParam(uploadedFile.Id))
};

client.Messages.CreateMessage(
    threadId: thread.Id,
    role: MessageRole.User,
    contentBlocks: contentBlocks
);

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

client.Files.DeleteFile(uploadedFile.Id);
client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);