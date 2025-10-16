using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;

// Load configuration from appsettings.json
IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];

// Create a PersistentAgentsClient
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

string fileName = "sample_file_for_upload.txt";
string fullPath = Path.Combine(AppContext.BaseDirectory, fileName);

// Create a local file for upload
File.WriteAllText(
    path: fullPath,
    contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457.");

// Create a PersistentAgent with a tool.
PersistentAgent agent = await client.Administration.CreateAgentAsync(
    model: modelDeploymentName,
    name: "my-agent",
    instructions: "You are a helpful agent that can help fetch data from files you know about.",
    tools: [new CodeInterpreterToolDefinition()]);

// Upload local file to the agent.
PersistentAgentFileInfo uploadedAgentFile = await client.Files.UploadFileAsync(
    filePath: "sample_file_for_upload.txt",
    purpose: PersistentAgentFilePurpose.Agents);

// Create a message attachment with the uploaded file and tool definition.
MessageAttachment attachment = new(
    fileId: uploadedAgentFile.Id,
    tools: [new CodeInterpreterToolDefinition()]);

// Create a thread.
PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

// Create a message.
await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    content: "Can you give me the documented codes for 'banana' and 'orange'?",
    attachments: [attachment]);

// Start run.
ThreadRun run = await client.Runs.CreateRunAsync(
    thread.Id,
    agent.Id);

// Poll until finished.
do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress);

// Get messages.
AsyncPageable<PersistentThreadMessage> messages = client.Messages.GetMessagesAsync(
    thread.Id,
    order: ListSortOrder.Ascending);

// Print messages.
await foreach (PersistentThreadMessage threadMessage in messages)
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
await client.Files.DeleteFileAsync(uploadedAgentFile.Id);
await client.Threads.DeleteThreadAsync(thread.Id);
await client.Administration.DeleteAgentAsync(agent.Id);