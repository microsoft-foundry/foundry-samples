package com.azure.ai.agents;

import com.azure.ai.agents.models.AgentVersionDetails;
import com.azure.ai.agents.models.PromptAgentDefinition;
import com.azure.identity.DefaultAzureCredentialBuilder;

public class CreateAgent {
    public static void main(String[] args) {
        // Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
        String ProjectEndpoint = System.getenv().getOrDefault("AZURE_AI_PROJECT_ENDPOINT", "your_project_endpoint");
        String AgentName = System.getenv().getOrDefault("AZURE_AI_FOUNDRY_AGENT_NAME", "your_agent_name");
        String ModelDeployment = System.getenv().getOrDefault("MODEL_DEPLOYMENT", "gpt-5-mini");

        // Create agents client to call Foundry API
        AgentsClient agentsClient = new AgentsClientBuilder()
                .credential(new DefaultAzureCredentialBuilder().build())
                .endpoint(ProjectEndpoint)
                .buildAgentsClient();

        // Create an agent with a model and instructions
        PromptAgentDefinition request = new PromptAgentDefinition(ModelDeployment) // supports all Foundry direct models
                .setInstructions("You are a helpful assistant that answers general questions");
        AgentVersionDetails agent = agentsClient.createAgentVersion(AgentName, request);

        System.out.println("Agent ID: " + agent.getId());
        System.out.println("Agent Name: " + agent.getName());
        System.out.println("Agent Version: " + agent.getVersion());
    }
}