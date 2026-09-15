package com.azure.ai.agents;

// Live-validation-only helper: deletes the agent created by ChatWithAgent.java so
// repeated live-validation runs don't accumulate agent versions. Not part of the
// documented quickstart narrative.

import com.azure.identity.DefaultAzureCredentialBuilder;

public class LiveSetupDeleteAgent {
    public static void main(String[] args) {
        // Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
        String foundryProjectEndpoint = "your_project_endpoint";
        String foundryAgentName = "your-agent-name";

        // Create agents client to call Foundry API
        AgentsClient agentsClient = new AgentsClientBuilder()
                .credential(new DefaultAzureCredentialBuilder().build())
                .endpoint(foundryProjectEndpoint)
                .buildAgentsClient();

        agentsClient.deleteAgent(foundryAgentName);
        System.out.println("Agent deleted (name: " + foundryAgentName + ")");
    }
}
