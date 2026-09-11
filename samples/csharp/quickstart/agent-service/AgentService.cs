// This sample combines each step of creating and running agents and conversations into a single example.
// In practice, you would typically separate these steps into different applications.
//
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.AI.Extensions.OpenAI;
using Azure.Identity;
using OpenAI.Responses;

#pragma warning disable OPENAI001

string foundryProjectEndpoint = "your_project_endpoint";
string foundryAgentName = "your_agent_name";

AIProjectClient projectClient = new AIProjectClient(
    new Uri(foundryProjectEndpoint),
    new DefaultAzureCredential());

//
// Create an agent version for a new prompt agent
//

ProjectsAgentDefinition agentDefinition = new DeclarativeAgentDefinition(
    "gpt-5-mini") // supports all Foundry direct models
{
    Instructions = "You are a foo bar agent. In EVERY response you give, ALWAYS include both `foo` and `bar` strings somewhere in the response.",
};
ProjectsAgentVersion newAgentVersion = await projectClient.AgentAdministrationClient.CreateAgentVersionAsync(
    foundryAgentName,
    options: new(agentDefinition));

//
// Create a conversation to maintain state between calls
//

ProjectConversationCreationOptions conversationOptions = new()
{
    Items = { ResponseItem.CreateSystemMessageItem("Your preferred genre of story today is: horror.") },
    Metadata = { ["foo"] = "bar" },
};
ProjectConversation conversation = await projectClient.ProjectOpenAIClient.GetProjectConversationsClient().CreateProjectConversationAsync(conversationOptions);

//
// Add items to an existing conversation to supplement the interaction state
//
string existingConversationId = conversation.Id;

_ = await projectClient.ProjectOpenAIClient.GetProjectConversationsClient().CreateProjectConversationItemsAsync(
    existingConversationId,
    [ResponseItem.CreateSystemMessageItem("Story theme to use: department of licensing.")]);

//
// Use the agent and conversation in a response
//

ProjectResponsesClient responseClient = projectClient.ProjectOpenAIClient.GetProjectResponsesClientForAgent(
    defaultAgent: foundryAgentName,
    defaultConversationId: existingConversationId);
List<ResponseItem> items = [ResponseItem.CreateUserMessageItem(inputTextContent: "Tell me a one-line story.")] ;
ResponseResult response = await responseClient.CreateResponseAsync(items);

Console.WriteLine(response.GetOutputText());
