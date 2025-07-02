# Sample using agents with functions and streaming in Azure.AI.Agents

This sample demonstrates how to use agents with local C# functions and streaming capabilities in the Azure.AI.Agents library. It covers defining functions, creating an agent with these functions, interacting with the agent in a streaming manner, and handling tool calls by executing the corresponding C# functions.

1. Set up configuration, create an agent client. This step includes all necessary `using` directives.

    ```C# Snippet:LocalFuncStream_Step1_CommonSetup
    using Azure.AI.Agents.Persistent;
    using Azure.Identity;
    using Microsoft.Extensions.Configuration;
    using System.ClientModel;
    using System.Text.Json;

    IConfigurationRoot configuration = new ConfigurationBuilder()
        .SetBasePath(AppContext.BaseDirectory)
        .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
        .Build();

    var projectEndpoint = configuration["ProjectEndpoint"];
    var modelDeploymentName = configuration["ModelDeploymentName"];
    PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());
    ```

2. Define the function tools. These include examples of functions with no parameters, a single required parameter, and one required and one optional parameter.

    ```C# Snippet:LocalFuncStream_Step2_DefineFunctionTools
    string GetUserFavoriteCity() => "Seattle, WA";
    FunctionToolDefinition getUserFavoriteCityTool = new("getUserFavoriteCity", "Gets the user's favorite city.");

    string GetCityNickname(string location) => location switch
    {
        "Seattle, WA" => "The Emerald City",
        _ => throw new NotImplementedException(),
    };
    FunctionToolDefinition getCityNicknameTool = new(
        name: "getCityNickname",
        description: "Gets the nickname of a city, e.g. 'LA' for 'Los Angeles, CA'.",
        parameters: BinaryData.FromObjectAsJson(
            new
            {
                Type = "object",
                Properties = new
                {
                    Location = new
                    {
                        Type = "string",
                        Description = "The city and state, e.g. San Francisco, CA",
                    },
                },
                Required = new[] { "location" },
            },
            new JsonSerializerOptions() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));

    string GetWeatherAtLocation(string location, string temperatureUnit = "f") => location switch
    {
        "Seattle, WA" => temperatureUnit == "f" ? "70f" : "21c",
        _ => throw new NotImplementedException()
    };
    FunctionToolDefinition getCurrentWeatherAtLocationTool = new(
        name: "getCurrentWeatherAtLocation",
        description: "Gets the current weather at a provided location.",
        parameters: BinaryData.FromObjectAsJson(
            new
            {
                Type = "object",
                Properties = new
                {
                    Location = new
                    {
                        Type = "string",
                        Description = "The city and state, e.g. San Francisco, CA",
                    },
                    Unit = new
                    {
                        Type = "string",
                        Enum = new[] { "c", "f" },
                    },
                },
                Required = new[] { "location" },
            },
            new JsonSerializerOptions() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));
    ```

3. Create the function `GetResolvedToolOutput`. This function is responsible for calling the appropriate local C# function based on the function name provided by the agent and returning the result as a `ToolOutput`.

    ```C# Snippet:LocalFuncStream_Step3_ToolOutputResolver
    ToolOutput GetResolvedToolOutput(string functionName, string toolCallId, string functionArguments)
    {
        if (functionName == getUserFavoriteCityTool.Name)
        {
            return new ToolOutput(toolCallId, GetUserFavoriteCity());
        }
        using JsonDocument argumentsJson = JsonDocument.Parse(functionArguments);
        if (functionName == getCityNicknameTool.Name)
        {
            string locationArgument = argumentsJson.RootElement.GetProperty("location").GetString();
            return new ToolOutput(toolCallId, GetCityNickname(locationArgument));
        }
        if (functionName == getCurrentWeatherAtLocationTool.Name)
        {
            string locationArgument = argumentsJson.RootElement.GetProperty("location").GetString();
            if (argumentsJson.RootElement.TryGetProperty("unit", out JsonElement unitElement))
            {
                string unitArgument = unitElement.GetString();
                return new ToolOutput(toolCallId, GetWeatherAtLocation(locationArgument, unitArgument));
            }
            return new ToolOutput(toolCallId, GetWeatherAtLocation(locationArgument));
        }
        return null;
    }
    ```

