package com.azure.ai.foundry.samples;

import com.azure.ai.agents.persistent.PersistentAgentsClient;
import com.azure.ai.agents.persistent.PersistentAgentsClientBuilder;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClient;
import com.azure.ai.agents.persistent.models.CreateAgentOptions;
import com.azure.ai.agents.persistent.models.CreateThreadAndRunOptions;
import com.azure.ai.agents.persistent.models.PersistentAgent;
import com.azure.ai.agents.persistent.models.ThreadRun;
import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;


/**
 * Sample demonstrating using Azure AI Agents Persistent SDK with Java.
 * This sample shows how to:
 * - Create a persistent agent
 * - Start a thread and run with the agent
 */
public class AgentSample {
    private static final ClientLogger logger = new ClientLogger(AgentSample.class);

    public static void main(String[] args) {
        // Load environment variables with better error handling, supporting both .env and system environment variables
        String endpoint = System.getenv("AZURE_ENDPOINT");
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        String agentName = System.getenv("AGENT_NAME");
        String instructions = System.getenv("AGENT_INSTRUCTIONS");

        

        // Check for required endpoint configuration
        if (projectEndpoint == null && endpoint == null) {
            String errorMessage = "Environment variables not configured. Required: either PROJECT_ENDPOINT or AZURE_ENDPOINT must be set.";
            logger.error("ERROR: {}", errorMessage);
            logger.error("Please set your environment variables or create a .env file. See README.md for details.");
            return;
        }
        
        // Use AZURE_ENDPOINT as fallback if PROJECT_ENDPOINT not set
        if (projectEndpoint == null) {
            projectEndpoint = endpoint;
            logger.info("Using AZURE_ENDPOINT as PROJECT_ENDPOINT: {}", projectEndpoint);
        }

        // Set defaults for optional parameters with informative logging
        if (modelName == null) {
            modelName = "gpt4o";
            logger.info("No MODEL_DEPLOYMENT_NAME provided, using default: {}", modelName);
        }
        if (agentName == null) {
            agentName = "java-quickstart-agent";
            logger.info("No AGENT_NAME provided, using default: {}", agentName);
        }
        if (instructions == null) {
            instructions = "You are a helpful assistant that provides clear and concise information.";
            logger.info("No AGENT_INSTRUCTIONS provided, using default instructions");
        }

        // Create Azure credential with DefaultAzureCredentialBuilder
        // This supports multiple authentication methods including environment variables,
        // managed identities, and interactive browser login
        logger.info("Building DefaultAzureCredential");
        TokenCredential credential = new DefaultAzureCredentialBuilder().build();

        try {
            // Build the general agents client
            logger.info("Creating PersistentAgentsClient with endpoint: {}", projectEndpoint);
            System.out.println("Creating PersistentAgentsClient...");
            PersistentAgentsClient agentsClient = new PersistentAgentsClientBuilder()
                .endpoint(projectEndpoint)
                .credential(credential)
                .buildClient();

            // Derive the administration client
            logger.info("Getting PersistentAgentsAdministrationClient");
            System.out.println("Deriving PersistentAgentsAdministrationClient...");
            PersistentAgentsAdministrationClient adminClient =
                agentsClient.getPersistentAgentsAdministrationClient();

            // Create an agent
            logger.info("Creating agent with name: {}, model: {}", agentName, modelName);
            System.out.println("\nCreating an agent...");
            PersistentAgent agent = adminClient.createAgent(
                new CreateAgentOptions(modelName)
                    .setName(agentName)
                    .setInstructions(instructions)
            );
            logger.info("Agent created successfully with ID: {}", agent.getId());
            System.out.printf("Agent created: ID=%s, Name=%s%n", agent.getId(), agent.getName());

            // Start a thread/run on the general client
            logger.info("Creating thread and run with agent ID: {}", agent.getId());
            System.out.println("\nCreating thread and run...");
            ThreadRun runResult = agentsClient.createThreadAndRun(
                new CreateThreadAndRunOptions(agent.getId())
            );
            logger.info("ThreadRun created with ThreadId: {}", runResult.getThreadId());
            System.out.printf("ThreadRun created: ThreadId=%s%n", runResult.getThreadId());

            // List available getters on ThreadRun for informational purposes
            System.out.println("\nAvailable getters on ThreadRun:");
            for (var method : ThreadRun.class.getMethods()) {
                if (method.getName().startsWith("get")) {
                    System.out.println(" - " + method.getName());
                }
            }

            logger.info("Demo completed successfully");
            System.out.println("\nDemo completed successfully!");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service returned error: Status code {}, Error message: {}", 
                statusCode, e.getMessage());
            System.err.printf("Service error %d: %s%n", statusCode, e.getMessage());
            System.err.println("Refer to the Azure AI Agents documentation for troubleshooting information.");
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in agent sample: {}", e.getMessage(), e);
            System.err.println("Error: " + e.getMessage());
        }
    }
}
