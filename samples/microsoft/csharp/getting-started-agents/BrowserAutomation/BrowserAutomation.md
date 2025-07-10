# Sample for using Azure Functions with agents in Azure.AI.Agents

## Prerequisites
[Optional Step]
In the appsettings.json, set a value for \"PlaywrightConnectionResourceId\" to ehe connection ID of the Serverless connection containing the details
of the Playwright Workspace browser.
Format: <AI Project resource ID>/connections<Serverless connection name>
- Creating a Playwright Workspace Resource: https://aka.ms/pww/docs/manage-workspaces
- Give the Project Identity a "Contributor" role on the Playwright Workspace resource, or configure a custom role by following these instructions: https://aka.ms/pww/docs/manage-workspace-access
- Generate an Access Token for the Playwright Workspace resource: https://aka.ms/pww/docs/generate-access-token
- Create a serverless connection in the Azure AI Foundry project with the Playwright Workspace Browser endpoint and Access Token. 

## Azure.AI.Agents Sample Code

1. First, we set up the necessary configuration, initialize the `PersistentAgentsClient`, define the tool definition for the Browser Automation tool, and then create the agent. This step includes all necessary `using` directives.

    Common setup:

    ```C# Snippet:BrowserAutomationStep1CommonSetup
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
    ```

    Synchronous sample:

    ```C# Snippet:BrowserAutomationStep1CreateAgentSync
    RequestContent agentRequestContent = RequestContent.Create(BinaryData.FromObjectAsJson(agentPayload));
    Response agentResponse = client.Administration.CreateAgent(content: agentRequestContent);
    PersistentAgent agent = PersistentAgent.FromResponse(agentResponse);
    ```

    Asynchronous sample:

    ```C# Snippet:BrowserAutomationStep1CreateAgentAsync
    RequestContent agentRequestContent = RequestContent.Create(BinaryData.FromObjectAsJson(agentPayload));
    Response agentResponse = await client.Administration.CreateAgentAsync(content: agentRequestContent);
    PersistentAgent agent = PersistentAgent.FromResponse(agentResponse);
    ```

2. Next, we create a new persistent agent thread and add an initial user message to it.

    Synchronous sample:

    ```C# Snippet:BrowserAutomationStep2CreateThreadMessageSync
    PersistentAgentThread thread = client.Threads.CreateThread();

    client.Messages.CreateMessage(
        thread.Id,
        MessageRole.User,
        "Find a popular quinoa salad recipe on Allrecipes with more than 500 reviews and a rating above 4 stars. Create a shopping list of ingredients for this recipe and include the total cooking and preparation time. on https://www.allrecipes.com/"
    );
    ```

    Asynchronous sample:

    ```C# Snippet:BrowserAutomationStep2CreateThreadMessageAsync
    PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

    await client.Messages.CreateMessageAsync(
        thread.Id,
        MessageRole.User,
        "Find a popular quinoa salad recipe on Allrecipes with more than 500 reviews and a rating above 4 stars. Create a shopping list of ingredients for this recipe and include the total cooking and preparation time. on https://www.allrecipes.com/"
    );
    ```

3. Then, we create a run for the agent on the thread and poll its status until it completes or requires action.

    Synchronous sample:

    ```C# Snippet:BrowserAutomationStep3RunAndPollSync
    ThreadRun run = client.Runs.CreateRun(thread.Id, agent.Id);

    do
    {
        Thread.Sleep(TimeSpan.FromMilliseconds(500));
        run = client.Runs.GetRun(thread.Id, run.Id);
    }
    while (run.Status == RunStatus.Queued
        || run.Status == RunStatus.InProgress
        || run.Status == RunStatus.RequiresAction);
    ```

    Asynchronous sample:

    ```C# Snippet:BrowserAutomationStep3RunAndPollAsync
    ThreadRun run = await client.Runs.CreateRunAsync(thread.Id, agent.Id);

    do
    {
        await Task.Delay(TimeSpan.FromMilliseconds(500));
        run = await client.Runs.GetRunAsync(thread.Id, run.Id);
    }
    while (run.Status == RunStatus.Queued
        || run.Status == RunStatus.InProgress
        || run.Status == RunStatus.RequiresAction);
    ```

4. After the run is complete, we retrieve and process the messages from the thread.

    Synchronous sample:

    ```C# Snippet:BrowserAutomationStep4ProcessResultsSync
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
    ```

    Asynchronous sample:

    ```C# Snippet:BrowserAutomationStep4ProcessResultsAsync
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
    ```

5. Finally, we clean up the created resources by deleting the thread and the agent.

    Synchronous sample:

    ```C# Snippet:BrowserAutomationStep5CleanupSync
    client.Threads.DeleteThread(thread.Id);
    client.Administration.DeleteAgent(agent.Id);
    ```

    Asynchronous sample:

    ```C# Snippet:BrowserAutomationStep5CleanupAsync
    await client.Threads.DeleteThreadAsync(thread.Id);
    await client.Administration.DeleteAgentAsync(agent.Id);
    ```
