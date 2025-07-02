using Azure;
using Azure.Core;
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
var playwrightConnectionResourceId = configuration["PlaywrightConnectionResourceId"];
PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

object browserAutomationToolDefinition = null;
if (string.IsNullOrWhitespace(playwrightConnectionResourceId))
{
    browserAutomationToolDefinition = new(
        type: "browser_automation",
    );
}
else
{
    browserAutomationToolDefinition = new(
        type: "browser_automation",
        browser_automation: new(
            connection: new(
                id: playwrightConnectionResourceId,
            ),
        ),
    );
}

object agentPayload = new(
    name: "Browser Automation Tool Demo Agent",
    description: "A simple agent that uses the browser automation tool.",
    model: modelDeploymentName,
    instructions: "You are an agent to help me with browser automation tasks. "
    + "You can answer questions, provide information, and assist with various tasks "
    + "related to web browsing using the browser_automation tool available to you.",
    tools: new[]
    {
        browserAutomationToolDefinition
    },
);

RequestContent agentRequestContent = RequestContent.Create(BinaryData.FromObjectAsJson(agentPayload));
Response agentResponse = client.Administration.CreateAgent(content: agentRequestContent);
PersistentAgent agent = PersistentAgent.FromResponse(agentResponse);

PersistentAgentThread thread = client.Threads.CreateThread();

client.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Find a popular quinoa salad recipe on Allrecipes with more than 500 reviews and a rating above 4 stars. Create a shopping list of ingredients for this recipe and include the total cooking and preparation time. on https://www.allrecipes.com/"
);

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