4. Create an agent, providing the function tool definitions created in the previous step.

    Synchronous sample:

    ```C# Snippet:LocalFuncStream_Step4_CreateAgentSync
    PersistentAgent agent = client.Administration.CreateAgent(
        model: modelDeploymentName,
        name: "SDK Test Agent - Functions",
        instructions: "You are a weather bot. Use the provided functions to help answer questions. "
            + "Customize your responses to the user's preferences as much as possible and use friendly "
            + "nicknames for cities whenever possible.",
        tools: [getUserFavoriteCityTool, getCityNicknameTool, getCurrentWeatherAtLocationTool]);
    ```

    Asynchronous sample:

    ```C# Snippet:LocalFuncStream_Step4_CreateAgentAsync
    PersistentAgent agent = await client.Administration.CreateAgentAsync(
        model: modelDeploymentName,
        name: "SDK Test Agent - Functions",
            instructions: "You are a weather bot. Use the provided functions to help answer questions. "
                + "Customize your responses to the user's preferences as much as possible and use friendly "
                + "nicknames for cities whenever possible.",
        tools: [getUserFavoriteCityTool, getCityNicknameTool, getCurrentWeatherAtLocationTool]);
    ```

5. Create a new agent thread and add an initial user message to it.

    Synchronous sample:

    ```C# Snippet:LocalFuncStream_Step5_CreateThreadMessageSync
    PersistentAgentThread thread = client.Threads.CreateThread();

    client.Messages.CreateMessage(
        thread.Id,
        MessageRole.User,
        "What's the weather like in my favorite city?");
    ```

    Asynchronous sample:

    ```C# Snippet:LocalFuncStream_Step5_CreateThreadMessageAsync
    PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

    await client.Messages.CreateMessageAsync(
        thread.Id,
        MessageRole.User,
        "What's the weather like in my favorite city?");
    ```

6. Create a streaming run for the thread and agent. Iterate through the streaming updates. If a `RequiredActionUpdate` is received, resolve the tool output and add it to a list. If a `MessageContentUpdate` is received, print the text. After processing updates in the current stream, if any tool outputs were collected, submit them back to the service to continue the run.

    Synchronous sample:

    ```C# Snippet:LocalFuncStream_Step6_StreamingRunSync
    List<ToolOutput> toolOutputs = [];
    ThreadRun streamRun = null!;
    CollectionResult<StreamingUpdate> stream = client.Runs.CreateRunStreaming(thread.Id, agent.Id);
    do
    {
        toolOutputs.Clear();
        foreach (StreamingUpdate streamingUpdate in stream)
        {
            if (streamingUpdate is RequiredActionUpdate submitToolOutputsUpdate)
            {
                RequiredActionUpdate newActionUpdate = submitToolOutputsUpdate;
                toolOutputs.Add(
                    GetResolvedToolOutput(
                        newActionUpdate.FunctionName,
                        newActionUpdate.ToolCallId,
                        newActionUpdate.FunctionArguments
                ));
                streamRun = submitToolOutputsUpdate.Value;
            }
            else if (streamingUpdate is MessageContentUpdate contentUpdate)
            {
                Console.Write($"{contentUpdate?.Text}");
            }
        }
        if (toolOutputs.Count > 0)
        {
            stream = client.Runs.SubmitToolOutputsToStream(streamRun, toolOutputs);
        }
    }
    while (toolOutputs.Count > 0);
    ```

    Asynchronous sample:

    ```C# Snippet:LocalFuncStream_Step6_StreamingRunAsync
    List<ToolOutput> toolOutputs = [];
    ThreadRun run = null!;
    AsyncCollectionResult<StreamingUpdate> stream = client.Runs.CreateRunStreamingAsync(thread.Id, agent.Id);
    do
    {
        toolOutputs.Clear();
        await foreach (StreamingUpdate streamingUpdate in stream)
        {
            if (streamingUpdate is RequiredActionUpdate submitToolOutputsUpdate)
            {
                RequiredActionUpdate newActionUpdate = submitToolOutputsUpdate;
                toolOutputs.Add(
                    GetResolvedToolOutput(
                        newActionUpdate.FunctionName,
                        newActionUpdate.ToolCallId,
                        newActionUpdate.FunctionArguments
                ));
                run = submitToolOutputsUpdate.Value;
            }
            else if (streamingUpdate is MessageContentUpdate contentUpdate)
            {
                Console.Write($"{contentUpdate?.Text}");
            }
        }
        if (toolOutputs.Count > 0)
        {
            stream = client.Runs.SubmitToolOutputsToStreamAsync(run, toolOutputs);
        }
    }
    while (toolOutputs.Count > 0);
    ```

7. Finally, clean up the created resources by deleting the thread and the agent.

    Synchronous sample:

    ```C# Snippet:LocalFuncStream_Step7_CleanupSync
    client.Threads.DeleteThread(threadId: thread.Id);
    client.Administration.DeleteAgent(agentId: agent.Id);
    ```

    Asynchronous sample:

    ```C# Snippet:LocalFuncStream_Step7_CleanupAsync
    await client.Threads.DeleteThreadAsync(threadId: thread.Id);
    await client.Administration.DeleteAgentAsync(agentId: agent.Id);
    ```
