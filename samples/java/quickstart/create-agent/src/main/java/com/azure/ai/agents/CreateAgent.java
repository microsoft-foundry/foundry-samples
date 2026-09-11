package com.azure.ai.agents;

import com.azure.ai.agents.models.AgentVersionDetails;
import com.azure.ai.agents.models.PromptAgentDefinition;
import com.azure.identity.DefaultAzureCredentialBuilder;

public class CreateAgent {
    public static void main(String[] args) {
        // Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
        String foundryProjectEndpoint = "your_project_endpoint";
        String foundryAgentName = "your_agent_name";

        // Create agents client to call Foundry API
        AgentsClient agentsClient = new AgentsClientBuilder()
                .credential(new DefaultAzureCredentialBuilder().build())
                .endpoint(foundryProjectEndpoint)
                .buildAgentsClient();

        // Create an agent with a model and instructions
        PromptAgentDefinition request = new PromptAgentDefinition("gpt-5-mini") // supports all Foundry direct models
                .setInstructions("You are a helpful assistant that answers general questions");
        AgentVersionDetails agent = agentsClient.createAgentVersion(foundryAgentName, request);

        System.out.println("Agent ID: " + agent.getId());
        System.out.println("Agent Name: " + agent.getName());
        System.out.println("Agent Version: " + agent.getVersion());
    }
}