using Azure.AI.Projects;
using Azure.Identity;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

string PROJECT_ENDPOINT = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string MODEL_DEPLOYMENT_NAME = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");
string AGENT_NAME = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AGENT_NAME'");

AIProjectClient projectClient = new(new Uri(AZURE_AI_FOUNDRY_PROJECT_ENDPOINT), new AzureCliCredential());
AgentClient agentClient = projectClient.GetAgentClient();
OpenAIClient openAIClient = agentClient.GetOpenAIClient();
OpenAIResponseClient responseClient = openAIClient.GetOpenAIResponseClient(MODEL_DEPLOYMENT_NAME);

ResponseCreationOptions responseCreationOptions = new();

List<ResponseItem> items = [ResponseItem.CreateUserMessageItem("What is the size of France in square miles?")];
OpenAIResponse response = await responseClient.CreateResponseAsync(items, responseCreationOptions);

Console.WriteLine(response.GetOutputText());