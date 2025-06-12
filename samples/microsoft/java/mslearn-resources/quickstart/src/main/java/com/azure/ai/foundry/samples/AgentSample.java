package com.azure.ai.foundry.samples;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClient;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClientBuilder;
import com.azure.ai.agents.persistent.models.CreateAgentOptions;
import com.azure.ai.agents.persistent.models.CreateThreadAndRunOptions;
import com.azure.ai.agents.persistent.models.PersistentAgent;
import com.azure.ai.agents.persistent.models.ThreadRun;

/**
 * Sample demonstrating using Azure AI Agents Persistent SDK with Java.
 */
public class AgentSample {
    public static void main(String[] args) {
        // Load environment variables
        String endpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        String agentName = System.getenv("AGENT_NAME");
        String instructions = System.getenv("AGENT_INSTRUCTIONS");

        // Validate required environment variables
        if (endpoint == null) {
            System.err.println("ERROR: Set PROJECT_ENDPOINT, e.g. https://<your>.services.ai.azure.com/api/projects/<project>");
            return;
        }
        if (modelName == null) {
            modelName = "gpt4o";  // Default if not provided
            System.out.println("MODEL_DEPLOYMENT_NAME not set, using default: " + modelName);
        }
        if (agentName == null) {
            agentName = "java-quickstart-agent";  // Default if not provided
            System.out.println("AGENT_NAME not set, using default: " + agentName);
        }
        if (instructions == null) {
            instructions = "You are a helpful assistant that provides clear and concise information.";  // Default if not provided
            System.out.println("AGENT_INSTRUCTIONS not set, using default instructions");
        }

        TokenCredential cred = new DefaultAzureCredentialBuilder().build();

        // Create admin client
        PersistentAgentsAdministrationClient adminClient = new PersistentAgentsAdministrationClientBuilder()
            .endpoint(endpoint)
            .credential(cred)
            .buildClient();

        // Create an agent
        System.out.println("\nCreating an agent...");
        PersistentAgent agent = adminClient.createAgent(new CreateAgentOptions(modelName)
            .setName(agentName)
            .setInstructions(instructions)
        );
        System.out.println("Agent created with ID: " + agent.getId());
        System.out.println("Agent name: " + agent.getName());

        // Create a thread and run
        System.out.println("\nCreating thread and run...");
        ThreadRun runResult = adminClient.createThreadAndRun(new CreateThreadAndRunOptions(agent.getId()));
        
        // Print available ThreadRun information
        System.out.println("Thread and Run created");
        System.out.println("Thread ID: " + runResult.getThreadId());
        
        // Use reflection to see available methods on ThreadRun
        System.out.println("\nAvailable methods on ThreadRun class:");
        for (java.lang.reflect.Method method : ThreadRun.class.getMethods()) {
            if (method.getName().startsWith("get")) {
                System.out.println("- " + method.getName());
            }
        }
        
        System.out.println("\nDemo completed successfully!");
    }
}