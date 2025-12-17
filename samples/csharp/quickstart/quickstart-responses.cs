using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

string projectEndpoint  = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string modelDeploymentName  = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");

AIProjectClient projectClient = new(new Uri(projectEndpoint ), new AzureCliCredential());

ProjectResponsesClient responseClient = projectClient.OpenAI.GetProjectResponsesClientForModel(modelDeploymentName);
ResponseResult response = await responseClient.CreateResponseAsync("What is the size of France in square miles?");

Console.WriteLine(response.GetOutputText());