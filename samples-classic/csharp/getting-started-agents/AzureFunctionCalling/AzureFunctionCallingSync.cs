using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using System.Text.Json;

IConfigurationRoot configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .Build();

var projectEndpoint = configuration["ProjectEndpoint"];
var modelDeploymentName = configuration["ModelDeploymentName"];
var storageQueueUri = configuration["StorageQueueURI"];
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

AzureFunctionToolDefinition azureFnTool = new(
    name: "foo",
    description: "Get answers from the foo bot.",
    inputBinding: new AzureFunctionBinding(
        new AzureFunctionStorageQueue(
            queueName: "azure-function-foo-input",
            storageServiceEndpoint: storageQueueUri
        )
    ),
    outputBinding: new AzureFunctionBinding(
        new AzureFunctionStorageQueue(
            queueName: "azure-function-tool-output",
            storageServiceEndpoint: storageQueueUri
        )
    ),
    parameters: BinaryData.FromObjectAsJson(
            new
            {
                Type = "object",
                Properties = new
                {
                    query = new
                    {
                        Type = "string",
                        Description = "The question to ask.",
                    },
                    outputqueueuri = new
                    {
                        Type = "string",
                        Description = "The full output queue uri."
                    }
                },
            },
        new JsonSerializerOptions() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }
    )
);

PersistentAgent agent = client.Administration.CreateAgent(
    model: modelDeploymentName,
    name: "azure-function-agent-foo",
    instructions: "You are a helpful support agent. Use the provided function any "
    + "time the prompt contains the string 'What would foo say?'. When you invoke "
    + "the function, ALWAYS specify the output queue uri parameter as "
    + $"'{storageQueueUri}/azure-function-tool-output'. Always responds with "
    + "\"Foo says\" and then the response from the tool.",
    tools: [azureFnTool]
);

PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "What is the most prevalent element in the universe? What would foo say?");

ThreadRun run = client.Runs.CreateRun(thread.Id, agent.Id);

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
    order: ListSortOrder.Ascending
);

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

client.Threads.DeleteThread(thread.Id);
client.Administration.DeleteAgent(agent.Id);