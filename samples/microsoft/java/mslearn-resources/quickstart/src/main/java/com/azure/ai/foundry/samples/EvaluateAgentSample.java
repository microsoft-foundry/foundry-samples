package com.azure.ai.foundry.samples;

import java.util.List;
import java.util.ArrayList;
import java.lang.reflect.Method;

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
 * Sample demonstrating agent evaluation features in Azure AI Agents.
 * 
 * This sample shows how to:
 * - Create a persistent agent
 * - Start a thread and run
 * - Find evaluation-related methods in the SDK clients
 */
public class EvaluateAgentSample {
    private static final ClientLogger logger = new ClientLogger(EvaluateAgentSample.class);
    
    public static void main(String[] args) {
        // Load environment variables with proper error handling
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
            agentName = "evaluation-agent";
            logger.info("No AGENT_NAME provided, using default: {}", agentName);
        }
        
        if (instructions == null) {
            instructions = "You are a helpful assistant that provides clear and concise information about the weather.";
            logger.info("No AGENT_INSTRUCTIONS provided, using default instructions: {}", instructions);
        }

        // Create Azure credential with DefaultAzureCredentialBuilder
        logger.info("Building DefaultAzureCredential");
        TokenCredential credential = new DefaultAzureCredentialBuilder().build();

        try {
            // Build the top-level client with proper configuration
            logger.info("Creating PersistentAgentsClient with endpoint: {}", projectEndpoint);
            System.out.println("\nCreating PersistentAgentsClient...");
            PersistentAgentsClient agentsClient = new PersistentAgentsClientBuilder()
                .endpoint(projectEndpoint)
                .credential(credential)
                .buildClient();
            
            // Derive the administration client for agent-management operations
            logger.info("Getting PersistentAgentsAdministrationClient");
            PersistentAgentsAdministrationClient agentClient = 
                agentsClient.getPersistentAgentsAdministrationClient();
            
            // Create an agent with proper error handling
            logger.info("Creating agent with name: {}, model: {}", agentName, modelName);
            System.out.println("\nCreating an agent...");
            PersistentAgent agent = agentClient.createAgent(new CreateAgentOptions(modelName)
                .setName(agentName)
                .setInstructions(instructions)
            );
            logger.info("Agent created successfully with ID: {}", agent.getId());
            System.out.println("Agent created with ID: " + agent.getId());
            System.out.println("Agent name: " + agent.getName());
            
            // Create a thread and run with the agent
            logger.info("Creating thread and run with agent ID: {}", agent.getId());
            System.out.println("\nCreating thread and run...");
            ThreadRun runResult = agentsClient.createThreadAndRun(new CreateThreadAndRunOptions(agent.getId()));
            
            // Log and display thread information
            logger.info("ThreadRun created with ThreadId: {}", runResult.getThreadId());
            System.out.println("Thread and Run created");
            System.out.println("Thread ID: " + runResult.getThreadId());
            
            // Use reflection to check for evaluation methods in the SDK clients
            logger.info("Checking for evaluation methods in PersistentAgentsAdministrationClient");
            System.out.println("\nPersistentAgentsAdministrationClient evaluation methods:");
            List<String> evaluationMethods = findEvaluationMethods(PersistentAgentsAdministrationClient.class);
            if (evaluationMethods.isEmpty()) {
                logger.info("No evaluation methods found in PersistentAgentsAdministrationClient");
                System.out.println("No evaluation methods found in PersistentAgentsAdministrationClient.");
            } else {
                for (String method : evaluationMethods) {
                    System.out.println("- " + method);
                }
            }
            
            // Check for evaluation methods in the general client
            logger.info("Checking for evaluation methods in PersistentAgentsClient");
            System.out.println("\nPersistentAgentsClient evaluation methods:");
            evaluationMethods = findEvaluationMethods(PersistentAgentsClient.class);
            if (evaluationMethods.isEmpty()) {
                logger.info("No evaluation methods found in PersistentAgentsClient");
                System.out.println("No evaluation methods found in PersistentAgentsClient.");
            } else {
                for (String method : evaluationMethods) {
                    System.out.println("- " + method);
                }
            }
            
            logger.info("Demo completed successfully");
            System.out.println("\nAgent creation and evaluation check completed successfully!");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service returned error: Status code {}, Error message: {}", 
                statusCode, e.getMessage());
            logger.error("Refer to the Azure AI Agents documentation for troubleshooting information.");
            
            // Still print error to console for user visibility
            System.err.printf("Service error %d: %s%n", statusCode, e.getMessage());
            System.err.println("Refer to the Azure AI Agents documentation for troubleshooting information.");
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in evaluation agent sample: {}", e.getMessage(), e);
            
            // Print simplified error to console
            System.err.println("Error: " + e.getMessage());
        }
    }
    
    /**
     * Helper method to find evaluation-related methods in a class using reflection.
     * 
     * @param cls The class to inspect for evaluation-related methods
     * @return A list of method names related to evaluation functionality
     */
    private static List<String> findEvaluationMethods(Class<?> cls) {
        List<String> methods = new ArrayList<>();
        logger.info("Searching for evaluation methods in class: {}", cls.getName());
        
        try {
            for (Method method : cls.getMethods()) {
                String name = method.getName().toLowerCase();
                if (name.contains("evaluat") || name.contains("assess") || name.contains("score") || 
                        name.contains("grade") || name.contains("measure") || name.contains("benchmark")) {
                    methods.add(method.getName());
                    logger.info("Found evaluation method: {}", method.getName());
                }
            }
        } catch (Exception e) {
            logger.error("Error searching for evaluation methods: {}", e.getMessage(), e);
        }
        
        logger.info("Found {} evaluation methods in class {}", methods.size(), cls.getName());
        return methods;
    }
}