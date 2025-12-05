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
var openApiSpec = configuration["OpenApiSpec"];
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

OpenApiToolDefinition openApiToolDef = new(
    name: "get_weather",
    description: "Retrieve weather information for a location",
    spec: BinaryData.FromBytes(File.ReadAllBytes(openApiSpec)),
    auth: new OpenApiAnonymousAuthDetails(),
    defaultParams: ["format"]
);

PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "Open API Tool Calling Agent",
    instructions: "You are a helpful agent.",
    tools: [openApiToolDef]
);

PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "What's the weather in Seattle?");

ThreadRun run = client.Runs.CreateRun(
    thread.Id,
    agent.Id);

do
{
    Thread.Sleep(TimeSpan.FromMilliseconds(500));
    run = client.Runs.GetRun(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);

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
        }
    }
}

client.Threads.DeleteThread(threadId: thread.Id);
client.Administration.DeleteAgent(agentId: agent.Id);