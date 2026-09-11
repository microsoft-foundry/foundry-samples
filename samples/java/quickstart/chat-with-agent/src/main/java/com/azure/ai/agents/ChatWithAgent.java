package com.azure.ai.agents;

import com.azure.ai.agents.models.PromptAgentDefinition;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.openai.client.OpenAIClient;
import com.openai.models.conversations.Conversation;
import com.openai.models.responses.Response;
import com.openai.models.responses.ResponseCreateParams;

public class ChatWithAgent {
    public static void main(String[] args) {
        // Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
        String foundryProjectEndpoint = "your_project_endpoint";
        String foundryAgentName = "your-agent-name";
        
        AgentsClientBuilder builder = new AgentsClientBuilder()
                .credential(new DefaultAzureCredentialBuilder().build())
                .endpoint(foundryProjectEndpoint);

        // Create the agent (or a new version, if it already exists)
        AgentsClient agentsClient = builder.buildAgentsClient();
        PromptAgentDefinition agentDefinition = new PromptAgentDefinition("gpt-5-mini") // supports all Foundry direct models
                .setInstructions("You are a helpful assistant that answers general questions");
        agentsClient.createAgentVersion(foundryAgentName, agentDefinition);

        // Create an OpenAI client bound to the agent endpoint
        OpenAIClient openai = builder.buildAgentScopedOpenAIClient(foundryAgentName);

        // Create a conversation for multi-turn chat
        Conversation conversation = openai.conversations().create();

        // Chat with the agent to answer questions
        Response response = openai.responses().create(
            ResponseCreateParams.builder()
                .conversation(conversation.id())
                .input("What is the size of France in square miles?")
                .build());
        printResponse(response);

        // Ask a follow-up question in the same conversation
        Response followUp = openai.responses().create(
            ResponseCreateParams.builder()
                .conversation(conversation.id())
                .input("And what is the capital city?")
                .build());
        printResponse(followUp);
    }

    private static void printResponse(Response response) {
        response.output().forEach(item -> item.message().ifPresent(message ->
            message.content().forEach(content -> content.outputText().ifPresent(
                text -> System.out.println(text.text())))));
    }
}