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

PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "Image Understanding Agent",
    instructions: "You are an image-understanding agent. Analyze images and provide textual descriptions."
);

PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

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

await client.Messages.CreateMessageAsync(
    threadId: thread.Id,
    role: MessageRole.User,
    contentBlocks: contentBlocks
);

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

await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);