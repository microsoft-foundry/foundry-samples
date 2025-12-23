using A2A;
using A2A.Client.Configuration;
using A2A.Client.Services;
using A2A.Models;
using A2A.Requests;
using Azure.Identity;
using System.CommandLine;
using Azure.AI.Projects;
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.Options;


var endpointOption = new Option<Uri>("--endpoint", description: "The service endpoint URI.") { IsRequired = true };
var audienceOption = new Option<string>("--audience", description: "The audience for authentication.") { IsRequired = true };
var apiVersionOption = new Option<string>("--apiVersion", description: "The API version.") { IsRequired = true };

var rootCommand = new RootCommand
{
    endpointOption,
    audienceOption,
    apiVersionOption
};

rootCommand.SetHandler(async (Uri endpoint, string audience, string apiVersion) =>
{
    var tokens = new DefaultAzureCredential();
    var agent = new AIProjectClient(endpoint, tokens).GetPersistentAgentsClient();

    // create the single agent
    var simpleAgent = await agent.Administration.CreateAgentAsync
    (
        model: "gpt-4o",
        name: "Foundry",
        instructions: "You are an expert with Azure AI Foundry. Answer questions about it."

    );

    Console.WriteLine($"Created agent: {simpleAgent.Value.Id}");

    // a2a setup for azure foundry agents
    try
    {
        var httpClient = new HttpClient();
        Console.WriteLine($"{endpoint}/workflows/a2a/agents/{simpleAgent.Value.Id}?api-version={apiVersion}");
        httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {(await tokens.GetTokenAsync(new Azure.Core.TokenRequestContext(new[] { audience }))).Token}");
        var client = new A2AProtocolHttpClient(Options.Create<A2AProtocolClientOptions>(new A2AProtocolClientOptions
        {
            Endpoint = new Uri($"{endpoint}/workflows/a2a/agents/{simpleAgent.Value.Id}?api-version={apiVersion}"),
        }), httpClient);


        // now interact with the agent using the A2A protocol
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
                        new TextPart("Hi there how are you?")
                    ]
                }
            }
        };

        // send inference request
        var response = await client.SendTaskAsync(request);

        foreach (var artifact in response.Result?.Artifacts ?? Enumerable.Empty<Artifact>())
        {
            if (artifact.Parts != null)
            {
                foreach (var part in artifact.Parts.OfType<TextPart>()) Console.WriteLine($"Agent> {part.Text}");
            }
        }

    }
    catch (Exception e)
    {
        Console.WriteLine(e);
    }
    finally
    {
        Console.WriteLine($"Deleting agent: {simpleAgent.Value.Id}");
        await agent.Administration.DeleteAgentAsync(simpleAgent?.Value.Id);
    }
}, endpointOption, audienceOption, apiVersionOption);

return await rootCommand.InvokeAsync(args);