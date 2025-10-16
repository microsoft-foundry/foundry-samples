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
// From config get an OpenApiSpec file including path.
var openApiSpec = configuration["OpenApiSpec"];

// Create a PersistentAgentsClient.
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

// Create an OpenApi tool definition.
OpenApiToolDefinition openApiToolDef = new(
    name: "get_weather",
    description: "Retrieve weather information for a location",
    spec: BinaryData.FromBytes(File.ReadAllBytes(openApiSpec)),
    openApiAuthentication: new OpenApiAnonymousAuthDetails(),
    defaultParams: ["format"]
);

// Create a PersistentAgent with tool.
PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "Open API Tool Calling Agent",
    instructions: "You are a helpful agent.",
    tools: [openApiToolDef]
);

// Create a thread.
PersistentAgentThread thread = client.Threads.CreateThread();

// Create a message.
client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "What's the weather in Seattle?");

// Start run.
ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id);

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
    order: ListSortOrder.Ascending);

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