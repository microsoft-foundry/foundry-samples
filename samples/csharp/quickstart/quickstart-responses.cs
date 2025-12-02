#:package Azure.AI.Projects@2.0.0-alpha.20251104.9
#:package Azure.AI.Agents@2.*-*
#:package Azure.Identity@1.*
#:package OpenAI@2.6.*
#:property PublishAot=false
#:property NoWarn=OPENAI001

using Azure.AI.Projects;
using Azure.AI.Agents;
using Azure.Identity;
using OpenAI;
using OpenAI.Responses;

string AZURE_AI_FOUNDRY_PROJECT_ENDPOINT = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'AZURE_AI_FOUNDRY_PROJECT_ENDPOINT'");
string MODEL_DEPLOYMENT_NAME = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME'");
string AGENT_NAME = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AZURE_AI_FOUNDRY_AGENT_NAME'");

AIProjectClient projectClient = new(new Uri(AZURE_AI_FOUNDRY_PROJECT_ENDPOINT), new AzureCliCredential());
AgentClient agentClient = projectClient.GetAgentClient();
OpenAIClient openAIClient = agentClient.GetOpenAIClient();
OpenAIResponseClient responseClient = openAIClient.GetOpenAIResponseClient(MODEL_DEPLOYMENT_NAME);

ResponseCreationOptions responseCreationOptions = new();

List<ResponseItem> items = [ResponseItem.CreateUserMessageItem("What is the size of France in square miles?")];
OpenAIResponse response = await responseClient.CreateResponseAsync(items, responseCreationOptions);

Console.WriteLine(response.GetOutputText());