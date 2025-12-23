using A2A.Client.Configuration;
using A2A.Client.Services;
using A2A.Models;
using A2A.Requests;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Options;
using System.CommandLine;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;




var endpointOption = new Option<Uri>("--endpoint", description: "The service endpoint URI.") { IsRequired = true };
var audienceOption = new Option<string>("--audience", description: "The audience for authentication.") { IsRequired = true };
var apiVersionOption = new Option<string>("--apiVersion", description: "The API version.") { IsRequired = true };
var modelName = new Option<string>("--model", description: "The model deoloyment name.") { IsRequired = true };

var rootCommand = new RootCommand
{
    endpointOption,
    audienceOption,
    apiVersionOption,
    modelName
};


string GetFile([CallerFilePath] string pth = "")
{
    var dirName = Path.GetDirectoryName(pth) ?? "";
    return Path.Combine(dirName, "sample_data/product_info_1.md");
}



rootCommand.SetHandler(async (Uri endpoint, string audience, string apiVersion, string modelName) =>
{
    DefaultAzureCredential tokenProvider = new();
    PersistentAgentsClient client = new(endpoint.ToString(), tokenProvider);
    // Upload file and create vector store.
    var filePath = GetFile();
    PersistentAgentFileInfo uploadedAgentFile = await client.Files.UploadFileAsync(
        filePath: filePath,
        purpose: PersistentAgentFilePurpose.Agents);
    PersistentAgentsVectorStore vectorStore = await client.VectorStores.CreateVectorStoreAsync(
            fileIds: new List<string> { uploadedAgentFile.Id },
            name: "my_vector_store");
    // Create file search tool with resources followed by creating agent.
    FileSearchToolResource fileSearchToolResource = new FileSearchToolResource();
    fileSearchToolResource.VectorStoreIds.Add(vectorStore.Id);
    // Create the agent used for the file search.
    PersistentAgent searchToolAgent = await client.Administration.CreateAgentAsync(
        model: modelName,
        name: "SDK Test Agent - Search",
        instructions: "You are a helpful agent that can help fetch data from files you know about.",
        tools: [new FileSearchToolDefinition()],
        toolResources: new ToolResources() { FileSearch = fileSearchToolResource }
    );


    // The function to be called by an agent.
    string endpointA2A = $"{endpoint}/workflows/a2a/agents/{searchToolAgent.Id}?api-version={apiVersion}";
    async Task<string> GetA2AResponse(string message)
    {
        HttpClient httpClient = new();
        httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {(await tokenProvider.GetTokenAsync(new Azure.Core.TokenRequestContext(new[] { audience }))).Token}");
        A2AProtocolHttpClient client = new(Options.Create<A2AProtocolClientOptions>(new A2AProtocolClientOptions
        {
            Endpoint = new Uri($"{endpoint}/workflows/a2a/agents/{searchToolAgent.Id}?api-version={apiVersion}"),
        }), httpClient);

        // Send request to agent
        var request = new SendTaskRequest()
        {
            Params = new()
            {
                Id = Guid.NewGuid().ToString("N"),
                Message = new()
                {
                    Role = A2A.MessageRole.User,
                    Parts =
                    [
                        new TextPart(message)
                    ]
                }
            }
        };

        // Get the response
        var response = await client.SendTaskAsync(request);

        StringBuilder sbResponse = new();
        foreach (var artifact in response.Result?.Artifacts ?? Enumerable.Empty<Artifact>())
        {
            if (artifact.Parts != null)
            {
                foreach (var part in artifact.Parts.OfType<TextPart>()) sbResponse.Append(part.Text);
            }
        }
        Console.WriteLine(sbResponse.ToString());
        return sbResponse.ToString();
    };

    // Define the specification for the function tool.
    FunctionToolDefinition getA2AResponseTool = new(
        name: "GetA2AResponse",
        description: "Get the information about Contoso products.",
        parameters: BinaryData.FromObjectAsJson(
            new
            {
                Type = "object",
                Properties = new
                {
                    Message = new
                    {
                        Type = "string",
                        Description = "The question to ask about Cotoso product.",
                    },
                },
                Required = new[] { "message" },
            },
            new JsonSerializerOptions() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));

    // The function to wrap function output.
    async System.Threading.Tasks.Task<ToolOutput> GetResolvedToolOutput(RequiredToolCall toolCall)
    {
        if (toolCall is RequiredFunctionToolCall functionToolCall)
        {
            using JsonDocument argumentsJson = JsonDocument.Parse(functionToolCall.Arguments);
            string messageArgument = argumentsJson.RootElement.GetProperty("message").GetString();
            return new ToolOutput(toolCall, await GetA2AResponse(messageArgument));
        }
        return null;
    }

    // Create an agent, using function tool to call file search agent using a2a protocol.
    PersistentAgent agent = await client.Administration.CreateAgentAsync(
        model: modelName,
        name: "SDK Test Agent - Retrieval",
        instructions: "Hello, you are helpful agent. When asked about Contoso project please send the question to the function tool and return the response.",
        tools: [getA2AResponseTool]
    );
    // Create thread.
    PersistentAgentThread thread = await client.Threads.CreateThreadAsync();
    Console.WriteLine($"Created thread {thread.Id}");

    // Create message.
    await client.Messages.CreateMessageAsync(
            thread.Id,
            Azure.AI.Agents.Persistent.MessageRole.User,
            "Hello, what Contoso products do you know?");
    // Create a run
    ThreadRun run = await client.Runs.CreateRunAsync(thread, agent);
    try
    {
        // Wait while the run completes.
        do
        {
            await System.Threading.Tasks.Task.Delay(TimeSpan.FromMilliseconds(500));
            run = await client.Runs.GetRunAsync(thread.Id, run.Id);

            if (run.Status == RunStatus.RequiresAction
                && run.RequiredAction is SubmitToolOutputsAction submitToolOutputsAction)
            {
                List<ToolOutput> toolOutputs = [];
                foreach (RequiredToolCall toolCall in submitToolOutputsAction.ToolCalls)
                {
                    toolOutputs.Add(await GetResolvedToolOutput(toolCall));
                }
                run = await client.Runs.SubmitToolOutputsToRunAsync(run, toolOutputs);
            }
        }
        while (run.Status == RunStatus.Queued
            || run.Status == RunStatus.InProgress);

        // Write out the messages.
        await foreach (PersistentThreadMessage threadMessage in client.Messages.GetMessagesAsync(thread.Id, order: ListSortOrder.Ascending))
        {
            Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");
            foreach (MessageContent contentItem in threadMessage.ContentItems)
            {
                if (contentItem is MessageTextContent textItem)
                {
                    Console.Write(textItem.Text);
                }
                else if (contentItem is MessageImageFileContent imageFileItem)
                {
                    Console.Write($"<image from ID: {imageFileItem.FileId}");
                }
                Console.WriteLine();
            }
        }
    }
    finally
    {
        // Delete thread
        await client.Threads.DeleteThreadAsync(thread.Id);
        // Delete uploaded file.
        await client.Files.DeleteFileAsync(uploadedAgentFile.Id);
        // Delete vector store.
        await client.VectorStores.DeleteVectorStoreAsync(vectorStore.Id);
        // Delete file search agent.
        await client.Administration.DeleteAgentAsync(searchToolAgent.Id);
        // Delete the agent, calling function.
        await client.Administration.DeleteAgentAsync(agent.Id);
    }


}, endpointOption, audienceOption, apiVersionOption, modelName);


return await rootCommand.InvokeAsync(args);