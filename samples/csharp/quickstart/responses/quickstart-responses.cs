using Azure.Identity;
using Azure.AI.Projects;
using Azure.AI.Extensions.OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
var foundryProjectEndpoint = "your_project_endpoint";

// Create project client to call Foundry API
AIProjectClient projectClient = new(
    endpoint: new Uri(foundryProjectEndpoint),
    tokenProvider: new DefaultAzureCredential());

// Run a responses API call
ProjectResponsesClient responseClient = projectClient.ProjectOpenAIClient.GetProjectResponsesClientForModel(
    "gpt-5-mini"); // supports all Foundry direct models
ResponseResult response = await responseClient.CreateResponseAsync(
    "What is the size of France in square miles?");
string outputText = response.GetOutputText();
if (string.IsNullOrWhiteSpace(outputText))
{
    throw new InvalidOperationException("Response output text was empty.");
}

Console.WriteLine(outputText);
