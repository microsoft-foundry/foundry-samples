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

PersistentAgentFileInfo uploadedFile = await client.Files.UploadFileAsync(
    filePath: filePath,
    purpose: PersistentAgentFilePurpose.Agents
);

PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "File Image Understanding Agent",
    instructions: "Analyze images from internally uploaded files."
);

PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

var contentBlocks = new List<MessageInputContentBlock>
{
    new MessageInputTextBlock("Here is an uploaded file. Please describe it:"),
    new MessageInputImageFileBlock(new MessageImageFileParam(uploadedFile.Id))
};

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    contentBlocks: contentBlocks);

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

await client.Files.DeleteFileAsync(uploadedFile.Id);
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);