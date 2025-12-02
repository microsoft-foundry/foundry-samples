//<chat_completion>
using System.ClientModel.Primitives;
using Azure.Identity;
using OpenAI;
using OpenAI.Chat;

#pragma warning disable OPENAI001

string projectEndpoint = System.Environment.GetEnvironmentVariable("AZURE_AI_INFERENCE")!;
string modelDeploymentName = System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL")!;

BearerTokenPolicy tokenPolicy = new(
    new DefaultAzureCredential(),
    "https://ai.azure.com/.default");
OpenAIClient openAIClient = new(
    authenticationPolicy: tokenPolicy,
    options: new OpenAIClientOptions()
    {
        Endpoint = new($"{projectEndpoint}/openai/v1"),
    });
ChatClient chatClient = openAIClient.GetChatClient(modelDeploymentName);

ChatCompletion completion = await chatClient.CompleteChatAsync(
    [
        new SystemChatMessage("You are a helpful assistant."),
                    new UserChatMessage("How many feet are in a mile?")
    ]);

Console.WriteLine(completion.Content[0].Text);
// </chat_completion>
