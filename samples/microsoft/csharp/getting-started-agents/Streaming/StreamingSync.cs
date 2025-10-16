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

PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "My Friendly Test Agent",
    instructions: "You politely help with math questions. Use the code interpreter tool when asked to visualize numbers.",
    tools: [new CodeInterpreterToolDefinition()]
);

PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Hi, Agent! Draw a graph for a line with a slope of 4 and y-intercept of 9.");

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

client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);