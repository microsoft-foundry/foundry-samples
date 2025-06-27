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
 * Sample demonstrating how to work with Azure AI Agents using the Azure AI Agents Persistent SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with Azure credentials
 * - Create a persistent agent with custom instructions
 * - Start a thread and run with the agent
 * - Access various properties of the agent and thread run
 * - Work with the PersistentAgentsClient and PersistentAgentsAdministrationClient
 * 
 * Environment variables:
 * - AZURE_ENDPOINT: Optional fallback. The base endpoint for your Azure AI service if PROJECT_ENDPOINT is not provided.
 * - PROJECT_ENDPOINT: Required. The endpoint for your Azure AI Project.
 * - MODEL_DEPLOYMENT_NAME: Optional. The model deployment name (defaults to "gpt-4o").
 * - AGENT_NAME: Optional. The name to give to the created agent (defaults to "java-quickstart-agent").
 * - AGENT_INSTRUCTIONS: Optional. The instructions for the agent (defaults to a helpful assistant).
 * 
 * Note: This sample requires proper Azure authentication. It uses DefaultAzureCredential which supports
 * multiple authentication methods including environment variables, managed identities, and interactive login.
 * 
 * SDK Features Demonstrated:
 * - Using the Azure AI Agents Persistent SDK (com.azure:azure-ai-agents-persistent:1.0.0-beta.2)
 * - Creating an authenticated client with DefaultAzureCredential
 * - Using the PersistentAgentsClientBuilder pattern for client instantiation
 * - Working with the PersistentAgentsAdministrationClient for agent management
 * - Creating agents with specific configurations (name, model, instructions)
 * - Starting threads and runs for agent conversations
 * - Working with agent state and thread management
 * - Accessing agent and thread run properties
 * - Implementing proper error handling for Azure service interactions
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
            modelName = "gpt-4o";
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
            PersistentAgentsClient agentsClient = new PersistentAgentsClientBuilder()
                .endpoint(projectEndpoint)
                .credential(credential)
                .buildClient();

            // Derive the administration client
            logger.info("Getting PersistentAgentsAdministrationClient");
            PersistentAgentsAdministrationClient adminClient =
                agentsClient.getPersistentAgentsAdministrationClient();

            // Create an agent
            logger.info("Creating agent with name: {}, model: {}", agentName, modelName);
            PersistentAgent agent = adminClient.createAgent(
                new CreateAgentOptions(modelName)
                    .setName(agentName)
                    .setInstructions(instructions)
            );
            logger.info("Agent created: ID={}, Name={}", agent.getId(), agent.getName());
            logger.info("Agent model: {}", agent.getModel());

            // Start a thread/run on the general client
            logger.info("Creating thread and run with agent ID: {}", agent.getId());
            ThreadRun runResult = agentsClient.createThreadAndRun(
                new CreateThreadAndRunOptions(agent.getId())
            );
            logger.info("ThreadRun created: ThreadId={}", runResult.getThreadId());

            // List available getters on ThreadRun for informational purposes
            logger.info("\nAvailable getters on ThreadRun:");
            for (var method : ThreadRun.class.getMethods()) {
                if (method.getName().startsWith("get")) {
                    logger.info(" - {}", method.getName());
                }
            }

            logger.info("\nDemo completed successfully!");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service error {}: {}", statusCode, e.getMessage());
            logger.error("Refer to the Azure AI Agents documentation for troubleshooting information.");
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in agent sample: {}", e.getMessage(), e);
        }
    }
}
