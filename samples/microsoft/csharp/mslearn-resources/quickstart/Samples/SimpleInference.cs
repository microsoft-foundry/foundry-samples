//<chat_completion>
using Azure;
using Azure.Identity;
using Azure.AI.Projects;
using Azure.AI.Inference;

var projectEndpoint = new Uri(System.Environment.GetEnvironmentVariable("AZURE_AI_ENDPOINT"));
var modelDeploymentName = System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL");
var credential = new DefaultAzureCredential();

AIProjectClient client = new AIProjectClient(projectEndpoint, credential);

ChatCompletionsClient chatClient = client.GetChatCompletionsClient();

var requestOptions = new ChatCompletionsOptions()
{
    Messages =
        {
            new ChatRequestSystemMessage("You are a helpful assistant."),
            new ChatRequestUserMessage("How many feet are in a mile?"),
        },
    Model = modelDeploymentName
};
Response<ChatCompletions> response = chatClient.Complete(requestOptions);
Console.WriteLine(response.Value.Content);
// </chat_completion>
