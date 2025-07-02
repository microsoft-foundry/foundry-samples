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
Response agentResponse = await client.Administration.CreateAgentAsync(content: agentRequestContent);
PersistentAgent agent = PersistentAgent.FromResponse(agentResponse);

PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

await client.Messages.CreateMessageAsync(
    thread.Id,
    MessageRole.User,
    "Find a popular quinoa salad recipe on Allrecipes with more than 500 reviews and a rating above 4 stars. Create a shopping list of ingredients for this recipe and include the total cooking and preparation time. on https://www.allrecipes.com/"
);

ThreadRun run = await client.Runs.CreateRunAsync(thread.Id, agent.Id);

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
    order: ListSortOrder.Ascending
);

await foreach (ThreadMessage threadMessage in messages)
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

await client.Threads.DeleteThreadAsync(thread.Id);
await client.Administration.DeleteAgentAsync(agent.Id);
